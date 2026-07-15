# 계획 01 — 리플레이어

`datasets/sn` 의 SN 원본을 타임시프트 재생해 `var/` 로 원천 로그를 만들어내는 Python 리플레이어.
계약은 [ADR-004](../decisions/ADR-004-replayer-data-layout.md).

각 Phase 는 새 세션에서 독립 실행 가능하도록 자체 문서 참조를 갖는다. Phase 0 은 이미 실행됐고,
아래 "확인된 사실"이 그 산출물이다 — **추측 대신 이 표를 근거로 구현한다.**

---

## Phase 0 — 확인된 사실 (실행 완료)

모두 실제 파일을 열어 확인했다. 출처 없는 항목은 넣지 않았다.

### 0-1. 리플레이어 출력은 정규화 **이전** 원본이다

근거가 독립적으로 4개 수렴한다:

| 근거 | 출처 |
|---|---|
| "둘 다 정규화 이전이라…" | `ADR-004:9` |
| "원시 레코드를 산출한다. 산출물은 아직 정규화 이전" + `poll() -> Iterator[dict[str, Any]]` | `collectors/base.py:13-21` |
| 파이프라인 순서 `collectors.poll → normalization → buffer.add` | `runtime/runner.py:5` |
| `raw_ref` 가 `var/` 의 파일:라인을 가리킨다 — `var/` 가 `NormalizedEvent` 면 자기 자신을 "정규화 이전 원본"으로 참조하는 순환 | `ADR-004:106` + `schemas/events.py:33-34` |

**즉 `NormalizedEvent` 를 import 하지 않는다.** 출력은 줄 단위 JSONL 컨테이너 + 모달리티 고유 원본 필드.

### 0-2. 원본 형태 — 출력과 모양이 다르다. 핵심 작업은 "재생"이 아니라 **피벗**이다

| 모달리티 | 원본 실제 형태 | 서비스 출처 | 필요한 변환 |
|---|---|---|---|
| log | `<Service>_.log` 평문, 서비스별 분리됨 | **파일명** (`MediaService_.log`) | 파싱 → JSONL |
| metric | **메트릭 종류별** CSV 15개 | **컬럼값** (`container_label_com_docker_compose_service`) | 서비스 기준 **재분할** |
| trace | `all_traces.csv` **단일 파일** | **컬럼값** (`service`) | 서비스 기준 **재분할** |

### 0-3. 포맷 실측

| 항목 | 값 | 출처 |
|---|---|---|
| log 타임스탬프 | `[%Y-%b-%d %H:%M:%S.%f]` — 월이 영문 약어(`Nov`), C 로케일 필요. **마이크로초가 없는 변형 존재** (아래 함정 11) | `log_data/Perf_CPU_*/UserService_.log:1` |
| log 라인 정규식 | `^\[(?P<ts>[^\]]+)\] <(?P<level>\w+)>: \((?P<src>[^:]+):(?P<srcline>\d+):(?P<func>[^)]+)\) (?P<msg>.*)$` | 위 파일 (비정형 라인 0건 확인) |
| log 레벨 | `<info>` / `<error>` 2종만 실측. `<warning>` 미출현 | `UserService_.log` (info 153023, error 200) |
| metric 타임스탬프 | `%Y-%m-%d %H:%M:%S` (초 단위, 15초 간격 스크레이프) | `socialnet_container_cpu.csv:2` |
| metric 공통 컬럼 | `timestamp,value,metric` + 파일마다 다른 레이블 컬럼 | `socialnet_container_cpu.csv:1` |
| trace CSV 헤더 | `trace_id,span_id,parent_span_id,service,operation,start_time,duration_us,http_status_code,http_method,http_url,component,tags,logs` | `all_traces.csv:1` |
| trace 타임스탬프 | `%Y-%m-%d %H:%M:%S.%f`, **UTC** (2098건 전수 대조로 확정) | `all_traces.csv` |

단 log/metric 은 타임존 표기가 물리적으로 없다 → **UTC 로 명시 해석**한다. naive 로 두면 실행 환경에 따라 어긋난다.

### 0-3'. 시간축 정렬 실측 — 종료는 맞고 시작은 다르다

3종 × 3모달리티 전수 측정:

