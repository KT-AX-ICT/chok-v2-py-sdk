# ADR-003 — 실시간 관측 불가 신호 처리

- 상태: 제안 (blocker)
- 날짜: 2026-07-13

## 맥락

기존 분석에서, 일부 결함의 핵심 근거는 **시나리오 종료 후에만** 확인 가능하다:

- `coverage_dir_missing` (Code_Stop_Media 의 대표 신호) — 서비스 커버리지 디렉터리 부재는 실행 종료
  시점 아티팩트.
- `summary.txt` 기반 서비스 부재 — 마지막 batch 에서만 감지.

아키텍처의 "실시간 30초 트리거" 와 충돌한다. 실시간 루프는 이 신호를 볼 수 없다.

## 결정 (방향)

실시간에 **관측 가능한 대체 신호**로 각 결함을 재정의한다:

| 결함 | 종료후 신호(연구) | 실시간 대체 신호(SDK) |
|---|---|---|
| Code_Stop_Media | coverage_dir_missing | trace 5xx span 급증, NginxThrift `TTransportException` 로그 |
| Svc_Kill_Media | (로그 error 0건 → 미감지) | **재시작 마커** kill–gap–resume, "Starting" 2회, trace death–resume gap |
| Perf CPU | — | metric cpu_max (이미 실시간 가능) |

## 결과/영향

- `trigger/detector.py` 는 coverage detector 를 실시간 파이프라인에서 **제외**.
- Svc_Kill 용 **신규 restart-marker detector** 가 필요 (연구 코드에 없음 — MVP blocker).
- 확정 전까지 detector 인터페이스/테스트를 고정할 수 없음.
