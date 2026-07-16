# 계획 01 — 리플레이어

`datasets/sn` 의 SN 원본을 타임시프트 재생해 `var/` 로 원천 로그를 만들어내는 Python 리플레이어.
경로·레이아웃 계약은 [ADR-004](../decisions/ADR-004-replayer-data-layout.md).
전체 흐름은 [01-replayer-flow.svg](01-replayer-flow.svg).

## 범위

**`var/` 에 데이터가 제대로 쌓이는 데까지다.** 재생 산출물이 원본에 충실하면 완료다.

리플레이어가 하는 일은 이것뿐이다:

> 원본 파일을 읽어 **타임스탬프만 파싱**하고, 그 시각에 맞춰 **원본 줄을 바이트 그대로** `var/` 에 쓴다.

포맷을 바꾸지 않는다. 서비스별로 재분할하지 않는다. 파일명을 바꾸지 않는다. 줄의 내용이 무엇을
의미하는지 보지 않는다.

범위 밖 — 이 계획에서 다루지 않는다:

- detector, 트리거 발화, correlation, baseline — SDK 파이프라인 소관이며 별도 작업자가 진행 중이다.
- `docs/decisions/ADR-001~003`, `docs/trigger-policy.md`, `docs/data-schema.md` 등 그쪽 문서 — **손대지 않는다.**
- 콜렉터의 원본 형식 파싱 — `var/` 에 원본이 오므로 콜렉터가 파싱한다. 리플레이어 일이 아니다.
- "데모가 도는가" — 리플레이어가 판단할 수 있는 기준이 아니다.

새 문서가 필요하면 `ADR-00N` 번호를 쓰지 않는다 — 다른 작업자와 번호가 겹친다.

각 Phase 는 새 세션에서 독립 실행 가능하도록 자체 참조를 갖는다. Phase 0 은 실행 완료됐고, 아래
"확인된 사실"이 그 산출물이다 — **추측 대신 이 표를 근거로 구현한다.**

---

## Phase 0 — 확인된 사실 (실행 완료)

모두 실제 파일을 열어 확인했다. 출처 없는 항목은 넣지 않았다.

### 0-1. 재생 대상과 출력 레이아웃

재생 대상은 **줄 단위이면서 타임스탬프가 있는 파일**뿐이다.

| 모달리티 | 원본 | 출력 | 개수 |
|---|---|---|---|
| log | `log_data/<시나리오>/<Service>_.log` | `var/log/<Service>_.log` | 11~12 |
| metric | `metric_data/<시나리오>/*.csv` | `var/metric/<같은 이름>.csv` | 15 |
| trace | `trace_data/<시나리오>/all_traces.csv` | `var/trace/all_traces.csv` | 1 |

**재생하지 않는 것:**

| 파일 | 이유 |
|---|---|
| `all_traces.json` | 87,142행 pretty-print JSON — 한 스팬이 여러 줄에 걸쳐 줄 단위 tail 불가 |
| `summary.txt`, `metadata.txt` | 타임스탬프 없음. 수집 부산물이지 실행 중인 서비스가 만드는 것이 아님 |
| `available_services.json` | 위와 같음 (Jaeger API 응답 기록) |

CSV 는 **출력 파일이 없거나 0바이트일 때만 헤더 한 줄을 쓰고**, 이후 행을 시각에 맞춰 append 한다.
시나리오를 바꿔 이어 돌려도 헤더가 파일 중간에 데이터 행인 척 끼어들지 않는다. 3종의 CSV 는 파일명도
헤더도 동일하다.

### 0-2. 타임스탬프 위치 — 파싱해야 하는 것은 이게 전부다

| 모달리티 | 파일 | 위치 | 포맷 |
|---|---|---|---|
| log (boost) | `<Service>_.log` | 줄 맨 앞 `[...]` | `%Y-%b-%d %H:%M:%S.%f` — 월이 영문 약어(`Nov`), C 로케일. **마이크로초 없는 변형 존재** (함정 6) |
| log (nginx) | `NginxThrift_.log` | 줄 맨 앞, 대괄호 없음 | `%Y/%m/%d %H:%M:%S` |
| log (thrift) | `ComposePostService_.log` (Code_Stop) | `Thrift: ` 뒤 | `%a %b %d %H:%M:%S %Y` — C asctime, 일(day)이 공백 패딩 |
| metric | 모든 `*.csv` | `timestamp` 컬럼 (첫 컬럼) | `%Y-%m-%d %H:%M:%S` |
| trace | `all_traces.csv` | `start_time` 컬럼 | `%Y-%m-%d %H:%M:%S.%f` |

