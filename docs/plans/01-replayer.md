# 계획 01 — 리플레이어

`datasets/sn` 의 SN 원본을 타임시프트 재생해 `var/` 로 원천 로그를 만들어내는 Python 리플레이어.
경로·레이아웃 계약은 [ADR-004](../decisions/ADR-004-replayer-data-layout.md).

## 범위

**`var/` 에 데이터가 제대로 쌓이는 데까지다.** 재생 산출물이 원본에 충실하면 완료다.

범위 밖 — 이 계획에서 다루지 않는다:

- detector, 트리거 발화, correlation, baseline — SDK 파이프라인 소관이며 별도 작업자가 진행 중이다.
- `docs/decisions/ADR-001~003`, `docs/trigger-policy.md`, `docs/data-schema.md` 등 그쪽 문서 — **손대지 않는다.**
- "데모가 도는가" — 리플레이어가 판단할 수 있는 기준이 아니다.

새 문서가 필요하면 `ADR-00N` 번호를 쓰지 않는다 — 다른 작업자와 번호가 겹친다.

각 Phase 는 새 세션에서 독립 실행 가능하도록 자체 참조를 갖는다. Phase 0 은 실행 완료됐고, 아래
"확인된 사실"이 그 산출물이다 — **추측 대신 이 표를 근거로 구현한다.**

---

## Phase 0 — 확인된 사실 (실행 완료)

모두 실제 파일을 열어 확인했다. 출처 없는 항목은 넣지 않았다.

### 0-1. 리플레이어 출력은 정규화 **이전** 원본이다

근거가 독립적으로 4개 수렴한다:

| 근거 | 출처 |
|---|---|
| "둘 다 정규화 이전이라…" | `ADR-004` 맥락 절 |
| "원시 레코드를 산출한다. 산출물은 아직 정규화 이전" + `poll() -> Iterator[dict[str, Any]]` | `collectors/base.py:13-21` |
| 파이프라인 순서 `collectors.poll → normalization → buffer.add` | `runtime/runner.py:5` |
| `raw_ref` 가 `var/` 의 파일:라인을 가리킨다 — `var/` 가 `NormalizedEvent` 면 자기 자신을 "정규화 이전 원본"으로 참조하는 순환 | `ADR-004` + `schemas/events.py:33-34` |

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
| log 타임스탬프 | `[%Y-%b-%d %H:%M:%S.%f]` — 월이 영문 약어(`Nov`), C 로케일 필요. **마이크로초 없는 변형 존재** (함정 11) | `log_data/Perf_CPU_*/UserService_.log:1` |
| log 라인 정규식 | `^\[(?P<ts>[^\]]+)\] <(?P<level>\w+)>: \((?P<src>[^:]+):(?P<srcline>\d+):(?P<func>[^)]+)\) (?P<msg>.*)$` | 위 파일 (비정형 라인 0건 확인) |
| log 레벨 | `<info>` / `<error>` 2종만 실측. `<warning>` 미출현 | `UserService_.log` (info 153023, error 200) |
| metric 타임스탬프 | `%Y-%m-%d %H:%M:%S` (초 단위, 15초 간격 스크레이프) | `socialnet_container_cpu.csv:2` |
| metric 공통 컬럼 | `timestamp,value,metric` + 파일마다 다른 레이블 컬럼 | `socialnet_container_cpu.csv:1` |
| trace CSV 헤더 | `trace_id,span_id,parent_span_id,service,operation,start_time,duration_us,http_status_code,http_method,http_url,component,tags,logs` | `all_traces.csv:1` |
| trace 타임스탬프 | `%Y-%m-%d %H:%M:%S.%f`, **UTC** (2098건 전수 대조로 확정) | `all_traces.csv` |

log/metric 은 타임존 표기가 물리적으로 없다 → **UTC 로 명시 해석**한다. naive 로 두면 실행 환경에 따라 어긋난다.

### 0-4. 시간축 정렬 실측 — 종료는 맞고 시작은 다르다

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

### 0-5. 함정 (전부 실측 확인)

1. **로그 파서가 2종 필요하다.** `NginxThrift_.log` 는 boost 가 아니라 nginx error_log 포맷이다:
   `2025/11/04 02:58:25 [error] 9#9: *816 [lua] compose.lua:62: ...` → `%Y/%m/%d %H:%M:%S`, 대괄호 없음.
   단일 파서 가정 시 Code_Stop 의 nginx 200행을 **전량 유실**한다.
2. **시나리오마다 파일 구성이 다르다.** Code_Stop 은 `MediaService_.log` **자체가 없다**(서비스가 죽어서).
   Perf_CPU / Svc_Kill 은 `NginxThrift_.log` 가 **0바이트**다. 파일 존재를 가정하면 안 된다.
