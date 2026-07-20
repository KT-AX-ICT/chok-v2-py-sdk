# 계획 04 — MemoryBuffer 구현 설계

엣지 파이프라인 ③ 버퍼 계층. 정규화 배치를 롤링 보관하고, 트리거 이후 스냅샷 조립이
구간 조회로 pre/post 를 가져갈 수 있게 한다. 계획 02 §③ 을 구체화하며 결정 C5(watermark 축출)는
그대로 유지하고, 보존 기간 산정과 coverage 집계 규칙을 새로 확정한다.

- 브랜치: `feat/tailer-normalization-buffer`
- 선행: [계획 02](02-collector-normalization-buffer.md) · [계획 03](03-tail-rework-normalization.md)
- 계약: `MemoryBuffer.append(NormalizedBatch)` / `get_snapshot(start, end) -> MultimodalSnapshot`
  (ADR-005), 윈도 정의 [ADR-001](../decisions/ADR-001-snapshot-window.md)

## 결정 사항

| # | 결정 | 근거 |
|---|---|---|
| B1 | 생성자를 `MemoryBuffer(retention_sec)` 로. 기본·주입값은 `PRE_SEC + 루프 주기`(=180+30=**210**) | pre 와 post 는 **시점이 다른 별개 질의**라 더해지지 않는다. 두 질의 각각에 필요한 값이 210 으로 같다(아래 §1). 버퍼는 pre/post 의미를 모르고 보존 기간만 안다 |
| B2 | coverage `present` = 윈도 내 배치들의 **OR**, `record_count` = **합계** | Code_Stop(전 배치 부재)은 missing 으로 정확히 잡힌다. 마지막 배치 기준으로 하면 `present=False` 인데 `record_count>0` 인 모순 상태가 생겨 소비자가 해석할 수 없다 |
| B3 | 축출·조회 모두 **레코드 timestamp** 기준. 축출 임계 = `watermark − retention_sec`, watermark = 관측된 `observed_until` 최대값 | 계획 02 C5 — 벽시계가 아니라 관측 진행도를 기준 삼으면 재생 정지·시계 어긋남에도 버퍼가 스스로 비지 않는다 |
| B4 | `get_snapshot` 결과 레코드는 timestamp 오름차순 정렬 | 배치 내 레코드는 **파일 단위로 읽히므로 시간순이 아니다**(파일 A 전체 → 파일 B 전체). 소비자가 매번 정렬하지 않도록 여기서 보장 |

## §1. 보존 기간이 210 인 유도

SDK 의 업무 범위는 **트리거 1회 → 기준점 앞뒤 3분(6분 창) 1개 번들 전송**까지다. 에러가 몇 분
지속되어도 전 구간을 따라가지 않는다. 수집·정규화·적재는 그 사이에도 멈추지 않는다.

버퍼는 롤링이라 시간이 흐르면 옛 구간이 밀려 사라지므로, 두 질의를 각각 견뎌야 한다.
**둘은 시점이 다른 별개 질의라 더해지지 않는다** — `PRE_SEC + POST_SEC` 로 잡으면 과다다.

anchor `T`, 루프 주기 30초 기준:

| 질의 | 조회 시점 (watermark) | 필요한 구간 | 필요 보존 |
|---|---|---|---|
| pre — `register_triggers` 가 즉시 복사 | `W₁ ≈ T` (최대 한 틱 뒤) | `[T−180, T)` | `180 + (W₁−T)` → **≤ 210** |
| post — `observed_until ≥ T+180` 인 틱 | `W₂ ∈ [T+180, T+210)` | `[T, T+180)` | `W₂ − T` → **< 210** |

두 요구가 같은 값(210)으로 수렴하므로 `retention_sec = PRE_SEC(180) + 루프 주기(30) = 210`
이다. `Settings.buffer_window_sec` 기본값 210 과도 일치한다.

여유는 각각 정확히 1 틱이다. 조회가 한 사이클 밀리면 앞부분이 **로그 없이** 잘린다.
밀릴 수 있는 경로는 **tick 드리프트** 하나다 — `sleep(30)` + 처리 시간이라 실제 주기는
30초보다 길고 누적된다.

모달리티별 `observed_until` 불일치는 위험이 아니다(ADR-007 §4): 러너가 매 틱 3모달리티를
같은 시각에 poll 하므로 `observed_until` 이 동기 진행한다. 축출 watermark 가 전체 max 여도
특정 모달리티만 먼저 버려지지 않는다.

