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

여유는 각각 정확히 1 틱이다. 다음 경로로 조회가 한 사이클 밀리면 앞부분이 **로그 없이** 잘린다:

1. **모달리티별 `observed_until` 불일치** — assembler 는 느린 모달리티를 대기하지 않고 개별
   기준으로 판정한다. 반면 축출 watermark 는 버퍼 전체의 max 라, metric 이 앞서가면
   watermark 가 metric 기준으로 진행해 log 레코드를 먼저 버릴 수 있다.
2. **tick 드리프트** — `sleep(30)` + 처리 시간이라 실제 주기는 30초보다 길고 누적된다.

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
- ADR-001 §미결에 근거 추가: 버퍼 보존 = pre+post, pre 는 트리거 시점 즉시 캡처.
- Runner 배선(retention 주입)은 계획 02 와 동일하게 **범위 밖** — Runner 담당자에게 전달할 사항.