3. **서비스명 표기가 모달리티마다 다르다.** log=`MediaService`(Pascal), metric=`media-service`(kebab),
   trace=`media-service`(kebab).
4. **metric 라벨 31개에 서비스가 아닌 것이 섞여 있다** — `cadvisor`, `prometheus`, `node-exporter`,
   `*-redis`, `*-mongodb`. 필터 필요 (D2).
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

### 0-6. 충실도의 정의

리플레이어는 **원본 레코드를 빠짐없이, 상대 간격을 유지한 채, 맞는 서비스 파일로 옮기면 끝이다.**
그 줄의 내용이 무엇인지는 보지 않는다 — 읽지 않고 옮긴다.

세 가지로 검증한다:

| 기준 | 방법 |
|---|---|
| **누락 없음** | 원본 레코드 수 == `var/` 의 줄 수 (모달리티별, 서비스별) |
| **간격 보존** | 출력의 인접 타임스탬프 차이 == 원본의 차이 |
| **분배 정확** | 서비스별 줄 수가 원본의 서비스별 레코드 수와 일치 |

원본 레코드 수는 리더(Phase 2)가 세고, 출력 줄 수는 라이터(Phase 4)가 센다. 둘을 대조하면
파이프라인 어디서 새는지 바로 드러난다.

### 0-7. 시나리오 길이

| 시나리오 | 데이터 전체 길이 |
|---|---|
| cpu | 1200s |
| kill_media | 1187s |
| code_media | 1514s |

전체 재생은 20~25분이다. 데모에서 그만큼 볼 필요가 없으면 `--duration` 으로 끊는다 (D5).

### 0-8. 따라야 할 기존 규약

| 필요한 것 | 복사할 위치 |
|---|---|
| argparse CLI 뼈대 (`build_parser()` 분리 + `main(argv) -> int`) | `src/rca_sdk/cli.py:11-28` |
| console script 등록 | `pyproject.toml` `[project.scripts]` |
| settings 주입 (`settings or load_settings()`) | `src/rca_sdk/runtime/runner.py:17-19` |
| Settings 필드 추가 (env_prefix `RCA_`) | `src/rca_sdk/config.py:9-28` |
| 테스트 스타일 (평면 `def test_*`, 한국어 주석, 고정 datetime) | `tests/test_smoke.py:18-45` |
| 모듈 헤더 (한국어 docstring + `from __future__ import annotations`) | 모든 `src/rca_sdk/**/*.py:1-3` |

린트: ruff `line-length=100`, `select=["E","F","I","UP","B"]`, py311. CI 는 `ruff check .` → `pytest`.
mypy 는 설정만 있고 CI 미실행.

### 0-9. 존재하지 않는 것 — 지어내지 마라

- `AnoMod/analysis/sn_db/loaders.py` — `data-schema.md` 가 참조하나 **이 저장소에 없다.**
- `normalize_log/metric/trace` — 전부 `raise NotImplementedError` 스캐폴드다. 호출하지 마라.
- `Runner.tick()` — `NotImplementedError`. 리플레이어는 Runner 에 의존하지 않는다.
- `make_event` 픽스처 — `NormalizedEvent` 레벨이라 리플레이어 테스트에 **쓸 수 없다**.

---

## Phase 1 — 선행 결정 (코드 없음)

| # | 질문 | 결정 |
|---|---|---|
| D1 | `var/<service>.jsonl` 의 service 표기형 | **`media-service`** — 3종 중 2종이 이미 그 표기라 log 만 매핑하면 된다 |
| D2 | **metric 라벨 31개 중 무엇을 서비스로 볼 것인가** | **미결.** 로그 파일이 있는 11~12개만 / `-service` 접미어만 / 전부 |
| D3 | 리플레이어 스크립트 이름·모듈 경로 | **`rca-replay` = `rca_sdk.replay.cli:main`** — 기존 `rca-collect` 와 대칭 |
| D4 | JSONL 한 줄의 필드 집합 | **미결.** Phase 2 에서 모달리티별로 확정 |

**D1 은 표기 통일일 뿐이다.** 3종 중 2종(metric·trace)이 이미 `media-service` 라 log 만 매핑하면 된다.
`media-service` 로 통일하고 넘어간다.

**D2 가 실질적 결정이다.** metric 의 `container_label_com_docker_compose_service` 값 31개에 서비스가
아닌 것이 섞여 있다 (함정 4):

```
media-service, social-graph-service, user-service ...    ← 서비스
cadvisor, prometheus, node-exporter, jaeger-agent         ← 인프라
user-mongodb, social-graph-redis, ...                     ← 데이터스토어
```