추가로, anchor 가 배치 폭(30초)보다 더 과거면 pre 앞부분이 잘린다. 배치 단위 detector 는
`trigger_time = observed_until` 이라 무관하고, 창 기반 detector(`cpu_spike`·`restart_marker`)도
**최초 발화 시점**에는 조건이 막 성립한 순간이라 30초 이내다. 다만 세션 종료 후 조건이
계속 유지되어 재발화하면 anchor 가 크게 낡을 수 있다 — 이는 버퍼가 아니라 세션 정책 문제다
(아래 §7).

여유를 넓히려면 `retention_sec` 만 올리면 된다(예: 240 = 2 틱). 다만 근거 없이 `PRE+POST`
같은 식으로 부풀리지 않는다 — 유도가 흐려지면 다음 사람이 조절 레버를 잘못 잡는다.

### 정정 이력

최초 설계는 보존을 `pre + post = 390` 으로 잡았다. 이는 **pre 와 post 를 둘 다 마지막에
꺼낸다**는 잘못된 전제였다. 실제 `register_triggers` 는 트리거 시점에 pre 를 즉시 복사하므로
(assembler.py) 두 질의는 겹치지 않는다. 위 표가 정정된 유도다.

## §2. 내부 구조

```python
self._records: dict[Modality, list[NormalizedRecord]]   # 모달리티별 시계열
self._history: dict[Modality, list[BatchCoverage]]      # 배치별 (관측 구간, roster)
self._watermark: datetime | None                        # 관측된 observed_until 최대값
```

`BatchCoverage` 는 buffer 내부 dataclass(`observed_from`·`observed_until`·`roster`).
schemas 공용 계약을 늘리지 않기 위해 내부 타입으로 둔다.

## §3. `append(batch)`

1. `batch.records` 를 해당 모달리티 리스트에 추가
2. `_history[modality]` 에 `BatchCoverage(from, until, roster)` 추가 —
   **레코드 0건 배치도 반드시 남긴다** (empty 판정 재료)
3. watermark 갱신 = `max(기존, batch.observed_until)`
4. 축출 — `timestamp < watermark − retention_sec` 인 레코드 제거,
   `observed_until < 임계` 인 이력 제거

축출은 append 마다 전체 스캔(O(n))이다. 30초에 한 번, 수만 건 규모라 자료구조 최적화는 YAGNI.

## §4. `get_snapshot(start, end)`

- **레코드**: `start <= timestamp < end`(반열림) 필터 → `model_copy(deep=True)` 로 독립 복사본 →
  timestamp 오름차순 정렬(B4)
- **coverage**: 구간과 겹치는 배치 = `observed_from < end and observed_until > start`.
  배치가 연속(`배치N.until == 배치N+1.from`)이므로 경계 배치 이중 계산이 없다 —
  윈도 시작 직전에 끝난 배치는 `until > start` 가 False 라 자연히 빠진다.
- 겹치는 배치들의 roster 를 source 별로 접어 `SourceStatus(source, present=OR, record_count=SUM)`
  → `coverage[modality.value]`
- 반환 `MultimodalSnapshot(logs, metrics, traces, coverage)`

deep copy 이유: 스냅샷 조립·전송 중에도 버퍼는 계속 append·축출된다. 얕은 복사면 전송 직전에
번들 내용이 바뀔 수 있다.

## §5. 테스트 전략 (TDD)

| 대상 | 케이스 |
|---|---|
| append·축출 | watermark 진행에 따른 축출 · 경계값(임계와 정확히 같으면 유지) · 벽시계 무관(시간이 안 흘러도 watermark 로 축출) · 0건 배치도 이력 유지 |
| 구간 조회 | 반열림 `[start, end)` — start 포함·end 제외 · 구간 밖 제외 · 빈 구간 |
| 독립성 | 스냅샷 취득 후 버퍼에 append·축출 → 스냅샷 내용 불변 |
| 정렬 | 파일 순서로 뒤섞여 들어온 레코드가 timestamp 순으로 반환 |
| coverage | OR 집계(한 배치만 present) · count 합계 · 겹침 판정 경계(직전 배치 제외) · 3상태(missing·empty·data) |
| 모달리티 분리 | log/metric/trace 가 각 리스트에 정확히 배분 |

## §6. 문서 여파