파싱 규칙 (3종 데이터 전수 통과 확인):

```python
BOOST  = re.compile(r'^\[(\d{4}-[A-Za-z]{3}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]')  # 마이크로초 선택적
NGINX  = re.compile(r'^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})')
THRIFT = re.compile(r'^Thrift: ([A-Za-z]{3} [A-Za-z]{3} [ \d]\d \d{2}:\d{2}:\d{2} \d{4}) ')

def parse_boost(s: str) -> datetime:
    for fmt in ('%Y-%b-%d %H:%M:%S.%f', '%Y-%b-%d %H:%M:%S'):   # 함정 6
        try: return datetime.strptime(s, fmt)
        except ValueError: pass
    raise ValueError(s)
```

`strptime` 의 `%d` 는 공백 패딩(`Nov  4`)을 받아낸다. 되렌더링 시 `%e` 는 윈도우에서 안 되므로
`f"{ts:%a %b} {ts.day:2d} {ts:%H:%M:%S %Y}"` 로 직접 패딩한다 — 원본과 바이트 동일함을 확인했다.

`%b` 는 C 로케일 의존이다. 로케일이 다른 환경에서 도는 것이 확인되면 월 이름을 직접 매핑한다.

log/metric 은 타임존 표기가 물리적으로 없다 → **UTC 로 명시 해석**한다. naive 로 두면 실행 환경에 따라
어긋난다. trace 의 `start_time` 은 UTC 임이 2098건 전수 대조로 확정됐다.

### 0-3. 시간축 정렬 실측 — 종료는 맞고 시작은 다르다

3종 × 3모달리티 전수 측정:

| 시나리오 | log | metric | trace | 시작 편차 | 종료 편차 |
|---|---|---|---|---|---|
| cpu | 22:26:39–22:46:39 | 22:26:53–22:47:06 | 22:28:45–22:46:39 | **126s** | 27s |
| kill_media | 00:01:50–00:21:37 | 00:02:07–00:22:05 | 00:04:49–00:21:37 | **179s** | 28s |
| code_media | 02:56:21–03:21:34 | 02:56:34–03:22:01 | 02:59:03–03:21:34 | **162s** | 26s |

**종료가 26~28초로 맞는 것이 핵심 근거다** — 세 모달리티가 같은 절대시각축을 공유한다. 어느 하나가
로컬타임(KST)이었다면 9시간 어긋났을 것이다.

**trace 만 2~3분 늦게 시작하는 것은 데이터의 사실이지 오류가 아니다.** 트레이스는 20% 확률 샘플이라
초반 트래픽이 희박하면 첫 샘플이 늦게 잡힌다.

→ **이것이 "전 모달리티에 같은 t0" 규칙의 근거다** (Phase 2). 같은 t0 를 쓰면 원본의 상대관계가 그대로
보존된다. 모달리티별 t0 를 쓰면 trace 가 126~179초 앞당겨지면서 **원본에 없던 정렬이 생긴다** —
그것이 왜곡이다.

### 0-4. 시나리오 길이

| 시나리오 | 전체 길이 |
|---|---|
| cpu | 1200s |
| kill_media | 1187s |
| code_media | 1514s |

전체 재생은 20~25분이다. 그만큼 볼 필요가 없으면 `--duration` 으로 끊는다.

### 0-5. 충실도의 정의

| 기준 | 방법 |
|---|---|
| **누락 없음** | 원본 줄 수 == `var/` 의 줄 수 (파일별). CSV 는 헤더 포함 |
| **내용 보존** | 출력 줄 == 입력 줄 (타임스탬프 필드만 다름) — 바이트 대조 |
| **간격 보존** | 출력의 인접 타임스탬프 차이 == 원본의 차이 |

원본이 파일별로 그대로 대응하므로 대조가 단순하다. `--duration` 으로 끊었으면 "누락 없음"은 끊긴
지점까지만 본다.

### 0-6. 함정 (전부 실측 확인)

1. **로그 파서가 2종 필요하다.** `NginxThrift_.log` 만 nginx error_log 포맷이다 (0-2). 단일 파서 가정 시
   Code_Stop 의 nginx 200행을 **전량 유실**한다.
