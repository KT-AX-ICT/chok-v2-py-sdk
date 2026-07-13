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

## 미결

- 발화 시점 이벤트의 pre/post 귀속 규칙.
- post 수집 중 재트리거 처리(윈도 연장 vs 별도 번들).
