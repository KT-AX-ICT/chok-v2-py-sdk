# ADR-006 — 트리거 detector 설계

- 상태: 확정
- 날짜: 2026-07-18
- 관련: [ADR-003](ADR-003-realtime-signal-scope.md)(실시간 대체 신호), [ADR-001](ADR-001-snapshot-window.md)(스냅샷 윈도), [ADR-005](ADR-005-sdk-structure.md)(SDK 구조), interface-contract §2.4

## 맥락

`TriggerDetector.evaluate(new_batch, buffer) -> list[TriggerEvidence]` 계약 위에 MVP 3종 결함(Perf CPU / Svc_Kill / Code_Stop)을 실시간 감지하는 detector를 구현해야 한다. 감지 로직은 계약 이전 프로토타입(`perf_trigger_sim`, `observe(value, ts)`)으로 러프하게 검증했고, 이를 계약 인터페이스로 옮기며 detector 구성·발화 규칙·임계 주입 방식을 확정한다.

전제: SDK는 런타임에 **어느 시나리오가 재생 중인지 모른다**(ADR-004). 따라서 detector는 "시나리오별"이 아니라 **신호별**이며, 모든 detector가 동시에 돌고 무엇이 발화하는지로 시나리오가 사후에 드러난다.

## 결정

### detector 구성 — 9 슬롯 (실로직 6 + placeholder 3)

시나리오 × 모달리티 매트릭스로 두되, 실데이터상 신호가 있는 칸만 로직을 넣고 무신호 칸은 placeholder(`[]`)로 채운다.

| | metric | trace | log |
|---|---|---|---|
| **perf** | `cpu_spike` | `latency_spike` | `error_rate` |
| **svc_kill** | placeholder | placeholder | `restart_marker` |
| **code_stop** | placeholder | `trace_5xx` | `nginx_error` |

- **placeholder 근거:** svc_kill metric(cAdvisor가 같은 라벨로 즉시 재생성 → 시계열 안 끊김), svc_kill trace(gap의 끝만 보여 실시간 트리거 불가), code_stop metric(죽은 컨테이너 목록 잔존)은 이 데이터셋에 실시간 신호가 없다. 억지 모델링 대신 `[]` 반환.

### 발화 규칙 — 두 종류

1. **숫자 임계 (5개, `NumericThresholdDetector` 공통 base):** 이번 배치에서 대표값을 뽑아 `value > max(baseline*ratio, floor)`이면 발화. 무상태.
   - `cpu_spike`: cpu 지표(`container_cpu`/`system_cpu_usage`) 최댓값
   - `latency_spike`: span `duration_ms` 최댓값
   - `error_rate`: `level=="error"` 로그 건수
   - `trace_5xx`: `http_status_code==500` span 건수 (500만, hung 제외)
   - `nginx_error`: nginx의 `event_type=="connection_error"` 로그 건수
2. **최근 창 카운트 (`restart_marker`, `cpu_spike`):** `buffer.get_snapshot(observed_until - lookback, observed_until)`로 최근 창을 조회해 카운트한다. `lookback`은 **detector의 `condition["window_sec"]`(기본 210초)** — buffer 내부 속성이 아니라 detector 설정에서 온다(계약 §2.3의 `get_snapshot`만 사용). restart_marker는 `service_start`를 서비스별로 세어 `>= threshold(2)`면, cpu_spike는 `system_cpu_usage > bar`를 세어 `>= min_over`면 발화. 무상태(매 평가마다 창 재계산).

### 핵심 원칙

- **임계값은 코드에 하드코딩하지 않고 `condition` dict로 주입**(계약 §0-5). 프로토타입 상수를 이월하지 않는다. 실제 값은 실데이터 분포로 도출(후속).
- **MVP는 무상태 배치 비교** — 연속 N회(지속성) 판정은 제외. 매 30초 배치를 baseline 기반 임계와 비교.
- **`TriggerEvidence.baseline`은 condition의 정적값** — 정상구간 재산출 안 함.
- **창 조회는 계약대로만** — 되돌아볼 창(`lookback`)은 detector `condition["window_sec"]`에서 주입하고, buffer는 계약 §2.3의 `get_snapshot(start, end)`로만 조회한다. `buffer.window_sec` 같은 내부 속성에 의존하지 않는다(cpu_spike·restart_marker 공통).
- 신호 추출은 **정규화 필드로만**(`metric_name`/`duration_ms`/`http_status_code`/`level`/`event_type`/`canonical_service`), union 레코드는 `isinstance`로 좁힘.
- 엣지는 **낱개 근거(evidence)만** emit. 모달리티 수렴·죽은 서비스 국소화는 중앙 RCA(§0-4).