| 시나리오 | log | metric | trace | 시작 편차 | 종료 편차 |
|---|---|---|---|---|---|
| cpu | 22:26:39–22:46:39 | 22:26:53–22:46:55 | 22:28:45–22:46:39 | **126s** | 16s |
| kill_media | 00:01:50–00:21:37 | 00:02:07–00:21:54 | 00:04:49–00:21:37 | **179s** | 17s |
| code_media | 02:56:21–03:21:34 | 02:56:34–03:21:50 | 02:59:03–03:21:34 | **162s** | 15s |

**종료가 15~17초로 맞는 것이 핵심 근거다** — 세 모달리티가 같은 절대시각축을 공유한다. 어느 하나가
로컬타임(KST)이었다면 9시간 어긋났을 것이다.

**trace 만 2~3분 늦게 시작하는 것은 데이터의 사실이지 오류가 아니다.** 트레이스는 20% 확률 샘플이라
(함정 7) 초반 트래픽이 희박하면 첫 샘플이 늦게 잡힌다.

→ **이것이 "모달리티 전체에 같은 t0" 규칙의 근거다** (Phase 3). 같은 t0 를 쓰면 원본의 상대관계가
그대로 보존된다. 모달리티별 t0 를 쓰면 trace 가 126~179초 앞당겨지면서 **원본에 없던 정렬이 생긴다** —
그것이 왜곡이다.

### 0-4. 함정 (전부 실측 확인)

1. **로그 파서가 2종 필요하다.** `NginxThrift_.log` 는 boost 가 아니라 nginx error_log 포맷이다:
   `2025/11/04 02:58:25 [error] 9#9: *816 [lua] compose.lua:62: ...` → `%Y/%m/%d %H:%M:%S`, 대괄호 없음.
   단일 파서 가정 시 Code_Stop 의 nginx 신호 200행을 **전량 유실**한다.
2. **시나리오마다 파일 구성이 다르다.** Code_Stop 은 `MediaService_.log` **자체가 없다**(서비스가 죽어서).
   Perf_CPU / Svc_Kill 은 `NginxThrift_.log` 가 **0바이트**다. 파일 존재를 가정하면 안 된다.
3. **서비스명 표기가 모달리티마다 다르다.** log=`MediaService`(Pascal), metric=`media-service`(kebab),
   trace=`media-service`(kebab). 파일명 통일에 매핑이 필요하다.
4. **metric 라벨 31개에 서비스가 아닌 것이 섞여 있다** — `cadvisor`, `prometheus`, `node-exporter`,
   `*-redis`, `*-mongodb`. 필터 필요.
5. **metric 은 `socialnet_container_*.csv` 만 서비스 귀인이 된다.** `system_*.csv` 는 호스트 집계라
   `instance=node-exporter:9100` 단일값 — 서비스 구분이 없다.
6. **`summary.txt` / `metadata.txt` 를 파싱하지 마라.** `Collection_Timestamp` 가 빈 값이고,
   `Duration_Hours: 24` 는 실제(약 20분)와 다르며, `summary.txt` 는 필드에 개행이 섞여 깨져 있다.
7. **트레이스는 20% 확률 샘플이다** (`sampler.param: 0.2`). 절대 카운트를 로그/메트릭과 직접 비교 불가.
8. **`all_traces.csv` 는 시간순 정렬이 아니다** (Perf_CPU: 첫 행 22:43:20 ≠ 실제 min 22:28:45).
   첫 행을 t0 으로 쓰면 안 된다.
9. **폴더명 시작 시각보다 데이터가 늦게 시작한다** (Code_Stop: 폴더 02:48:19 vs 데이터 02:56:21, 8분 갭).
   **t0 은 데이터 실측 min 을 쓴다.**
10. **트레이스는 CSV 만 읽으면 된다.** `all_traces.json` 은 CSV 대비 추가 정보가 없고(2098건 전수 대조),
    CSV 가 이미 `processes` 룩업과 `references[0]` → parent 추출을 끝내뒀다.
11. **로그 타임스탬프에 마이크로초가 없는 변형이 있다.** `[2025-Nov-03 22:28:07]` — `.%f` 없음.
    `SocialGraphService_.log` 1건, `UserService_.log` 1건 (Perf_CPU 기준). 마이크로초가 정확히 0 이라
    boost 가 생략한 것으로 보인다. **딱 2건이지만 파서가 죽으면 재생이 통째로 멈춘다.**

