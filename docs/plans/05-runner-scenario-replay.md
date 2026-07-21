# 계획 05 — Runner 구현과 시나리오 재생 테스트

- 상태: 진행중
- 날짜: 2026-07-20
- 선행: [계획 04](04-memory-buffer.md) (§7-3 `since` detector 측 구현 완료)

## 목적

Runner 를 구현해 파이프라인을 한 바퀴 돌리고, `datasets/sn` 의 3개 결함 시나리오를 30초 배치로
재생해 **시나리오별 스냅샷 번들이 실제로 어떻게 구성되는지** 확인한다. 회귀 검증(단정)과
눈으로 볼 결과(리포트)를 둘 다 낸다.

## 결정 사항

| # | 결정 | 근거 |
|---|---|---|
| R1 | 재생 하네스는 **가짜 Collector** 로 만든다 (정규화 배치 직접 주입 아님) | `Collector.poll() -> RawBatch` 만 대체하면 **실제 normalizer 가 루프에 남는다**. 비용은 같은데 검증 범위가 넓다 |
| R2 | detector `condition` 은 **`Settings` 에 dict 로** 둔다 | 기존 Settings 패턴과 일관. `RCA_` 환경변수 override 와 테스트 주입이 둘 다 쉽다. 값은 ADR-006 미결의 확정치를 기본값으로 |
| R3 | 타임스탬프는 **시프트하지 않는다** | 버퍼 축출이 벽시계가 아니라 watermark 기준이라 2025-11-03 데이터가 그대로 돈다. 리플레이어의 시각 보정은 테스트에 불필요 |
| R4 | Runner 는 구성요소를 **주입받는다** | `tick()` 이 테스트 가능해야 한다. `run()` 의 sleep 루프만 실시간용 |
| R5 | 파일 재생(E2E) 은 **이번 범위 밖** | collectors 의 오프셋·CSV 헤더·미완성 줄은 `tests/test_collectors.py` 가 이미 덮는다. 49MB×3 재생은 CI 부담 |

## §1. 데이터셋 실측

| 시나리오 | 스팬 | metric 샘플 | logs | traces |
|---|---|---|---|---|
| `Svc_Kill_Media` | 2025-11-04 00:01:57 ~ 00:21:58 (20분) | 80 / 15초 | 49MB | 2.9MB |
| `Code_Stop_MediaService` | 2025-11-04 02:56:54 ~ 03:21:54 (25분) | 102 | 48MB | 2.4MB |
| `Perf_CPU_Contention` | 2025-11-03 22:27:14 ~ 22:46:59 (20분) | 81 | 49MB | 2.8MB |

20~25분 = **40~50 틱**. 6분 번들이 3~4개 들어갈 길이라 재발화 거동까지 관측된다.

## §2. Runner 설계

```python
class Runner:
    def __init__(self, settings, *, sources, buffer, detectors, snapshot, transport): ...
        # sources: list[tuple[Collector, Normalizer]]
        self._detect_since: datetime | None = None

    def tick(self) -> list[SnapshotBundle]:
        batches = [n.normalize(c.poll()) for c, n in self.sources]
        for b in batches:
            self.buffer.append(b)
        observed_until = max(b.observed_until for b in batches)

        bundles = self.snapshot.finalize_ready(observed_until, self.buffer)
        if bundles:
            self._detect_since = bundles[-1].window.end     # 계획 04 §7-3

        evidences = [
            e for b in batches for d in self.detectors
            for e in d.evaluate(b, self.buffer, since=self._detect_since)
        ]
        self.snapshot.register_triggers(evidences, self.buffer)

        for bundle in bundles:
            self.transport.send(bundle)
        return bundles
```

**순서가 계약이다.** `append → finalize_ready → evaluate → register_triggers`.
`append` 가 먼저인 이유는 창 기반 detector 가 버퍼에 의존해서고, `finalize_ready` 가 `evaluate`
앞인 이유는 이 틱에 완성된 번들의 창 끝이 곧 이번 평가의 하한이기 때문이다. 뒤집으면 방금
전송한 구간으로 즉시 재발화한다 (계획 04 §7-3, ADR-006 러너 통합 전제).

`transport.send` 를 마지막에 두어, 전송이 실패해도 `_detect_since` 는 이미 전진해 있다 —
같은 번들을 무한 재시도하지 않는다.

## §3. 재생 하네스 (`tests/replay/`)

```
DatasetReplayCollector(Collector)
  __init__(scenario_dir, modality, tick_sec=30)
  poll() -> RawBatch    # 호출할 때마다 다음 30초 구간
```

