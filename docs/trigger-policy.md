# 트리거 정책

## baseline 편차 감지 (모달리티별)

기존 연구 코드의 임계 정책을 출발점으로 한다:

| 모달리티 | 신호 | 임계 (기본) |
|---|---|---|
| metric | `system_cpu_max` | ≥ 95 (절대) |
| log | 서비스별 error 라인 비율 | ≥ 2.0× baseline (baseline 0 이면 즉시 트리거) |
| trace | error span / dur_p95 비율 | error>0, 또는 dur_p95 ≥ 2.0× baseline |

## 상관 (correlation)

`canonical_service` 로 서비스명 정규화 후 모달리티 간 후보를 묶는다. `corroboration`(수렴 모달리티 수)
× 평균 severity = incident score.

## dispatch 판정

어느 한 모달리티라도 triggered → 스냅샷 번들 전송. 전무 → 관찰 지속(전송 없음).

## MVP 목표 시나리오 (SN, DB 에러 제외)

| 시나리오 | 실시간 주 신호 |
|---|---|
| Perf CPU Contention | metric cpu_max |
| Svc_Kill_Media | **재시작 마커 (kill–gap–resume, "Starting" 2회)** — 신규 detector 필요 |
| Code_Stop_Media | trace 5xx span, NginxThrift `Could not resolve host for client socket.` |

> ⚠️ `coverage_dir_missing`(연구 코드의 code_media 핵심 신호)은 실시간 관측 불가 → ADR-003 참조.