### cpu_spike 판정 기준 변경 — 절대 임계(≥95) → plateau(지속)

초기 정책은 `system_cpu_usage ≥ 95 절대값 1회 초과 시 발화`였으나, AnoMod SN 3종 실측 분석 후 **host CPU plateau(지속)** 기준으로 변경한다.

**실측 근거 (AnoMod SN, `SN오류정리` — 저장소 외부 옵시디언):**
- baseline CPU도 순간 **max 81%**까지 튄다 → 단일 샘플 절대값 판정은 산발 노이즈에 취약(측정 스파이크·GC 등으로 순간 고점 발생 가능).
- 결함 신호의 특징은 **봉우리가 아니라 plateau**(높은 샘플의 연속 누적): baseline **3/79 산발** vs 주입 **23/80 연속**. 주입 후 약 1분이면 50% 초과 샘플이 5개 이상 연속 누적, 최대 99%.

**판정 방식:**
- 대상 = host CPU(`system_cpu_usage`). 샘플 "높음" 기준선(예: 50%) 초과 샘플의 **연속 누적 수·지속시간**으로 판정. 절대값 1회 초과가 아니다.
- "50%"는 발화선이 아니라 **샘플을 '높음'으로 분류하는 기준선**이며, 실제 발화 판정은 그 위에서의 **연속 누적**이다.

**세 판정 옵션 비교** (bar = 샘플을 '높음'으로 치는 기준선, 지속 = 발화까지 필요한 높은 샘플 수):

| 옵션 | bar | 지속 | 구현 | 특성 |
|---|---|---|---|---|
| **≥95 절대** | 95% | 1개(봉우리) | 현행 코드 그대로(무상태 단일배치) | 단순. 단일 튐 오탐·약한 지속 결함(계속 85%) 놓침 |
| **plateau** | 50% | N개 누적 | 윈도 로직 필요 | 실측 지지. 단일 튐·약한 결함 다 대응. 정상 고부하엔 오탐 여지 |
| **sustained ≥95** | 90~95% | N개 | 윈도 로직 필요 | 절충. 단일 튐·정상 고부하 둘 다 방어. bar 높으면 약한 결함 놓칠 수 |

- 이 시스템 baseline은 **3~10%**라 "50%"는 낮은 값이 아니라 정상의 5~15배 = 명백한 이상. 그래서 실측(baseline 3/79 산발 vs 주입 23/80 연속)이 plateau·bar50을 지지한다.

**"윈도 로직"이란:** 이번 배치 하나가 아니라 `buffer.get_snapshot(observed_until - lookback, observed_until)`로 **최근 창의 샘플들을 되돌아봐** "높음(>bar)" 샘플 수를 센다(`lookback` = condition `window_sec`). `restart_marker`가 부팅 마커를 세는 방식과 **동형**이고, detector는 카운터를 들지 않고 매 평가마다 buffer로 재계산하므로 **무상태 유지**. **구현 완료** — cpu_spike는 이 방식으로 전환됨. 계약의 `get_snapshot`만 쓰고 buffer 내부 속성엔 의존하지 않는다.

**구현 함의 (현행 코드와의 간극):**
- 현재 `cpu_spike`는 **단일 배치 `max(cpu) > threshold` 무상태**로, plateau를 아직 구현하지 않았다(MVP에서 "연속 지속성 판정"을 제외했기 때문).
- **≥95 절대** 채택 시 → 코드 변경 0, `condition={"baseline":0, "floor":95}` 주입만으로 즉시 동작(임계를 코드에 안 박은 덕).
- **plateau / sustained** 채택 시 → cpu_spike를 위 윈도 로직으로 전환(restart_marker 동형). condition에 `sample_bar`·`min_over` 주입. **plateau와 sustained는 같은 코드, `bar`·`count` 파라미터만 다르다** — 하나 만들면 condition으로 전환 가능.
- **확정: plateau 채택** (실데이터 근거 — Perf CPU 분석: median/단일절대 판별 불가, baseline `3/79` 산발 vs 주입 `23/80` 연속). ≥95 절대·sustained는 미채택. → **cpu_spike를 윈도 로직으로 구현**: `system_cpu_usage`(호스트) 샘플 중 `bar`(기본 50%) 초과가 buffer 윈도에서 `min_over`(기본 5)개 이상이면 발화. `container_cpu`는 국소화용이라 트리거 대상 아님.