- `buffer/README.md` 현행화 — 현재 `add()/window_events()` 로 적혀 있으나 실제 계약은
  `append()/get_snapshot()`.
- ADR-001 에 보존 유도 추가: 보존 = `PRE_SEC + 루프 주기` = 210. pre 는 트리거 시점 즉시
  캡처하므로 pre 와 post 는 **더해지지 않는다** (§1 정정 이력 참조).
- Runner 배선(retention 주입)은 계획 02 와 동일하게 **범위 밖** — Runner 담당자에게 전달할 사항.

## §7. 인접 계층에 전달할 사항 (버퍼 범위 밖)

버퍼 유도를 정정하며 trigger·snapshot 코드를 읽고 확인한 사항. 소유가 아니라 손대지 않았다.
`origin/feat/modality-trigger-detectors` 를 rebase 로 받으며 해소 여부를 갱신했다(2026-07-20).

1. ~~**`cpu_spike` 가 발화 불가**~~ — **해소** (`833460a`). detector 가 `metric_name == "system_cpu"`
   를 찾는데 정규화는 파일명 stem 을 쓰므로 `system_cpu_usage.csv` → `"system_cpu_usage"` 라
   초과 샘플이 항상 0건이었다. upstream 이 `CPU_METRIC = "system_cpu_usage"` 로 정합화하고,
   ADR-006 에 "metric_name 은 임의 별칭이 아니라 MetricNormalizer 가 파일명에서 유도한 값"
   이라는 경고를 추가했다.
2. ~~**`modality_info` 가 missing 을 못 낸다**~~ — **해소** (`1bafca3`). `present` 를 반영해
   missing/empty/data 3상태를 완성했다. Code_Stop 국소화의 부재 신호가 이제 번들에 실린다.
3. **창 기반 detector 가 이미 번들로 보낸 구간을 다시 센다** — **detector 측 구현 완료, Runner 배선
   대기.** `evaluate(..., since=None)` 로 계약을 넓히고 `cpu_spike`·`restart_marker` 에 적용했다
   (테스트 7건). Runner 는 아직 스캐폴드라 `_detect_since` 필드와 배선 TODO 만 두었다.
   번들 종료 후 재발화해 내용이
   겹치는 번들을 또 보내는 것 자체는 **설계 의도**다(중복 허용, 쿨다운 불필요). 문제는
   `cpu_spike`·`restart_marker` 가 무상태라 매 틱 `observed_until − window_sec` 를 그대로
   되돌아본다는 점이다. 직전 번들이 어디까지 담았는지 모르므로 **이미 전송한 구간의 샘플을
   재차 카운트**한다.

   부작용: 재계산된 창에는 초과 샘플이 많이 쌓여 있어 `k번째 오래된 샘플`(= `trigger_time`)이
   watermark 보다 100초 이상 과거가 된다. 그러면 `pre = [anchor−180, anchor)` 가 보존
   구간(210초)을 벗어나 **앞부분이 경고 없이 빠진다** — 번들의 `window` 메타는 3분이라고
   적혀 있는데 내용은 1분뿐인 상태로 전송된다.

   **제안**: `evaluate()` 에 **평가 하한 `since`** 를 넘기고, 되돌아보기 시작점을 거기서 자른다.

   ```python
   def evaluate(self, new_batch, buffer, since: datetime | None = None) -> ...:
       start = new_batch.observed_until - timedelta(seconds=lookback)
       if since is not None:
           start = max(start, since)      # ← 변경점 전부
   ```

   그러면 번들 이후 데이터만으로 다시 세므로 "임계를 다시 넘으면 그 시점 앞뒤 3분" 이라는
   의도대로 동작하고, k번째 샘플이 곧 최신이라 anchor 가 현재 배치 안에 들어와 pre 유실도
   같이 사라진다.

   **`since` 는 판정에만 걸리고 페이로드에는 안 걸린다.** 번들 창
   `[anchor−180, anchor+180)` 은 `get_snapshot` 으로 버퍼에 있는 대로 전부 뜬다 —
   `SnapshotManager` 는 `since` 를 모른다. 잘린 구간의 데이터는 (a) 직전 번들에 이미 실려
   전송됐고 (b) 새 번들의 pre 가 되짚어 한 번 더 담는다(중복 허용). 실제 비용은 **발화 지연**뿐이다.

   경계는 반열림끼리 맞물린다 — 직전 번들이 `[…, window_end)` 로 `window_end` 를 제외하고,
   `since = window_end` 는 `get_snapshot` 의 `start <= ts` 로 포함된다. 중복도 누락도 없다.

   **소유는 Runner.** detector 는 "번들"이 아니라 시각 하나를 받으므로 무상태(ADR-006)가
   유지된다. Runner 가 `finalize_ready` 반환 시 `_detect_since = bundle.window.end` 로 갱신한다.
   세션이 열려 있는 동안(post 대기 3분)은 게이팅이 필요 없다 — `register_triggers` 가 재트리거를
   기존 세션에 흡수하므로 새 번들 자체가 안 생긴다. 두 장치가 시간축에서 겹치지 않는다.

   | 구간 | 재발화를 막는 장치 | 출처 |
   |---|---|---|
   | 트리거 ~ 번들 완성 | 단일 세션 슬롯 | 기존 코드 |
   | 번들 완성 이후 | `since` = 번들 창 끝 | 이 제안 |

   **한계 두 가지 (과대평가 금지)**

   - `since` 는 **번들 직후의 체계적 낡음**만 없앤다. 한동안 번들이 없던 상태에서는 `since` 가
     멀거나 `None` 이라 되돌아보기가 `window_sec` 전체로 열리고, 이벤트가 드문드문하면 anchor 가
     여전히 최대 `window_sec` 과거에 찍혀 pre 가 잘릴 수 있다. 그 잔여분까지 잡으려면 §9(anchor 를
     배치 경계로 통일)가 필요하다 — **§9 는 순수 선택이 아니다.**
   - 발화까지 `since` 로부터 **180초를 넘게** 걸리면 anchor 가 밀려 pre 가 `since` 까지 못 닿고,
     그 사이 구간은 어느 번들에도 안 들어간다. `cpu_spike` 는 15초 샘플 × 5개 = 최대 60초라
     안전하나, 이벤트가 드문 로그 기반 detector 에서는 가능하다. **기록만 하고 지금 손대지 않는다.**

   구현 비용: `evaluate()` 시그니처(계약 §2.4)에 기본값 `None` 파라미터 1개 추가(하위 호환),
   창 기반 detector 각 1줄, Runner 상태 1개. 버퍼·`SnapshotManager` 는 변경 없다.
