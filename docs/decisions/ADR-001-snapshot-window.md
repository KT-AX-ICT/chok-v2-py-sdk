# ADR-001 — 스냅샷 pre/post 윈도 정의

- 상태: 제안
- 날짜: 2026-07-13

## 맥락

아키텍처 그림은 "3분 30초 버퍼 + pre-trigger + 3분 대기 + post-trigger" 를 명시하나, 정확한 경계가
모호하다.

## 결정 (잠정)

- 버퍼(pre) 윈도 = 210초(3분 30초). 트리거 직전 버퍼 전체를 `pre_events` 로 사용.
- post 수집 = 180초(3분). 발화 후 이 기간 이벤트를 `post_events` 로.
- 설정: `RCA_BUFFER_WINDOW_SEC`, `RCA_POST_TRIGGER_WAIT_SEC`.

## 버퍼 보존 기간 (계획 04 에서 확정)

버퍼 보존 = `PRE_SEC(180) + 루프 주기(30) = **210초**`.

pre 와 post 는 **시점이 다른 별개 질의**라 더해지지 않는다. `register_triggers` 는 트리거
시점에 pre `[T−180, T)` 를 즉시 복사하고, `finalize_ready` 는 `T+180` 도달 틱에 post
`[T, T+180)` 를 따로 뜬다. 각 질의에 필요한 보존이 모두 210 으로 수렴한다 —
유도표는 [계획 04 §1](../plans/04-memory-buffer.md).

여유는 각각 1 틱이다. 넓히려면 `retention_sec` 만 올린다(`PRE+POST` 로 부풀리지 않는다 —
그렇게 적어두면 다음 사람이 post 정책을 조절 레버로 착각한다).

버퍼는 `retention_sec` 만 주입받고 pre/post 의미는 모른다.

## 미결

- 발화 시점 이벤트의 pre/post 귀속 규칙.
- ~~post 수집 중 재트리거 처리(윈도 연장 vs 별도 번들)~~ — **해소.** `register_triggers` 가
  단일 세션 슬롯을 써서 post 대기 중 재트리거를 기존 세션에 흡수한다(anchor·창·pre 고정,
  `triggered_by` 만 누적). 윈도 연장은 하지 않는다.
- **번들 전송 이후의 재발화 기준** — 미해결. 창 기반 detector 가 이미 전송한 구간을 다시 세어
  anchor 가 과거로 끌려간다. 제안은 `evaluate(..., since=직전 번들 window_end)` 로 평가 하한을
  자르는 것 — [계획 04 §7-3](../plans/04-memory-buffer.md).
- **`trigger_time` 의 의미** — 미해결. "이상 확증 시각" 과 "창 중심" 을 한 필드가 겸한다.
  [계획 04 §9](../plans/04-memory-buffer.md).