### 0-5. ADR-003 신호 실재 검증 (직접 확인)

ADR-003 이 정의한 실시간 신호가 커밋된 167MB 안에 실제로 있는지 확인했다. **문서에 검증 기록이 없어
직접 측정했다.**

| 시나리오 | ADR-003 요구 신호 | 실재 | 실측 |
|---|---|---|---|
| Perf_CPU | metric `system_cpu_max` ≥ 95 | **O** | 최대 **100.00** — 임계 통과 |
| Svc_Kill_Media | 재시작 마커 "Starting" 2회 | **O** | `00:01:57.490`, `00:03:41.500` |
| Code_Stop_Media | trace 5xx 급증 | **O** | 500 스팬 **70건** / 전체 1595 |
| Code_Stop_Media | NginxThrift `TTransportException` | **X — 0건** | 실제 문구는 `compost_post failure: Could not resolve host for client socket.` (200건) |

**`TTransportException` 은 데이터에 있다 — 다른 시나리오에.** `Code_Stop_MediaService` 가 아니라
**`Code_Stop_UserService`** 의 `NginxThrift_.log` 에 200건 있다 (MVP 3종 밖이라 커밋 범위 밖). 결함 대상
서비스에 따라 nginx 가 다르게 실패한다 — media-service 를 죽이면 호스트 해석 실패, user-service 를
죽이면 thrift 전송 예외. **ADR-003 이 UserService 시나리오의 신호를 MediaService 행에 적어둔 것이다.**

→ **처리 완료.** 브랜치 `fix/adr-003-code-media-signal` (커밋 `8d65257`) 에서 ADR-003 과
`docs/trigger-policy.md` 의 문구를 실측값으로 정정하고 위 측정치를 근거로 남겼다. 이 계획의 Phase 1-1 은
그 PR 이 머지되면 닫힌다.

나머지 3개 신호는 실재하므로 데모 3종은 성립한다.

### 0-6. pre/post 윈도 실측 — ADR-001 의 210초를 채울 수 없다

| 시나리오 | 데이터 시작 | 결함 시점 | pre 가용 | post 가용 |
|---|---|---|---|---|
| Svc_Kill_Media | 00:01:54 | 00:03:41 (재시작) | **107s** | 1076s |
| Code_Stop_Media | 02:56:21 | 02:58:25 (첫 error) | **124s** | 1389s |

ADR-001 요구는 pre 210s / post 180s. **post 는 넉넉하나 pre 는 3종 중 2종이 절반에도 못 미친다.**
버그가 아니라 데이터의 한계다 — 번들의 `pre_events` 가 짧아질 뿐 파이프라인은 돈다. 다만 "210초 버퍼"를
전제한 테스트를 쓰면 실패한다.

### 0-7. 따라야 할 기존 규약

| 필요한 것 | 복사할 위치 |
|---|---|
| argparse CLI 뼈대 (`build_parser()` 분리 + `main(argv) -> int`) | `src/rca_sdk/cli.py:11-28` |
| console script 등록 | `pyproject.toml:27-28` |
| settings 주입 (`settings or load_settings()`) | `src/rca_sdk/runtime/runner.py:17-19` |
| Settings 필드 추가 (env_prefix `RCA_`) | `src/rca_sdk/config.py:9-28` |
| 테스트 스타일 (평면 `def test_*`, 한국어 주석, 고정 datetime) | `tests/test_smoke.py:18-45` |
| 모듈 헤더 (한국어 docstring + `from __future__ import annotations`) | 모든 `src/rca_sdk/**/*.py:1-3` |

린트: ruff `line-length=100`, `select=["E","F","I","UP","B"]`, py311. CI 는 `ruff check .` → `pytest`.
mypy 는 설정만 있고 CI 미실행.

### 0-8. 존재하지 않는 것 — 지어내지 마라

- `AnoMod/analysis/sn_db/loaders.py` — `data-schema.md:20` 이 참조하나 **이 저장소에 없다.**
- `normalize_log/metric/trace` — 전부 `raise NotImplementedError` 스캐폴드다. 호출하지 마라.
- `Runner.tick()` — `NotImplementedError`. 리플레이어는 Runner 에 의존하지 않는다.
- `make_event` 픽스처 — `NormalizedEvent` 레벨이라 리플레이어 테스트에 **쓸 수 없다**.