4. ~~**trigger·snapshot 단위 테스트 부재**~~ — **해소** (`281f999`). `tests/trigger/` 8개 +
   `tests/snapshot/` 1개가 추가되어 전체 96 → 139 통과.

5. **`cpu_spike` 판정 규칙이 근거와 불일치** — **결정됨: 규칙 유지, ADR 서술만 정정**
   (2026-07-20, 유경). upstream 이 `metric_name` 은 고쳤으나 ADR-006 의 "baseline 3/79 **산발**"
   서술은 4곳 그대로다(§51·66·74·90). 실측상 판별력이 같으므로 코드는 건드리지 않고 ADR 문구만
   사실에 맞춘다. 아래 §8.

6. **`trigger_time` 의 의미가 어디에도 규정돼 있지 않다** — **미해결.** 아래 §9.

## §8. `cpu_spike` 판정 규칙 (결정: 코드 유지 · ADR 서술만 정정)

ADR-006 은 근거를 "plateau = 높은 샘플의 **연속** 누적, baseline 3/79 **산발** vs 주입 23/80 연속"
으로 적었으나, 구현은 창 안 **총 개수**(`len(over) >= min_over`)를 센다. 연속성을 보지 않으므로
서술과 규칙이 다르다. `833460a` 이 `metric_name` 은 정합화했으나 이 항목은 그대로다.

### 실측 (`system_cpu_usage.csv`, bar=50%, 창 210초=14샘플)

| 시나리오 | 샘플 | 간격 | >50% 총 | **최장 연속 런** | 창 내 최대 개수 | max |
|---|---|---|---|---|---|---|
| Perf CPU 주입 | 80 | 15s 고정 | 23 | **23** | 14 | 100.0 |
| Baseline | 79 | 15s 고정 | 3 | **3** | 3 | 81.3 |
| Svc_Kill | 79 | 15s 고정 | 3 | **3** | 3 | 79.6 |
| Code_Stop | 101 | 15s 고정 | 3 | **3** | 3 | 83.1 |

### 측정이 뒤집은 것

