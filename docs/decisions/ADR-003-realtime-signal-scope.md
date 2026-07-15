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
| Code_Stop_Media | coverage_dir_missing | trace 5xx span 급증, NginxThrift `Could not resolve host for client socket.` 로그 |
| Svc_Kill_Media | (로그 error 0건 → 미감지) | **재시작 마커** kill–gap–resume, "Starting" 2회, trace death–resume gap |
| Perf CPU | — | metric cpu_max (이미 실시간 가능) |

### 신호 실재 검증 (2026-07-15)

위 표는 재정의 시점에 원본 데이터로 확인되지 않았다. SN 데이터셋에서 직접 측정한 결과:

| 결함 | 신호 | 실측 |
|---|---|---|
| Perf CPU | metric `system_cpu_max` ≥ 95 | **O** — `system_cpu_usage.csv` 최대 100.00 |
| Svc_Kill_Media | "Starting" 2회 | **O** — `MediaService_.log` `00:01:57.490`, `00:03:41.500` (간격 104초) |
| Code_Stop_Media | trace 5xx | **O** — `all_traces.csv` `http_status_code=500` 70건 / 전체 1595 |
| Code_Stop_Media | NginxThrift `TTransportException` | **X** — 0건 |

**`TTransportException` 정정.** 이 문자열은 `Code_Stop_MediaService` 가 아니라 **`Code_Stop_UserService`**
시나리오의 `NginxThrift_.log` 에 있다 (200건). 결함 대상 서비스에 따라 nginx 가 다르게 실패한다:

| 시나리오 | NginxThrift 에러 문구 | 건수 |
|---|---|---|
| `Code_Stop_MediaService` | `compost_post failure: Could not resolve host for client socket.` | 200 |
| `Code_Stop_UserService` | `thrift/Thrift.lua:37: TTransportException` | 200 |

MVP 대상은 `Code_Stop_MediaService` 이므로 표의 문구를 실측값으로 바꾼다. `TTransportException` 을 찾는
detector 는 MVP 데이터에서 **영구히 발화하지 않는다.**

주의 — `Perf_CPU_Contention` 과 `Svc_Kill_Media` 는 `NginxThrift_.log` 가 **0바이트**다. nginx 신호는
`Code_Stop_MediaService` 에서만 관측된다.

## 결과/영향

- `trigger/detector.py` 는 coverage detector 를 실시간 파이프라인에서 **제외**.
- Svc_Kill 용 **신규 restart-marker detector** 가 필요 (연구 코드에 없음 — MVP blocker).
- 확정 전까지 detector 인터페이스/테스트를 고정할 수 없음.
- nginx 로그 detector 는 `Could not resolve host for client socket.` 를 찾는다. 시나리오를
  `Code_Stop_UserService` 로 넓히면 `TTransportException` 도 함께 봐야 한다.
- `NginxThrift_.log` 는 boost 포맷이 아니라 nginx error_log 포맷(`%Y/%m/%d %H:%M:%S`)이다 — 로그 파서가
  별도로 필요하다.