---

## Phase 1 — 선행 결정 (코드 없음)

구현 전에 막힌 것을 푼다. 문서가 답하지 않아 Phase 0 이 공백으로 남긴 것들이다.

### 1-1. ADR-003 정정 — **완료 (머지 대기)**

브랜치 `fix/adr-003-code-media-signal` / 커밋 `8d65257`. Code_Stop 의 nginx 신호를
`Could not resolve host for client socket.` 로 정정하고, `TTransportException` 의 실제 위치
(`Code_Stop_UserService`)와 4개 신호 측정치를 근거로 남겼다. `docs/trigger-policy.md` 의 중복 표도 함께.

**먼저 한 이유**: 리플레이어가 nginx 로그를 재생하도록 만들어놓고 detector 가 없는 문자열을 찾으면
데모가 안 도는데, 원인이 리플레이어인지 detector 인지 데이터인지 구분되지 않는다.

**남은 것**: 그 PR 머지 후 이 브랜치를 리베이스한다.

### 1-2. 결정할 것

| # | 질문 | 선택지 | 권장 |
|---|---|---|---|
| D1 | `var/<service>.jsonl` 의 service 표기형 | `MediaService` (log 원본) / `media-service` (metric·trace 원본) | **`media-service`** — 정확성엔 영향 없다(아래). 3종 중 2종이 이미 그 표기라 log 만 매핑하면 되고, 디스크에서 일관되게 보인다 |
| D1' | **metric 라벨 31개 중 무엇을 서비스로 볼 것인가** | 로그 파일이 있는 11~12개만 / `-service` 접미어만 / 전부 | 결정 필요 — 이쪽이 실질적이다 (아래) |
| D2 | 배속 기준 시계 | 벽시계 / 이벤트 타임스탬프 | **벽시계로 결정됨** (2026-07-15). 이벤트 타임스탬프 기준이면 30초 루프 주기가 제멋대로가 된다. 단 아래 1-3 의 부작용이 따라온다 |
| D3 | 리플레이어 스크립트 이름·모듈 경로 | — | **`rca-replay` = `rca_sdk.replay.cli:main`** — 기존 `rca-collect` 와 대칭 |
| D4 | JSONL 한 줄의 필드 집합 | — | Phase 2 에서 모달리티별로 확정하고 `docs/data-schema.md:20` 의 TODO 를 닫는다 |

**D1 은 정확성 문제가 아니다.** `trigger/correlation.py:14-20` 을 읽어보면 두 표기가 같은 값으로 수렴한다:

```python
s = re.sub(r"[^a-z0-9]", "", name.lower())   # "MediaService"  → "mediaservice"
s = re.sub(r"service$", "", s)                # "media-service" → "mediaservice" → "media"
```

`var/log/MediaService.jsonl` 과 `var/metric/media-service.jsonl` 이 파일명은 달라도 correlation 은 정상
동작한다. 일관성 문제일 뿐이니 `media-service` 로 통일하고 넘어간다.

**D1' 이 실질적 결정이다.** metric 의 `container_label_com_docker_compose_service` 값 31개에 서비스가
아닌 것이 섞여 있다 (함정 4):

```
media-service, social-graph-service, user-service ...    ← 서비스
cadvisor, prometheus, node-exporter, jaeger-agent         ← 인프라
user-mongodb, social-graph-redis, ...                     ← 데이터스토어
```

`cadvisor` 는 `canonical_service()` 를 통과해도 `cadvisor` 로 남아 **자기 자신이 하나의 서비스가 된다.**
31개를 다 쓰면 `var/metric/` 에 파일이 31개 생기고 그중 상당수가 트리거 후보로 올라온다.

### 1-3. 배속 기능은 **범위에서 제외**한다 (2026-07-15 결정)

당초 요구사항은 1x/5x/10x 였으나 제외한다. 근거:

**타임스탬프 압축이 불가피하다.** 재생 시 타임스탬프를 `T0 + (orig - t0)/speed` 로 쓸 수밖에 없다.
`/speed` 를 안 하면(간격 보존) 타임스탬프가 벽시계보다 미래로 달려나가 스냅샷의
`window_start`/`window_end` 가 미래를 가리킨다. 그런데 `/speed` 를 하면 **간격이 배속만큼 줄어든다** —
Svc_Kill 의 "Starting" 2회 간격이 1x 에서 104초, 10x 에서 10.4초다.