동작:

1. 시나리오 디렉토리를 한 번 읽어 **원본 줄/행 그대로** 메모리에 올린다.
2. 버킷팅용으로만 타임스탬프를 파싱해 30초 구간에 나눈다 (리플레이어가 하는 일과 동일).
3. `poll()` 마다 다음 구간을 `RawBatch(records=[원본 dict], sources=[파일명])` 로 낸다.

**중요 — 여기서 멈춘다.** 원본 줄을 `{"raw": line}` / 컬럼 dict 그대로 넘기므로
**정규화는 실제 `LogNormalizer`·`MetricNormalizer`·`TraceNormalizer` 가 한다.**
`sources` 는 파일명 목록이라 roster·present 판정도 실제 경로를 탄다.

t0 = 3개 모달리티 타임스탬프의 최솟값. 모든 모달리티가 같은 틱 경계를 공유한다
(ADR-007 §4 가 전제하는 "한 틱에 3개 모달리티 동시 관측").

## §4. 시나리오별 기대

| 시나리오 | 발화해야 | 침묵해야 | 특이 검증 |
|---|---|---|---|
| `Svc_Kill_Media` | `restart_marker`(media) | `cpu_spike`, svc_kill metric/trace | anchor = 2번째 부팅 `00:03:41` |
| `Code_Stop_MediaService` | `trace_5xx`, `nginx_error` | `cpu_spike`, code_stop metric | media 로그 끊김 → `modality_info` **missing** |
| `Perf_CPU_Contention` | `cpu_spike` | `restart_marker` | `error_rate` 가 duplicate-key artifact 로 오발화하지 않는가 |

침묵 검증이 발화 검증만큼 중요하다 — `cpu_spike` 는 `metric_name` 불일치로 조용히 0건이었던
전례가 있다(§7-1, `833460a`).

## §5. 검증할 불변식

시나리오 무관하게 항상 성립해야 하는 것:

1. **번들 창 = `[anchor−180, anchor+180)`**, `trigger_info.trigger_time == anchor`
2. **pre 잘림 없음** — 번들 첫 레코드 timestamp ≥ `window.start`, 창 메타 3분 ↔ 실제 내용 일치
3. **레코드 시간순** — pre 뒤에 post 를 이어 붙인 결과가 오름차순
4. **`since` 효과** — 번들 N+1 의 발화 근거가 된 샘플이 번들 N 의 창 안에 있지 않다
5. **동시 세션 1개** — 어느 시점에도 열린 세션은 최대 하나
6. **coverage 3상태** — `modality_info` 의 각 소스가 missing/empty/data 중 하나로 확정

## §6. 결과 리포트

테스트가 `test_report/scenario-replay-report.md` 를 생성한다:

- 시나리오별 **발화 타임라인** — 틱 번호, detector, `trigger_time`, service
- **번들 목록** — 창, 발화 모달리티, 모달리티별 레코드 수
- **coverage 표** — 소스별 missing/empty/data
- **볼륨 실측** — 번들당 총 레코드 수·바이트 (§7-2 payload 상한 논의 재료)

단정만으로는 "결과값 확인" 이 안 된다. 리포트가 눈으로 볼 산출물이다.

## §7. 이 작업이 꺼낼 미결

1. **detector condition 배선** — ADR-006 미결이 "값 확정 완료, 배선은 러너 단계" 로 남아 있다.
   R2 로 `Settings` 에 넣는다. 이 계획에서 해소.
2. **번들 payload 상한** — ADR-006 미결. 6분 창에 전 서비스 로그면 수십만 줄이다. 이 테스트가
   실측치를 처음 낸다. 상한·샘플링 정책 결정은 수치를 보고.
3. **`trigger_time` 의미** — 계획 04 §9. 시나리오별 anchor 를 실제로 보면 배치 경계 통일이
   필요한지 판단 근거가 나온다.

## §8. 작업 순서 (TDD)

1. `Settings` 에 detector condition 추가 (R2) — 기본값은 ADR-006 확정치
2. `Runner.tick()` — 가짜 구성요소로 순서 계약부터 RED→GREEN (§2)
3. `DatasetReplayCollector` — 30초 버킷팅·`sources` 산출 (§3)
4. 시나리오 3종 테스트 (§4·§5)
5. 리포트 생성 (§6)

데이터셋이 없는 클론에서는 3~5를 skip 한다 (`tests/trigger/test_realdata.py` 와 동일 패턴).
