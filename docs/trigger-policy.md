# 트리거 정책

실측 근거: AnoMod SN 3종 시나리오 분석 (Anomod_note/SN오류정리, 옵시디언 — 저장소 외부).
각 detector 는 자기 트리거 조건(threshold)을 직접 들고 있으며, 정상구간 baseline 산출은 하지 않는다
(ADR-005). 수렴(correlation)도 엣지에서 하지 않는다 — 낱개 근거(TriggerEvidence)만 전송한다.

## 실시간 detector 3종 (ADR-003)

| detector | 모달리티 | 신호 | 판정 기준 (실측) |
|---|---|---|---|
| `cpu_spike` | metric | host CPU(`system_cpu_usage`) plateau | **50% 초과 샘플의 연속 누적**. 절대값 1회 초과가 아니라 초과 샘플 수·지속시간으로 판정한다 (baseline 3/79 산발 노이즈 vs 주입 23/80 연속 plateau, baseline 도 max 81% 까지 튐). 주입 후 약 1분이면 99% 초과 샘플 5개 이상 쌓임 |
| `restart_marker` | log | 서비스 로그 `Starting … server` 마커 | 같은 서비스에서 **2회째 관측** = 죽었다 재기동(kill–resume) 확증. Svc_Kill 의 유일한 실시간 신호 (직전 error/fatal 0건이면 외부 강제종료) |
| `trace_5xx` | trace | http 5xx span | **500 span 발생 즉시** (실측: 전부 nginx `/post/compose`, 빠른 실패 13~78ms). 보조 확증: hung span(`duration_us` > 10초 — 분포가 <0.1s 와 >10s 로 갈려 10초 컷이 빈 골짜기), NginxThrift `[error]` 로그(trace 500 을 ~38초 선행) |

## 모달리티별 실측 반응 (SN 3종)

| 시나리오 | metric | log | trace |
|---|---|---|---|
| Perf_CPU_Contention | ✅ plateau (선행 트리거) | ❌ 무신호 | 🟡 latency p50 ~1.8× (약 2분 뒤 확증), 5xx·error 0 |
| Svc_Kill_Media | ❌ (컨테이너 시계열 연속·리셋 없음) | ✅ `Starting` 2회 (유일) | ❌ (gap 은 첫 재개 span 에서야 확인 — 사후) |
| Code_Stop_Media | ❌ (죽은 컨테이너 잔존) | ✅ nginx `[error]` 분당 ~11건 (선행) | ✅ 500 span + hung span |

세 시나리오 모두 **3개 모달리티 동시 감지는 성립하지 않는다** — 시나리오마다 점화하는 축이 다르다.
그래서 어느 한 detector 의 evidence 만으로도 dispatch 한다.

## 판정 시 주의 (실측 함정)

- **평균/중앙값으로는 못 잡는다** — CPU 결함도 median 은 baseline 과 동일(3.9% vs 3.6%).
  결함은 "전체적으로 조금 높음"이 아니라 "일부 구간이 확 튀어 지속됨"이라 초과 이벤트의 개수·길이로 판정한다.
- **로그 error 건수는 트리거가 아니다** — userservice duplicate-key(j1 테스트 계정) 등 워크로드
  아티팩트가 baseline 에도 동일하게 존재한다.
- **API 성공률·상태코드도 오염** — 400/404 는 워크로드 아티팩트, baseline 과 동일 분포.
- **죽은 서비스 특정(국소화)은 실시간 보장 안 됨** — Code_Stop 의 nginx 에러는 익명
  (`Could not resolve host`). nginx 가 직접 부르는 서비스(user-service)만 이름이 찍힌다.
  국소화는 중앙 RCA 가 번들의 부재 신호(`modality_info` missing/empty)와 함께 판정한다.

## dispatch 판정

어느 detector 든 `TriggerEvidence` 를 내면 → 스냅샷 세션 개시(anchor ±3분, ADR-001) → 번들 전송.
전무 → 관찰 지속(전송 없음).