31개를 다 쓰면 `var/metric/` 에 파일이 31개 생긴다. 로그 파일이 있는 11~12개로 맞추면 세 모달리티의
서비스 집합이 정렬된다.

### D5. 배속 기능은 **범위에서 제외**한다 (2026-07-15 결정)

당초 요구사항은 1x/5x/10x 였으나 제외한다.

**배속은 간격 보존과 양립하지 않는다.** 재생 시 타임스탬프를 `T0 + (orig - t0)/speed` 로 쓸 수밖에
없는데, `/speed` 를 하면 **간격이 배속만큼 줄어든다** (10x 면 104초 간격이 10.4초). `/speed` 를 안 하면
타임스탬프가 벽시계보다 미래로 달려나간다. 어느 쪽이든 **재생 산출물이 원본과 달라진다** — 0-6 의
"간격 보존"을 정면으로 위반하므로 완료 기준 자체가 무너진다.

**대신 `--duration <초>` 로 끊는다.** 배속이 풀려던 문제는 "20~25분을 다 볼 수 없다"였고, 끊는 것으로
해결된다 — 타임스탬프를 건드리지 않으므로 끊기 전까지는 원본과 동일하다. 기본값은 두지 않는다
(생략 시 전체 재생). 얼마를 볼지는 돌리는 사람이 정한다.

### 검증

- [ ] D2 가 정해졌다 (metric 라벨 필터)
- [ ] D4 가 정해졌다 (JSONL 필드 집합)

---

## Phase 2 — 리더: 원본 → 공통 레코드

`src/rca_sdk/replay/readers.py`. 각 리더는 시나리오 디렉터리를 받아 `(service, timestamp, dict)` 를 산출한다.
**타임시프트는 하지 않는다** — 원본 시각 그대로. 시프트는 Phase 3.

### 구현

| 리더 | 입력 | 서비스 도출 | 참조 |
|---|---|---|---|
| `read_logs()` | `log_data/<시나리오>/<Service>_.log` | 파일명 stem 에서 `_` 제거 → D1 표기로 매핑 | 0-3 정규식 |
| `read_nginx()` | 같은 폴더 `NginxThrift_.log` | 고정 `nginx-thrift` | 함정 1 |
| `read_metrics()` | `metric_data/<시나리오>/socialnet_container_*.csv` | `container_label_com_docker_compose_service` 컬럼 | 함정 4, 5 |
| `read_traces()` | `trace_data/<시나리오>/all_traces.csv` | `service` 컬럼 | 함정 10 |

**필수 처리**
- 파일 부재를 정상으로 다룬다 (함정 2). Code_Stop 에 `MediaService_.log` 없음, 0바이트 nginx 파일 존재.
- log/metric 타임스탬프를 **UTC 로 명시** 부여한다 (`tzinfo=UTC`). naive 금지.
- metric 은 `socialnet_container_*` 만. `system_*` 은 서비스 귀인 불가라 **범위 밖**.
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
- `NormalizedEvent` 를 import 하지 마라 (0-1).

### 검증

- [ ] 3종 시나리오 각각에서 리더가 산출한 레코드 수가 0 이 아니다
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
  `now()` 를 다시 부르지 않는다). `t0` = 해당 시나리오 **전 모달리티 통틀어 실측 min** (함정 9).
- **상대 간격을 보존한다** (0-6). 배속이 없으므로(D5) 나눗셈이 없고 타임스탬프가 벽시계를 그대로
  따라간다. 개별 시각을 독립 치환하면 간격이 깨진다 — `T0` 를 고정 앵커로 잡는 이유다.
- 서비스명을 D1 표기로 통일. log 의 `MediaService` → `media-service` 매핑.

### 안티패턴 가드

- 세 모달리티에 **같은 t0** 을 써라. 모달리티별 t0 을 쓰면 trace 가 126~179초 앞당겨져 원본에 없던
  정렬이 생긴다 (0-4).
- `canonical_service()` 를 파일명에 쓰지 마라 — 그건 소비하는 쪽의 함수다. D1 을 따른다.

### 검증

- [ ] 시프트 후 인접 레코드 간격이 원본과 동일 (0-6 "간격 보존")
- [ ] 시프트 후 세 모달리티의 min 타임스탬프 간격이 원본과 같다 (cpu 126s / kill_media 179s / code_media 162s)
- [ ] `t0` 이 폴더명이 아니라 데이터 실측 min 임을 단언하는 테스트

---

## Phase 4 — 라이터 + purge

`src/rca_sdk/replay/writer.py`.

### 구현

- `var/{log,metric,trace}/<service>.jsonl` 에 **append**. 디렉터리 자동 생성.
- 한 줄 = JSON 객체 하나. 개행 포함 금지 (tail 이 줄 단위로 읽는다 — `ADR-004`).
- `--reset` 시 `var/` 를 비우고 시작 (`ADR-004` — append 라 재실행 시 중복).

