# trigger — ④ 트리거

버퍼의 정규화 이벤트를 입력받아 이상을 감지하고 낱개 근거(`TriggerEvidence`)를 낸다.
**수렴은 하지 않는다** — 여러 근거를 묶어 incident 로 판단하는 것은 중앙 RCA 몫이다.

- `detector.py` — `TriggerDetector` 추상 인터페이스 + 되돌아보기 시작점 계산.
- `base.py` — `NumericThresholdDetector`. 이번 배치의 대표값을 condition 임계와 비교(무상태).
- `models.py` — `TriggerEvidence`.
- `perf/` · `svc_kill/` · `code_stop/` — 시나리오별 모달리티 detector.

## 무상태 원칙 (ADR-006)

detector 는 카운터를 들지 않는다. 매 `evaluate` 마다 `buffer.get_snapshot` 으로 창을 다시 센다.
버퍼 내부 속성에는 손대지 않고 계약(`get_snapshot`)만 쓴다 (계약 §2.3).

창을 보는 detector는 `cpu_spike`(perf/metric)와 `restart_marker`(svc_kill/log) 둘뿐이다.
나머지는 이번 배치만 본다.

## `evaluate(new_batch, buffer, since=None)`

`since` 는 **평가 구간 하한**이다. 직전 번들이 담아 전송한 구간을 다시 세면 k번째 샘플
(= `trigger_time`)이 과거로 끌려가 `pre` 가 잘리므로, 창 기반 detector 는 되돌아보기 시작점을
여기서 자른다 — `_lookback_start()` 가 `max(anchor − window_sec, since)` 를 낸다.

- **포함 경계.** `get_snapshot` 이 `[start, end)` 라 직전 번들이 제외한 `window_end` 를 여기서
  집는다 → 중복도 누락도 없다.
- **판정에만 걸린다.** 번들 창 `[anchor±180)` 은 `SnapshotManager` 가 `since` 와 무관하게 뜬다.
  잘린 구간의 데이터는 직전 번들에 이미 실렸고, 새 번들의 pre 가 되짚어 한 번 더 담는다(중복 허용).
- **detector 는 이 값의 출처를 모른다.** 시각 하나를 받을 뿐이라 무상태가 유지된다.
  번들 이력을 아는 것은 조립자인 `Runner`(`_detect_since`)다.
- 배치만 보는 detector 는 되돌아보기가 없어 무시한다.

한계와 유도는 [계획 04 §7-3](../../../docs/plans/04-memory-buffer.md).

## 미확정

- `trigger_time` 의 의미 — "이상 확증 시각"과 "창 중심"을 한 필드가 겸한다.
  [계획 04 §9](../../../docs/plans/04-memory-buffer.md).
- `cpu_spike` 판정 규칙: 창 내 총 개수 유지로 결정, ADR-006 의 "산발" 서술만 정정 대상
  ([계획 04 §8](../../../docs/plans/04-memory-buffer.md)).
- baseline 출처(동봉 프로파일 vs 롤링 self-baseline) — ADR-002.
- 실시간 관측 불가 신호의 대체 정의 — ADR-003.

참고: [docs/trigger-policy.md](../../../docs/trigger-policy.md),
[ADR-006](../../../docs/decisions/ADR-006-trigger-detectors.md)