- **ADR-006 의 "baseline 3/79 산발" 은 사실이 아니다.** baseline 의 초과 3개는 최장 런도 3 —
  즉 **연속**이다. 실제 판별 축은 `산발 vs 연속` 이 아니라 **런 길이 3 vs 23** 이다.
- 그래서 규칙을 연속 런으로 바꿔도 **판별력은 현행과 같다**(baseline 3 vs 주입 23/14, 둘 다
  임계 5 로 안전). 이 데이터에서 놓치는 결함은 없다 — 고칠 실동작 결함이 아니라 **설계 정합성**
  문제다.
- 샘플 간격이 15초로 완전히 균일해 **누락이 없다** → 갭 허용 로직은 불필요, 순수 런으로 충분.

### 결정 (2026-07-20)

**규칙은 현행 유지**(창 내 총 개수 `len(over) >= min_over`), **ADR-006 의 서술만 정정**한다.
실측에서 개수 방식과 런 방식의 판별력이 같고(baseline 3 vs 주입 23/14, 둘 다 임계 5 로 안전),
고칠 실동작 결함이 없기 때문이다. 정정할 문구는 ADR-006 §51·66·74·90 의
"baseline 3/79 **산발**" → 실제는 **연속 런 3**, 판별 축은 `산발 vs 연속` 이 아니라 **런 길이 3 vs 23**.

아래 런 기반 규칙은 채택하지 않되, 향후 오발화가 관측되면 꺼내 쓸 대안으로 남긴다.

### 대안 규칙 (미채택 · 보류)

```
발화 조건: 창 내 최장 연속 초과 런 ≥ min_run
condition = {metric: "system_cpu_usage", bar: 50, min_run: 5}
```

근거: (a) ADR-006 이 스스로 밝힌 신호 특성(지속)과 규칙이 일치한다. (b) 산발 노이즈가 늘어도
런은 길어지지 않아 임계 여유가 유지된다 — 현행 개수 방식은 창 안 어디든 5개면 발화하므로
GC·측정 스파이크가 3.5분에 흩어져 5회만 나도 오발화한다. 지금 데이터에 그런 분포가 없을 뿐이다.

`min_run=5`(75초 지속) 는 baseline 최장 3 대비 여유 2. `metric` 값은 §7-1(이름 불일치)과 함께
정해야 한다.

부수 확인: baseline 최대 81.3% < 95% 이므로 "≥95 절대" 도 이 데이터에선 갈린다. 다만 단일
샘플 판정이라 여유가 14%p 뿐이고, 런 방식(3 vs 23)이 분리 폭에서 우월하다 — ADR-006 의
plateau 채택 결론 자체는 유지된다.

## §9. `trigger_time` 의 의미 (미해결)

`TriggerEvidence.trigger_time` 이 무엇을 가리키는지가 계약·ADR 어디에도 없다. 현재 구현은
detector 마다 다르게 채운다.

| detector | `trigger_time` | 성격 |
|---|---|---|
| `cpu_spike` | `min_over` 번째 오래된 초과 샘플의 timestamp | 창 안 과거 시점 |
| `svc_kill` (log) | `threshold` 번째 오래된 이벤트 시각 | 창 안 과거 시점 |

`SnapshotManager` 는 이 값을 그대로 anchor 로 써서 창을 `[anchor±180)` 로 잡는다. 즉
**"이상이 확증된 시각"** 과 **"창의 중심"** 이라는 두 역할을 한 필드가 겸한다. 어긋나면
번들 `window` 메타와 실제 내용이 불일치한다(§7-3).

선택지:

1. **역할 분리** — `trigger_time`(보고용, 정밀 시각)과 `anchor`(창 중심, 배치 경계)를 따로 둔다.
2. **배치 경계로 통일** — anchor = 발화 배치의 `observed_until`. 정밀 시각은 잃지만 번들이 6분
   원본을 통째로 실으므로 중앙 RCA 가 스스로 찾을 수 있다. §7-3 의 남은 낡음까지 해소된다.
3. **현행 유지 + 명문화** — "창 안에서 임계를 확증한 k번째 샘플의 시각" 이라고 계약에 적는다.

현 권고는 **2** — §7-3 의 `since` 자르기로 못 잡는 잔여 낡음을 이것이 덮는다. 다만 중앙 RCA 가
배치 구조를 전제해도 되는지 확인이 필요하다(협의 사항).