### 방어 코드 (Codex 검토 반영)

- `nginx_error`: `canonical_service=="nginx"` 필터를 더해, nginx 외 서비스의 connection_error를 nginx로 오집계하지 않도록.
- `restart_marker`: `threshold = max(1, ...)`로 음수/0 주입 시 오발화·IndexError 방어.

## 결과/영향

- 파일 구조: `trigger/base.py` + `trigger/{perf,svc_kill,code_stop}/{metric,trace,log}.py`. 서브패키지 `__init__.py`는 docstring만(미완성 모듈 import로 인한 수집 실패 방지).
- 러너는 9개를 모두 등록해 30초 루프에서 동시 평가한다. detector 파일의 시나리오 구분은 코드 조직일 뿐 런타임 라벨이 아니다.
- 검증: 단위 30 + 실데이터 4 = 40 테스트 통과, `ruff`·`mypy` 클린. 실데이터(`datasets/sn/`)로 cpu_spike/trace_5xx/nginx_error/restart_marker 발화 확인. (테스트 파일은 이번 커밋 범위에서 제외.)

## 미결

- **실 임계값 도출 (실측 근거 확보, 배선은 러너 때)** — 각 detector의 `condition`을 실데이터 분포로 도출함:
  - `cpu_spike`(plateau): `{metric:"system_cpu_usage", bar:50, min_over:5}` — baseline 3/80 산발 vs 주입 23/80 연속.
  - `trace_5xx`: `{baseline:0, floor:1~3}` — 500 span baseline 0, Code_Stop 70~98건.
  - `nginx_error`: `{baseline:0, floor:3~5}` — connection_error baseline 0, ~11/분(≈5.5/30s).
  - `restart_marker`: `{threshold:2}` — 정상 부팅 1, kill 2. (이미 구현 일치)
  - `error_rate`(perf): perf log는 duplicate-key(j1) **artifact라 무신호** — threshold를 baseline 아티팩트율(~5/30s) 위로 둬 거의 침묵.
  - `latency_spike`(확증): OUT p50 11.6 → IN 21.3ms. floor~20ms 또는 ratio~1.8. 전체창 희석 주의.
  - 값 확정 완료, config·러너 주입은 러너 단계.
  - ⚠️ **`metric_name` 은 임의 별칭이 아니라 `MetricNormalizer` 가 파일명에서 기계적으로 유도한 값**이다
    (`socialnet_` 접두어만 제거: `system_cpu_usage.csv` → `system_cpu_usage`, `socialnet_container_cpu.csv` → `container_cpu`).
    리플레이어가 원본 파일명을 그대로 `var/` 에 쓰므로 실운용에서도 동일하다. detector 는 이 값과 `==` 정확일치로 비교하며,
    어긋나면 예외도 로그도 없이 조용히 0건이 되어 "CPU 정상"과 구분되지 않는다
    (실제로 `system_cpu` 로 적혀 있어 cpu_spike 가 무발화였다 — 2026-07-20 수정).
- **`restart_marker` 윈도 경계 — 수용(MVP 확정)** — 두 부팅이 210초를 넘게 벌어지면 못 잡는다. MVP는 이 한계를 **수용하고 현행(단순 윈도 카운트) 그대로 간다.** 반열림 `[start, end)`라 `observed_until`에 정확히 걸친 마커는 다음 배치에서 집계. (개선 필요 시 후속에서 윈도 확장·상태 추적 검토.)
- **번들 payload 상한** — 실데이터상 6분 윈도에 전 서비스 로그가 수십만 줄. 샘플링/상한/서비스 필터 필요.
- **러너 통합 전제** — `append → evaluate` 순서(restart_marker가 buffer 윈도에 의존).