### 안티패턴 가드

- **`--reset` 이 `var/` 밖을 지우지 않게 하라.** `source_root` 를 해석한 절대경로가 CWD 하위인지
  확인하고, 아니면 실패시킨다. 상대경로 + CWD 전제라 오설정 시 엉뚱한 경로를 지울 수 있다.
- `var/` 를 커밋하지 마라 — `.gitignore` 가 막지만, pre-commit `check-added-large-files`(500KB)도 걸린다.

### 검증

- [ ] `tmp_path` 로 writer 단위 테스트 (`ADR-004` — fixture 파일 새로 만들지 말 것)
- [ ] 각 줄이 `json.loads()` 가능
- [ ] `--reset` 두 번 실행 후 줄 수가 1회 실행과 같다 (중복 없음)
- [ ] `--reset` 없이 두 번 실행하면 줄 수가 2배 (append 확인)

---

## Phase 5 — 스케줄러 + CLI

`src/rca_sdk/replay/cli.py`, `src/rca_sdk/replay/scheduler.py`.

### 구현

- CLI: `rca-replay <scenario> [--duration <초>] [--reset]`. `cli.py:11-28` 패턴 복사
  (`build_parser()` 분리, `main(argv) -> int`). **`--speed` 는 만들지 않는다** (D5).
- 스케줄러는 벽시계 기준으로 `new_ts` 에 도달하면 그 레코드를 쓴다. `--duration` 경과 시 정지.
- `pyproject.toml` `[project.scripts]` 에 `rca-replay = "rca_sdk.replay.cli:main"` 추가.
  **editable 설치는 재설치 필요** (`uv sync`).
- 시나리오 매핑 (`ADR-004` 승계):
  `cpu=Perf_CPU_Contention`, `kill_media=Svc_Kill_Media`, `code_media=Code_Stop_MediaService`
  → 접두어로 `datasets/sn/<모달리티>/` 하위 디렉터리를 찾는다 (폴더명에 타임스탬프가 붙어 exact match 아님).
- 경로 검증 1회: `dataset_root` 부재 시 **해석된 절대경로와 CWD 를 함께** 알리고 실패.

### 안티패턴 가드

- 시나리오를 경로에 인코딩하지 마라 (`ADR-004` — 인자로만 받고 출력은 항상 같은 `var/`).
- `Path(__file__).parents[N]` 로 저장소 루트를 계산하지 마라 (`ADR-004` 에서 명시적으로 기각됨).

### 검증

- [ ] `uv run rca-replay cpu --reset` 후 `var/{log,metric,trace}/` 에 파일 생성
- [ ] `uv run rca-replay --help` 가 3종 시나리오와 `--duration` 을 보여준다
- [ ] 잘못된 CWD 에서 실행 시 절대경로+CWD 를 담은 명확한 실패
- [ ] `--duration` 생략 시 전체 재생, 지정 시 그 시각에 정지한다

---

## Phase 6 — 통합 검증

**완료 기준: 재생 산출물이 원본에 충실한가.**

- [ ] 3종 전부 재생 성공: `for s in cpu kill_media code_media; do uv run rca-replay $s --reset; done`
- [ ] **누락 없음** — 리더가 센 원본 레코드 수 == `var/` 의 줄 수 (모달리티별, 서비스별로 대조)
- [ ] **간격 보존** — 출력의 인접 타임스탬프 차이가 원본과 동일
- [ ] **분배 정확** — 서비스별 줄 수가 원본의 서비스별 레코드 수와 일치
- [ ] 모든 줄이 `json.loads()` 가능
- [ ] 안티패턴 grep:
  - `grep -rn "NormalizedEvent" src/rca_sdk/replay/` → 0건
  - `grep -rn "summary.txt\|metadata.txt\|all_traces.json" src/rca_sdk/replay/` → 0건
  - `grep -rn "parents\[" src/rca_sdk/replay/` → 0건
- [ ] `uv run pytest` / `uv run ruff check .` 통과
- [ ] `git status` 에 `var/` 가 안 잡힌다

---

## 열린 문제

| # | 문제 | 영향 |
|---|---|---|
| 1 | D2(metric 라벨 필터), D4(JSONL 필드 집합) 미결 | Phase 2 전에 정하면 됨 |
| 2 | 데이터 끝에 도달하면 정지인지 반복인지 미정 | Phase 5 에서 결정 |
| 3 | metric `value` 단위 미확정 — container 0.0008~0.29(코어분율?) vs system 0~100(%) | 원본 PromQL 미확인. 출력은 원본 값을 그대로 흘리므로 리플레이어는 막히지 않는다 |