**그러면 detector 가 배속을 알아야 한다.** 재시작 마커를 "약 100초 갭"으로 튜닝하면 10x 에서 10.4초 갭을
못 잡는다. 그런데 `ADR-004:109-111` 은 "SDK 는 지금 무엇이 재생 중인지 알 필요가 없다"고 결정했다.
배속을 알려주면 그 결정이 깨진다.

**그리고 어느 쪽이든 30초 루프가 결함을 놓친다.** 10x 면 결함이 재생 시작 11~12초에 발생하는데
`loop_interval_sec=30` 이라 첫 tick 전에 지나간다.

### 1-3'. 대신 **재생 종료 조건**으로 데모 길이를 줄인다

배속이 풀려던 문제는 "20~25분 재생을 데모에서 다 볼 수 없다"였다. 이건 **끊는 것으로 해결된다** —
시계도 detector 도 건드리지 않는다.

실측: 세 시나리오의 결함이 105~124초에 오고, `post_trigger_wait` 180초를 더하면 **5분이면 끝난다.**

| 시나리오 | 결함 시점 | 필요 길이 | 전체 재생 시 |
|---|---|---|---|
| cpu | +105s (`system_cpu_usage` 첫 95 돌파, 19/80 샘플이 95 이상) | **285s** | 1200s |
| kill_media | +107s ("Starting" 2회차) | **287s** | 1187s |
| code_media | +124s (첫 error / nginx) | **304s** | 1514s |

→ CLI 에 `--duration <초>` (기본 300) 를 둔다. 배속 옵션은 만들지 않는다.

### 검증

- [x] `grep -rn "TTransportException" docs/` → ADR-003 의 "실제 위치" 설명에만 등장 (정정 완료, `8d65257`)
- [x] ADR-003 에 실측 근거(200건, 문구 원문)가 인용돼 있다
- [ ] D1/D3 이 ADR-004 에 반영됐다
- [ ] D2 의 배속 제한 방식이 정해졌다 (1-3 의 3안 중 택1)

---

## Phase 2 — 리더: 원본 → 공통 레코드

`src/rca_sdk/replay/readers.py`. 각 리더는 시나리오 디렉터리를 받아 `(service, timestamp, dict)` 를 산출한다.
**타임시프트는 하지 않는다** — 원본 시각 그대로. 시프트는 Phase 3.

### 구현

| 리더 | 입력 | 서비스 도출 | 참조 |
|---|---|---|---|
| `read_logs()` | `log_data/<시나리오>/<Service>_.log` | 파일명 stem 에서 `_` 제거 → D1 표기로 매핑 | Phase 0-3 정규식 |
| `read_nginx()` | 같은 폴더 `NginxThrift_.log` | 고정 `nginx-thrift` | Phase 0-4 함정 1 |
| `read_metrics()` | `metric_data/<시나리오>/socialnet_container_*.csv` | `container_label_com_docker_compose_service` 컬럼 | Phase 0-4 함정 4,5 |
| `read_traces()` | `trace_data/<시나리오>/all_traces.csv` | `service` 컬럼 | Phase 0-4 함정 10 |

**필수 처리**
- 파일 부재를 정상으로 다룬다 (함정 2). Code_Stop 에 `MediaService_.log` 없음, 0바이트 nginx 파일 존재.
- log/metric 타임스탬프를 **UTC 로 명시** 부여한다 (`tzinfo=UTC`). naive 금지.
- metric 은 `socialnet_container_*` 만. `system_*` 은 서비스 귀인 불가라 **이 Phase 범위 밖**.
- `metric` 컬럼(Prometheus 레이블셋 덤프)은 뒤 컬럼과 중복이니 출력에 넣지 않는다.

### 안티패턴 가드

- `summary.txt` / `metadata.txt` 를 읽지 마라 (함정 6 — 값이 비었거나 깨졌다).
- `all_traces.json` 을 읽지 마라 (함정 10 — CSV 로 충분, JSON 은 `processes` 룩업이 필요해 더 비싸다).
- `normalization/common.py:9` 의 `parse_timestamp()` 를 로그에 쓰지 마라 — `fromisoformat` 기반이라
  영문 월(`Nov`)을 **파싱하지 못한다**. 대신 아래 규칙 파서를 쓴다 (3종 데이터 전수 통과 확인):

