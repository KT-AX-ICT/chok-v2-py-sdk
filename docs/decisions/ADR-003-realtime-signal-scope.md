# ADR-003 — 실시간 관측 불가 신호 처리

- 상태: 제안 (blocker)
- 날짜: 2026-07-13 (2026-07-16 실측 분석 반영 — 대체 신호·임계 갱신)

## 맥락

기존 분석에서, 일부 결함의 핵심 근거는 **시나리오 종료 후에만** 확인 가능하다:

- `coverage_dir_missing` (Code_Stop_Media 의 대표 신호) — 서비스 커버리지 디렉터리 부재는 실행 종료
  시점 아티팩트.
- `summary.txt` 기반 서비스 부재 — 마지막 batch 에서만 감지.

아키텍처의 "실시간 30초 트리거" 와 충돌한다. 실시간 루프는 이 신호를 볼 수 없다.

## 결정 (방향)

실시간에 **관측 가능한 대체 신호**로 각 결함을 재정의한다. 신호·임계는 SN 3종 실측 분석
(Anomod_note/SN오류정리, 옵시디언 — 저장소 외부) 기준:

| 결함 | 종료후 신호(연구) | 실시간 대체 신호(SDK, 실측) |
|---|---|---|
| Code_Stop_Media | coverage_dir_missing | NginxThrift `[error]` 로그(`Could not resolve host`, 익명) → **+38초 뒤** trace 500 span(`/post/compose`) + hung span(>10초). 실시간엔 죽은 서비스 특정 불가 — 국소화는 중앙 RCA 몫 |
| Svc_Kill_Media | (로그 error 0건 → 미감지) | **재시작 마커** — 같은 서비스 로그 `Starting` **2회째**(유일한 실시간 신호). trace gap 은 첫 재개 span 에서야 닫혀 사후 다운타임 표시용일 뿐 트리거 부적합. metric·5xx·latency 전부 무신호 |
| Perf CPU | — | metric host CPU **plateau** — 50% 초과 샘플의 연속 누적(절대 임계 1회 아님. baseline 도 max 81% 튐). trace latency(p50 ~1.8×)가 약 2분 뒤 확증하는 보조 신호 |

## 결과/영향

- `trigger/detector.py` 는 coverage detector 를 실시간 파이프라인에서 **제외**.
- Svc_Kill 용 **신규 restart-marker detector** 가 필요 (연구 코드에 없음 — MVP blocker).
- 확정 전까지 detector 인터페이스/테스트를 고정할 수 없음.
