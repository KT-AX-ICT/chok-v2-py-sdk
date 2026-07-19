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

버퍼 보존은 pre 윈도(210초)가 아니라 **pre + post(=390초)** 로 둔다. pre 는 트리거 시점에
`SnapshotManager.register_triggers` 가 즉시 복사하므로 안전하지만, post 는 `finalize_ready`
시점에 버퍼에서 꺼내므로 보존이 210초면 여유가 **정확히 1 tick(30초)** 뿐이다.
모달리티별 `observed_until` 불일치·tick 드리프트·재시도로 한 사이클만 밀려도 post 앞부분이
로그 없이 잘린다. 근거 타임라인은 [계획 04 §1](../plans/04-memory-buffer.md) 참조.

버퍼는 `retention_sec` 만 주입받고 pre/post 의미는 모른다 — 정책이 바뀌어도 버퍼는 불변.

## 미결

- 발화 시점 이벤트의 pre/post 귀속 규칙.
- post 수집 중 재트리거 처리(윈도 연장 vs 별도 번들).