```python
BOOST = re.compile(r'\[(\d{4}-[A-Za-z]{3}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]')  # 마이크로초 선택적
NGINX = re.compile(r'^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})')                     # NginxThrift 전용

def parse_boost(s: str) -> datetime:
    for fmt in ('%Y-%b-%d %H:%M:%S.%f', '%Y-%b-%d %H:%M:%S'):   # 함정 11 — 마이크로초 없는 변형
        try: return datetime.strptime(s, fmt)
        except ValueError: pass
    raise ValueError(s)
```

  `%b` 는 C 로케일 의존이다. 로케일이 다른 환경에서 도는 것이 확인되면 월 이름을 직접 매핑한다.
- `NormalizedEvent` 를 import 하지 마라 (Phase 0-1).

### 검증

- [ ] 3종 시나리오 각각에서 리더가 산출한 레코드 수를 출력해 0 이 아님을 확인
- [ ] Code_Stop 에서 `read_logs()` 가 `MediaService` 없이도 예외 없이 동작
- [ ] Perf_CPU 에서 `read_nginx()` 가 0바이트 파일에 대해 0건 산출 (예외 아님)
- [ ] 모든 타임스탬프가 tz-aware (`ts.tzinfo is not None`)
- [ ] `read_traces()` 산출 서비스 집합이 `available_services.json` 과 일치
- [ ] `uv run ruff check .`

---

## Phase 3 — 타임시프트 + 서비스명 정규화

`src/rca_sdk/replay/shift.py`.

### 구현

- **오프셋 시프트**: `new_ts = T0 + (orig_ts - t0)`. `T0` = 재생 시작 시각(고정 앵커, 매 레코드마다
  `now()` 를 다시 부르지 않는다). `t0` = 해당 시나리오 **전 모달리티 통틀어 실측 min**
  (함정 9 — 폴더명 시작 시각이 아니다).
- **상대 간격을 보존한다.** Svc_Kill 의 "Starting" 2회 간격 104초(`00:01:57.490`→`00:03:41.500`)가
  재생 후에도 104초여야 재시작 마커 detector 가 성립한다. 개별 시각을 독립 치환하면 간격이 깨진다.
  배속이 없으므로(1-3) 나눗셈이 없고, 타임스탬프가 벽시계를 그대로 따라간다.
- 서비스명을 D1 표기로 통일. log 의 `MediaService` → `media-service` 매핑.

### 안티패턴 가드

- `canonical_service()` 를 파일명에 쓰지 마라 — 그건 트리거 시점 상관용이고(`trigger-policy.md:16`),
  파일명 적용은 결정된 바 없다. D1 을 따른다.
- 세 모달리티에 **같은 t0** 을 써라. 모달리티별 t0 을 쓰면 시각축이 어긋나 상관이 깨진다
  (Phase 0-3 — 세 모달리티는 같은 절대시각축을 공유한다).

### 검증

- [ ] 시프트 후 Svc_Kill 의 "Starting" 2회 간격이 104초 ± 1s
- [ ] 시프트 후 세 모달리티의 min 타임스탬프가 서로 1초 이내
- [ ] `t0` 이 폴더명이 아니라 데이터 실측 min 임을 단언하는 테스트

---

## Phase 4 — 라이터 + purge

`src/rca_sdk/replay/writer.py`.

### 구현

- `var/{log,metric,trace}/<service>.jsonl` 에 **append**. 디렉터리 자동 생성.
- 한 줄 = JSON 객체 하나. 개행 포함 금지 (tail 이 줄 단위로 읽는다 — `ADR-004:104`).
- `--reset` 시 `var/` 를 비우고 시작 (`ADR-004:115` — append 라 재실행 시 중복).

### 안티패턴 가드

- **`--reset` 이 `var/` 밖을 지우지 않게 하라.** `source_root` 를 해석한 절대경로가 CWD 하위인지
  확인하고, 아니면 실패시킨다. 상대경로 + CWD 전제(`ADR-004:61`)라 오설정 시 엉뚱한 경로를 지울 수 있다.
- `var/` 를 커밋하지 마라 — `.gitignore:47` 이 막지만, pre-commit `check-added-large-files`(500KB)도 걸린다.