2. **시나리오마다 파일 구성이 다르다.** Code_Stop 은 `MediaService_.log` **자체가 없다**(서비스가 죽어서).
   Perf_CPU / Svc_Kill 은 `NginxThrift_.log` 가 **0바이트**다. 파일 존재를 가정하면 안 된다.
3. **CSV 는 시간순이 아니다. 로그는 사실상 시간순이다. 둘의 처리가 다르다** (아래 0-6' 참조).
4. **폴더명 시작 시각보다 데이터가 늦게 시작한다** (Code_Stop: 폴더 02:48:19 vs 데이터 02:56:21, 8분 갭).
   **t0 은 데이터 실측 min 을 쓴다.**
5. **파일 크기 편차가 380배다** (Perf_CPU: `SocialGraphService_.log` 153,621행 / 27MB vs
   `UrlShortenService_.log` 401행). 전량 메모리 적재는 피한다.
6. **로그 타임스탬프에 마이크로초가 없는 변형이 있다.** `[2025-Nov-03 22:28:07]` — `.%f` 없음.
   `SocialGraphService_.log` 1건, `UserService_.log` 1건 (Perf_CPU 기준). 마이크로초가 정확히 0 이라
   boost 가 생략한 것으로 보인다. **딱 2건이지만 파서가 죽으면 재생이 통째로 멈춘다.**

### 0-6'. 정렬 — 로그는 순서 보존, CSV 는 정렬

| | 정렬 | 근거 |
|---|---|---|
| **로그** | **하지 않는다** | 파일에 적힌 순서가 서비스가 쓴 순서다. tailer 도 그 순서로 읽는다 |
| **metric / trace CSV** | **한다** | 행 순서가 쿼리 결과 순서일 뿐 쓰인 순서가 아니다 |

**로그는 마이크로초 단위로 역행한다.** `SocialGraphService_.log` 는 153,621줄 중 **28,727줄**이 앞줄보다
이르다 (0.000001~0.0007초). 멀티스레드 서비스가 한 파일에 쓰면서 생긴 실제 뒤섞임이며, 그 순서가 진실이다.
정렬하면 원본에 없던 순서를 만들어낸다. 역행 폭이 1밀리초 미만이라 파일 순서대로 흘려도 시각은 사실상
단조증가한다.

**CSV 는 계열별로 묶여 있어 20분씩 되감긴다.** `socialnet_container_cpu.csv` 는 31계열 × 80샘플인데
한 계열의 80샘플(20분)이 다 나온 뒤 다음 계열이 처음 시각부터 다시 시작한다:

```
행    1   22:27:07  cadvisor
행   80   22:46:52  cadvisor            ← 20분치 끝
행   81   22:27:07  compose-post-redis  ← 되감김
```

파일 순서대로 방출하면 **cadvisor 하나만 20분에 걸쳐 재생되고 나머지 30계열은 시각이 이미 지나 마지막에
한꺼번에 쏟아진다.** 재생이 아니라 덤프가 된다. metric CSV 15개 중 **7개**가 비정렬이고 `all_traces.csv`
도 마찬가지다.

정렬하는 쪽이 실제에 더 가깝다 — 진짜 Prometheus 는 시각순으로 스크레이프하지 계열별로 몰아 쓰지 않는다.
계열 묶음은 range query 응답을 CSV 로 내보낼 때 생긴 모양이다.

**크기가 이 규칙을 허용한다**: 정렬이 필요한 CSV 는 전부 합쳐 **5MB**(전량 적재 무해), 정렬이 불필요한
로그가 **49MB**(제너레이터로 흘림). 정렬 요구와 "전량 적재 금지"는 충돌하지 않는다.

### 0-7. 따라야 할 기존 규약

| 필요한 것 | 복사할 위치 |
|---|---|
| argparse CLI 뼈대 (`build_parser()` 분리 + `main(argv) -> int`) | `src/rca_sdk/cli.py:11-28` |
| settings 주입 (`settings or load_settings()`) | `src/rca_sdk/runtime/runner.py:17-19` |
| Settings 필드 추가 (env_prefix `RCA_`) | `src/rca_sdk/config.py:9-28` |
| 테스트 스타일 (평면 `def test_*`, 한국어 주석, 고정 datetime) | `tests/test_smoke.py:18-45` |
| 리플레이어 테스트 위치·실행 | `demo/replayer/tests/` · `uv run python -m pytest demo/` |
| 모듈 헤더 (한국어 docstring + `from __future__ import annotations`) | 모든 `src/rca_sdk/**/*.py:1-3` |

린트: ruff `line-length=100`, `select=["E","F","I","UP","B"]`, py311. mypy 는 설정만 있고 CI 미실행.

**테스트는 SDK 와 분리한다.** `demo/` 는 설치되는 패키지가 아니라 bare `pytest` 로는 `import demo` 가
안 된다 (`sys.path` 에 저장소 루트가 없다). `python -m` 이 CWD 를 넣어주므로 리플레이어 테스트는
`uv run python -m pytest demo/` 로 돌린다. `pyproject.toml` 의 `testpaths = ["tests"]` 가 그대로라
`.github/workflows/ci.yml` 의 bare `pytest` 는 SDK 것만 본다 — CI 도 pyproject 도 건드리지 않는다.
루트에 `conftest.py` 를 만들지 마라.

### 0-8. 존재하지 않는 것 — 지어내지 마라

- `AnoMod/analysis/sn_db/loaders.py` — `data-schema.md` 가 참조하나 **이 저장소에 없다.**
- `normalize_log/metric/trace` — 전부 `raise NotImplementedError` 스캐폴드다. 호출하지 마라.
- `Runner.tick()` — `NotImplementedError`. 리플레이어는 Runner 에 의존하지 않는다.
- `make_event` 픽스처 — `NormalizedEvent` 레벨이라 리플레이어 테스트에 **쓸 수 없다**.

---

## Phase 1 — 리더: 원본 → (시각, 원본 줄)

`demo/replayer/readers.py`. 각 리더는 원본 파일을 받아 `(timestamp, 원본 줄)` 을 순서대로 산출한다.
**줄을 해석하지 않는다** — 타임스탬프만 파싱하고 줄은 통째로 들고 간다. 타임시프트도 하지 않는다.

### 구현

| 리더 | 입력 | 타임스탬프 |
|---|---|---|
| `read_log()` | `<Service>_.log` (boost) | 줄 맨 앞 `[...]` — 0-2 `BOOST` |
| `read_nginx()` | `NginxThrift_.log` | 줄 맨 앞 — 0-2 `NGINX` |
| (thrift) | `ComposePostService_.log` 안에 섞여 있음 | `Thrift: ` 뒤 — 0-2 `THRIFT`. boost 파서와 같은 리더가 함께 처리한다 |
| `read_csv()` | metric CSV 15개, `all_traces.csv` | 지정 컬럼 (metric=`timestamp`, trace=`start_time`) |

**필수 처리**
- 파일 부재·0바이트를 정상으로 다룬다 (함정 2).
- CSV 는 헤더를 따로 반환한다 (라이터가 먼저 써야 함).
- **리더는 정렬하지 않는다.** 파일 순서 그대로 산출한다. 정렬은 CSV 에 한해 스케줄러가 한다 (0-6').
- log/metric 타임스탬프에 **UTC 를 명시** 부여한다 (`tzinfo=UTC`).
- 27MB 파일이 있으므로 제너레이터로 흘린다 (함정 5). 전량 리스트 적재 금지.

### 안티패턴 가드

- **줄을 파싱하지 마라.** 타임스탬프 외의 필드(level, message, service, span_id …)를 뜯을 이유가 없다.
  그건 콜렉터 일이다.
- `summary.txt` / `metadata.txt` / `available_services.json` / `all_traces.json` 을 읽지 마라 (0-1).
- `normalization/common.py:9` 의 `parse_timestamp()` 를 쓰지 마라 — `fromisoformat` 기반이라 영문 월
  (`Nov`)을 파싱하지 못한다. 0-2 의 규칙 파서를 쓴다.
- `NormalizedEvent` 를 import 하지 마라.

### 검증

- [ ] 3종 시나리오 각각에서 리더가 산출한 줄 수 == 원본 파일의 줄 수 (CSV 는 헤더 제외)
- [ ] Code_Stop 에서 `MediaService_.log` 부재에도 예외 없이 동작
- [ ] Perf_CPU 에서 `read_nginx()` 가 0바이트 파일에 대해 0건 산출 (예외 아님)
- [ ] 모든 타임스탬프가 tz-aware (`ts.tzinfo is not None`)
- [ ] 산출한 줄이 원본 줄과 바이트 동일
- [ ] `uv run ruff check .`

---

## Phase 2 — 타임시프트

`demo/replayer/shift.py`.

### 구현

- **오프셋 시프트**: `new_ts = T0 + (orig_ts - t0)`. `T0` = 재생 시작 시각(고정 앵커, 매 레코드마다
  `now()` 를 다시 부르지 않는다). `t0` = 해당 시나리오 **전 모달리티 통틀어 실측 min** (함정 4).
- **줄 안의 타임스탬프 문자열을 새 값으로 치환한다.** 원본과 같은 포맷으로 다시 렌더링해야 콜렉터가
  읽을 수 있다. **줄의 나머지 부분은 건드리지 않는다.** 리더가 파싱하는 4종을 그대로 되돌린다:

| 대상 | 재렌더 포맷 | 소수점 (실측) |
|---|---|---|
| boost | `%Y-%b-%d %H:%M:%S[.%f]` | 6자리. **3종 통틀어 3줄만 없음** (함정 6) |
| thrift | C `asctime` — `Tue Nov  4 02:58:25 2025`. 일자는 공백 폭 2 (`%e`) | 없음 |
| nginx | `%Y/%m/%d %H:%M:%S` | 없음 |
| metric CSV | `timestamp` = **0번 컬럼** | 없음 (3종 35,932행 전부) |
| trace CSV | `start_time` = **5번 컬럼** | 6자리 (전부) |

- 타임스탬프에 어떤 배율도 적용하지 않는다. 개별 시각을 독립 치환하면 간격이 깨진다 — `T0` 를 고정
  앵커로 잡는 이유다.

### 안티패턴 가드

- 세 모달리티에 **같은 t0** 을 써라. 모달리티별 t0 을 쓰면 trace 가 126~179초 앞당겨져 원본에 없던
  정렬이 생긴다 (0-3).
- 마이크로초 없는 원본 줄(함정 6)을 치환할 때 마이크로초를 **덧붙이지 마라** — 원본 형식 유지가 원칙이다.
  없이 들어온 줄은 없이 내보낸다. **metric CSV 전체가 여기 해당한다** — boost 3줄만의 문제가 아니다.
  포맷을 모달리티로 고르지 말고, **원본 문자열에 소수점이 있는지 보고** 결정하라.
- **`str.replace()` 로 치환하지 마라.** 같은 시각 문자열이 메시지 본문에도 있으면 거기까지 바뀐다.
  정규식의 `span(1)` 로 바이트 범위를 잘라 끼운다.
- **CSV 를 `csv.writer` 로 되쓰지 마라.** `all_traces.csv` 의 `tags` 필드는 쉼표와 이스케이프된 따옴표를
  품고 있어(`"{""component"": ""nginx"", ...}"`) 재직렬화하면 인용 방식이 원본과 달라진다. 필드의 원본
  바이트 범위만 찾아 도려낸다.
- **월·요일 이름에 `strftime` 의 `%b`/`%a` 를 쓰지 마라.** 로케일에 따라 바뀌어 출력 바이트가 실행
  환경에 좌우된다. 이름을 직접 박는다. (`%e` 는 Windows 에 아예 없다.)

### 검증

**항등 테스트가 렌더러 검증의 축이다.** `anchor == t0` 로 두면 `new_ts == orig_ts` 이므로 출력 줄은
입력 줄과 **바이트 동일**해야 한다. 포맷을 한 글자라도 다르게 재현하면 여기서 걸린다.

- [ ] 시프트 후 인접 레코드 간격이 원본과 동일 (0-5 "간격 보존")
- [ ] 시프트 후 줄이 타임스탬프 외 바이트 동일 (0-5 "내용 보존") — 시프트한 줄을 원본 시각으로 되돌리면
      원본과 같은지로 확인한다
- [ ] 시프트 후 세 모달리티의 min 타임스탬프 간격이 원본과 같다 (cpu 126s / kill_media 179s / code_media 162s)
- [ ] `t0` 이 폴더명이 아니라 데이터 실측 min 임을 단언하는 테스트 — 폴더명보다 실측이 늦다
- [ ] 마이크로초 없는 줄이 시프트 후에도 마이크로초 없이 나온다
- [ ] 위 항목을 **3종 전수(989,199줄)** 로 1회 확인 — 테스트는 표본만 돈다

---

## Phase 3 — 라이터 + purge

`demo/replayer/writer.py`, `demo/replayer/runlog.py`.

### 구현

- `var/{log,metric,trace}/<원본 파일명>` 에 **append**. 디렉터리 자동 생성.
- CSV 헤더는 **출력 파일이 없거나 0바이트일 때만** 쓴다 (0-1). 이미 있으면 쓰지 않는다 — 파일 중간에
  헤더가 들어가면 tail 하는 쪽이 `timestamp` 를 시각으로 파싱하려다 실패한다.
- **이어 돌리기가 정상 경로다.** 시나리오를 바꿔 다시 실행하면 앞 실행 뒤에 이어 쌓인다. `T0` 가 매
  실행 `now()` 라 시각은 계속 증가하고, 덧붙는 것 자체는 데이터를 깨뜨리지 않는다.
- `--reset` 은 **선택적 정리**다. 깨끗한 상태에서 다시 보고 싶을 때 쓴다. 없어도 재생은 성립한다.
  **`var/{log,metric,trace}` 세 디렉터리만 비운다** — `var/` 를 통째로 지우지 않는다 (아래 실행 기록 보존).

### 실행 기록 — `var/.replay/runs.csv`

`var/` 만 봐서는 어디서 시나리오가 바뀌었는지 알 수 없다. 이어 돌리기가 정상 경로이므로 기록이 필요하다.

| 컬럼 | 값 |
|---|---|
| `scenario` | `cpu` / `kill_media` / `code_media`. reset 행은 빈 값 |
| `started_at` | ISO8601. **이 값이 곧 그 실행의 `T0` 앵커다** — 원본 시각 → 재생 시각 매핑을 되짚을 수 있다 |
| `ended_at` | 완료 시 채운다. 진행 중이면 빈 값 |
| `status` | `running` → `completed` / `interrupted` / `reset` |

- 재생 시작 시 `status=running` 행을 append 하고, 종료 시 **그 행을 갱신**한다 (파일이 작아 전체 재작성).
- `--duration` 만료·`KeyboardInterrupt` → `interrupted`. 강제 종료되면 `running` 인 채로 남는다 — 사실
  그대로라 그것도 정보다.
- `--reset` 은 `scenario` 가 빈 `status=reset` 행을 남긴다. 기록과 실제 데이터가 어긋나 보일 때 이유가 된다.
- `.replay/` 는 `--reset` 대상이 아니므로 이력이 보존된다.

### 안티패턴 가드

- **`--reset` 의 방어는 "대상 한정"이다.** 지우는 것은 `<source_root>/{log,metric,trace}` 세 디렉터리
  뿐이다. `source_root` 자체를 `rmtree` 에 넘기지 마라. 경로가 어디로 잘못 잡히든 날아가는 것은 그 밑의
  그 세 폴더로 한정된다.
- **CWD 하위인지 검사하지 마라.** 상대경로는 정의상 항상 CWD 하위라 오설정을 걸러내지 못하면서
  (엉뚱한 CWD 에서도 `./var` → `<그 CWD>/var` 로 통과한다), ADR-004 가 허용한 절대경로 override 만
  거부한다. CWD 오설정은 기동 시 **디렉터리 부재 체크**가 잡는다 — 엉뚱한 데서 돌리면 `var/log` 가 없다.
- `var/` 를 커밋하지 마라 — `.gitignore` 가 막지만, pre-commit `check-added-large-files`(500KB)도 걸린다.

### 검증

- [ ] `tmp_path` 로 writer 단위 테스트 (`ADR-004` — fixture 파일 새로 만들지 말 것)
- [ ] `--reset` 두 번 실행 후 줄 수가 1회 실행과 같다 (중복 없음)
- [ ] `--reset` 없이 두 번 실행하면 줄 수가 2배 (append 확인)
- [ ] CSV 출력의 첫 줄이 원본 헤더와 동일
- [ ] **시나리오를 바꿔 이어 돌린 CSV 에 헤더가 1개뿐이다** — 모든 행이 시각으로 파싱된다
- [ ] `--reset` 후에도 `var/.replay/runs.csv` 가 남고 `status=reset` 행이 붙는다
- [ ] 정상 종료 시 해당 행의 `status` 가 `running` → `completed` 로 갱신된다

---

## Phase 4 — 스케줄러 + CLI

`demo/replayer/cli.py`, `demo/replayer/scheduler.py`.

### 구현

- CLI: `python -m demo.replayer <scenario> [--duration <초>] [--reset]`. `cli.py:11-28` 패턴 복사
  (`build_parser()` 분리, `main(argv) -> int`). `__main__.py` 가 `cli.main()` 을 호출한다.
- 스케줄러는 현재 시각이 `new_ts` 에 도달하면 그 줄을 쓴다. `--duration` 경과 시 정지하고, 생략 시
  데이터 끝까지 재생한다.
- **데이터 끝에 도달하면 정지한다.** 반복하지 않는다 — 되감으면 시각이 뒤로 튀어 원본에 없던 일이
  생긴다. 더 보고 싶으면 시나리오를 골라 다시 실행하면 되고, 그때 이어 쌓인다.
- **CSV 는 `new_ts` 로 정렬한 뒤** 병합한다. **로그는 파일 순서 그대로** 병합한다 (0-6').
- 병합은 파일별 스트림의 k-way merge 다 — 각 스트림 안의 순서는 절대 바꾸지 않고, 다음에 내보낼
  스트림만 고른다. 파일 단위로 순차 처리하면 시각축이 깨진다.
- **`pyproject.toml` 을 건드리지 않는다.** 콘솔 스크립트를 등록하면 wheel 에 들어가 실서비스 설치본에
  `rca-replay` 명령이 생긴다. 저장소 루트에서 `python -m demo.replayer` 로 실행한다.
- 시나리오 매핑 (`ADR-004` 승계):
  `cpu=Perf_CPU_Contention`, `kill_media=Svc_Kill_Media`, `code_media=Code_Stop_MediaService`
  → 접두어로 `datasets/sn/<모달리티>/` 하위 디렉터리를 찾는다 (폴더명에 타임스탬프가 붙어 exact match 아님).
- 경로 검증 1회: `dataset_root` 부재 시 **해석된 절대경로와 CWD 를 함께** 알리고 실패.

### 안티패턴 가드

- 시나리오를 경로에 인코딩하지 마라 (`ADR-004` — 인자로만 받고 출력은 항상 같은 `var/`).
- `Path(__file__).parents[N]` 로 저장소 루트를 계산하지 마라 (`ADR-004` 에서 명시적으로 기각됨).

### 검증

- [ ] `uv run python -m demo.replayer cpu --reset` 후 `var/{log,metric,trace}/` 에 원본과 같은 이름의 파일 생성
- [ ] `uv run python -m demo.replayer --help` 가 3종 시나리오와 `--duration` 을 보여준다
- [ ] 잘못된 CWD 에서 실행 시 절대경로+CWD 를 담은 명확한 실패
- [ ] `--duration` 생략 시 전체 재생, 지정 시 그 시각에 정지한다 — 데이터 끝에서 반복하지 않고 정지
- [ ] `cpu --duration 30` 후 `code_media --duration 30` 을 이어 돌리면 `runs.csv` 에 두 행이 남고,
      둘 다 `completed` 이며, `started_at` 이 증가한다

---

## Phase 5 — 통합 검증

**완료 기준: 재생 산출물이 원본에 충실한가** (0-5).

- [ ] 3종 전부 재생 성공: `for s in cpu kill_media code_media; do uv run python -m demo.replayer $s --reset; done`
- [ ] **누락 없음** — `var/` 각 파일의 줄 수 == 원본 파일의 줄 수
- [ ] **내용 보존** — 각 줄이 원본과 타임스탬프 외 바이트 동일
- [ ] **간격 보존** — 인접 타임스탬프 차이가 원본과 동일
- [ ] `var/` 파일 목록이 원본의 재생 대상 목록과 일치 (log 11~12 / metric 15 / trace 1)
- [ ] 안티패턴 grep:
  - `grep -rn "NormalizedEvent\|json.dumps" demo/replayer/` → 0건
  - `grep -rn "summary.txt\|metadata.txt\|all_traces.json" demo/replayer/` → 0건
  - `grep -rn "parents\[" demo/replayer/` → 0건
- [ ] `uv run pytest` / `uv run ruff check .` 통과
- [ ] `git status` 에 `var/` 가 안 잡힌다

---

## 열린 문제

없음.