### 검증

- [ ] `tmp_path` 로 writer 단위 테스트 (`ADR-004:128` — fixture 파일 새로 만들지 말 것)
- [ ] 각 줄이 `json.loads()` 가능
- [ ] `--reset` 두 번 실행 후 줄 수가 1회 실행과 같다 (중복 없음)
- [ ] `--reset` 없이 두 번 실행하면 줄 수가 2배 (append 확인)

---

## Phase 5 — 스케줄러 + CLI

`src/rca_sdk/replay/cli.py`, `src/rca_sdk/replay/scheduler.py`.

### 구현

- CLI: `rca-replay <scenario> [--duration 300] [--reset]`. `cli.py:11-28` 패턴 복사
  (`build_parser()` 분리, `main(argv) -> int`). **`--speed` 는 만들지 않는다** (1-3).
- 스케줄러는 벽시계 기준으로 `new_ts` 에 도달하면 그 레코드를 쓴다. `--duration` 경과 시 정지
  (1-3' — 5분이면 3종 전부 결함 + post 180초를 덮는다).
- `pyproject.toml:27-28` 에 `rca-replay = "rca_sdk.replay.cli:main"` 추가.
  **editable 설치는 재설치 필요** (`pip install -e ".[dev]"` 또는 `uv sync`).
- 시나리오 매핑 (`ADR-004:125` 승계):
  `cpu=Perf_CPU_Contention`, `kill_media=Svc_Kill_Media`, `code_media=Code_Stop_MediaService`
  → 접두어로 `datasets/sn/<모달리티>/` 하위 디렉터리를 찾는다 (폴더명에 타임스탬프가 붙어 있어 exact match 아님).
- 경로 검증 1회 (`ADR-004:77-85`): `dataset_root` 부재 시 **해석된 절대경로와 CWD 를 함께** 알리고 실패.
- `Settings` 에 필드가 더 필요하면 `config.py:9-28` 규칙(env_prefix `RCA_`)을 따른다.

### 안티패턴 가드

- 시나리오를 경로에 인코딩하지 마라 (`ADR-004:109` — 인자로만 받고 출력은 항상 같은 `var/`).
- `Path(__file__).parents[N]` 로 저장소 루트를 계산하지 마라 (`ADR-004:72-73` — 명시적으로 기각됨).

### 검증

- [ ] `uv run rca-replay cpu --reset` 후 `var/{log,metric,trace}/` 에 파일 생성
- [ ] `uv run rca-replay --help` 가 3종 시나리오와 `--duration` 을 보여준다
- [ ] 잘못된 CWD 에서 실행 시 절대경로+CWD 를 담은 명확한 실패
- [ ] `--duration 300` 이 약 5분에 정지하고, 그 안에 결함 신호가 나온다

---

## Phase 6 — 통합 검증

**기준선은 `ADR-004:36` — "클론만으로 데모 3종이 돈다".**

- [ ] 3종 전부 재생 성공: `for s in cpu kill_media code_media; do uv run rca-replay $s --reset; done`
- [ ] **Phase 0-5 의 신호가 재생 산출물에 살아 있다**:
  - `var/metric/` 에 value ≥ 95 인 레코드 존재 (Perf_CPU)
  - `var/log/media-service.jsonl` 에 "Starting the media-service server" 2건, 간격 104초 (Svc_Kill)
  - `var/trace/` 에 `http_status_code=500` 70건 (Code_Stop)
  - `var/log/nginx-thrift.jsonl` 에 "Could not resolve host" 200건 (Code_Stop)
- [ ] 모든 줄이 `json.loads()` 가능: `find var -name '*.jsonl' | xargs -I{} sh -c 'python -c "import json,sys;[json.loads(l) for l in open(sys.argv[1])]" {}'`
- [ ] 안티패턴 grep:
  - `grep -rn "NormalizedEvent" src/rca_sdk/replay/` → 0건
  - `grep -rn "summary.txt\|metadata.txt\|all_traces.json" src/rca_sdk/replay/` → 0건
  - `grep -rn "parents\[" src/rca_sdk/replay/` → 0건
- [ ] `uv run pytest` / `uv run ruff check .` 통과
- [ ] `git status` 에 `var/` 가 안 잡힌다

### 이 Phase 에서 하지 않는 것

**detector 연동은 범위 밖이다.** `ADR-003:30` — "확정 전까지 detector 인터페이스/테스트를 고정할 수
없음". `trigger/detector.py` 의 restart-marker detector 는 아직 없다(`ADR-003:29` — "연구 코드에 없음
— MVP blocker"). 리플레이어는 **재생 산출물에 신호가 살아 있는 것**까지만 책임진다.

---

## 열린 문제

### 리플레이어 범위 내

| # | 문제 | 영향 |
|---|---|---|
| 1 | D1'(metric 라벨 필터), D4(JSONL 필드 집합) 미결 | Phase 2~3 전에 정하면 됨 |
| 2 | 재생이 `--duration` 전에 데이터 끝에 도달하면 정지인지 반복인지 미정 | Phase 5 에서 결정. 5분 재생엔 안 걸린다 (데이터가 20분+) |
| 3 | metric `value` 단위 미확정 — container 0.0008~0.29(코어분율?) vs system 0~100(%) | 원본 PromQL 미확인. 임계 95 는 `system_*` 기준이라 당장은 무관 |

### 리플레이어 범위 밖 — 다른 문서로 이관 필요

아래는 리플레이어 구현과 무관하다. "재생한 데이터로 데모가 성립하는가"를 확인하다 발견한 것이라
여기 적어둘 뿐, **결론은 해당 문서에서 내야 한다.** 이 계획은 신호를 살려 내보내는 데까지만 책임진다.

| # | 발견 | 갈 곳 |
|---|---|---|
| 4 | **빈 baseline 으로는 3종 전부 log 가 user-service 를 오탐한다** (아래) | ADR-002 (이미 blocker) |
| 5 | **결함 서비스 ≠ 에러 보고 서비스** (아래) | `docs/trigger-policy.md` 의 correlation 절 |
| 6 | pre 윈도 부족 — 결함이 105~124초에 오는데 ADR-001 요구는 210초 | ADR-001. 데이터 한계라 리플레이어로 해결 불가 |
| 7 | Runner 기동 시 경로 검증 미구현 (`ADR-004` — "tailer 구현보다 먼저") | 별도 작업. 없으면 CWD 오설정이 조용한 0건으로 흘러간다 |
| 8 | ADR-004 의 "`sn_normal.json` 이 커밋돼 있어 당장은 막히지 않는다" 가 **틀렸다** | ADR-004. 파일은 있어도 값이 비어 실제로 막는다 |

**#4 근거.** `src/rca_sdk/resources/baselines/sn_normal.json` 은 placeholder 로 `"log": {"error_by_service": {}}`
다. `trigger-policy.md` 는 log 를 "≥ 2.0× baseline (**baseline 0 이면 즉시 트리거**)" 로 정하므로, 빈
baseline 에서는 error 라인이 하나라도 있으면 발화한다. 실측:

| 시나리오 | 서비스 | 건수 | 문구 |
|---|---|---|---|
| Perf_CPU | UserService | 200 | `Failed to insert user j1 to MongoDB: E11000 duplicate key` |
| Svc_Kill_Media | UserService | 200 | 〃 |
| Code_Stop_Media | UserService | 200 | 〃 |
| Code_Stop_Media | ComposePostService | 200 | `Failed to connect media-service-client` |

UserService 의 200건은 **3종 전부에 똑같이 있는 상시 배경 노이즈**다 — 워크로드 생성기가 같은 유저를
반복 삽입해 나는 것이고 결함과 무관하다. Perf_CPU 와 Svc_Kill 은 error 를 내는 서비스가 UserService
**뿐**이라 log 후보가 오직 오탐 하나다.

역으로 이 노이즈가 3종에 일정하다는 건 **좋은 baseline 재료**라는 뜻이다.
`error_by_service: {"user-service": 200}` 이면 오탐이 사라진다.

**#5 근거.** Code_Stop_MediaService 에서 media-service 는 죽어서 **로그 파일 자체가 없고**(함정 2),
ComposePostService 가 `Failed to connect media-service-client` 를 200건 낸다. log 는 ComposePost 를,
trace 5xx 는 media 를 가리켜 `canonical_service` 로 묶이지 않는다 — code_media 의 3중 수렴이 성립하지
않는다. detector 가 에러 **메시지 안의** 대상 서비스를 파싱해야 할 수 있다.
