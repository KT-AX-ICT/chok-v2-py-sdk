# 리플레이어 (demo/replayer)

`datasets/sn` 의 SN 원본을 읽어 **타임스탬프만 파싱**하고, 현 시각에 맞춰 **타임시프트**한 후, **원본 줄을 바이트 그대로** `var/` 에 "실서비스 측 원천 로그"를 만들어내는 데모 도구.   
SDK 콜렉터(tailer)가 관측할 데이터를 재현한다.

역할 구분:   
> 포맷 변경 금지, 서비스별로 재분할 금지, 파일명 변경 금지

- 경로·레이아웃 계약: [ADR-004-replayer-data-layout.md](../../docs/decisions/ADR-004-replayer-data-layout.md)
- 설계·구현 계획: [docs/plans/01-replayer.md](../../docs/plans/01-replayer.md)
  ([흐름도](../../docs/plans/01-replayer-flow.svg))

> **왜 `demo/` 인가** — 리플레이어는 데모용 데이터 공급기이지 SDK 의 일부가 아니므로, wheel 에 포함되지 않도록 `src/rca_sdk/` 밖 `demo/` 에 둔다. 콘솔 스크립트도 등록하지 않는다 — 테스트는 `python -m demo.replayer` 로 실행한다.

---

## 동작 원리

```
datasets/sn/{log,metric,trace}_data/<시나리오>_*/   ──읽기──▶  리플레이어  ──쓰기──▶  var/{log,metric,trace}/
        (불변 아카이브, 원본 시각)                                              (현재 시각으로 시프트, tailer 관측 대상)
```

1. **탐색** — 시나리오 인자로 `datasets/sn/` 에서 재생 대상 파일(`*_.log`, metric CSV,
   `all_traces.csv`)을 찾는다.
2. **t0 측정** — 전 모달리티를 통틀어 가장 이른 실측 시각을 기준점 `t0` 으로 잡는다.
   모달리티마다 따로 잡지 않는다 (원본에 없던 정렬이 생기는 것을 막는다).
3. **시프트 + 병합** — `new_ts = 재생시작시각 + (원본시각 - t0)`. 원본의 간격을 그대로 보존하면서
   전 소스를 시각순으로 k-way 병합한다.
4. **페이싱** — 현재 시각이 `new_ts` 에 닿을 때까지 기다렸다가, 원본 줄의 타임스탬프 자리만
   새 값으로 치환해 `var/` 에 append 한다. 데이터 끝에 도달하면 정지한다(반복 없음).

---

## 사전 준비

- **uv** 로 개발 세팅(저장소 루트 [README](../../README.md) 참조). `.python-version`·`uv.lock` 이
  커밋돼 있어 인터프리터·의존성이 고정된다:
  ```bash
  uv sync --extra dev
  ```
  이후 모든 명령은 `uv run <명령>` 으로 실행한다(가상환경 자동 활성). `uv run` 이 `uv.lock` 과
  자동으로 동기화하므로 매번 sync 를 먼저 부를 필요는 없다.
- **데이터셋** — MVP 3종 시나리오의 log/metric/trace 는 저장소에 커밋돼 있어 클론만으로 돈다.
  (나머지 시나리오·모달리티는 별도 공유. [datasets/sn/README](../../datasets/sn/README.md) 참조)
- **반드시 저장소 루트에서 실행한다.** 경로(`var/`, `datasets/sn`)는 `.env`·`config.py` 위치가
  아니라 **작업 디렉터리(CWD) 기준**으로 풀린다. 다른 데서 띄우면 데이터를 못 찾고 실패한다
  (ADR-004 참조).

---

## 실행

```bash
uv run python -m demo.replayer <시나리오명> [옵션]
```

### * 시나리오

| 인자          | SN 결함군                  | 내용                          |
|---------------|----------------------------|-------------------------------|
| `cpu`         | `Perf_CPU_Contention`      | CPU 경합                      |
| `kill_media`  | `Svc_Kill_Media`           | media 서비스 강제 종료        |
| `code_media`  | `Code_Stop_MediaService`   | media 서비스 코드 결함 정지   |

### * 옵션

| 옵션              | 설명                                                            |
|-------------------|-----------------------------------------------------------------|
| `--duration SEC`  | 이 초만큼만 재생하고 정지 (생략 시 데이터 끝까지). 재생 시간축 기준. |
| `--reset`         | `var/{log,metric,trace}` 를 비우고 시작. 실행 이력은 보존.       |

### 예시

```bash
# cpu 시나리오를 데이터 끝까지 재생
uv run python -m demo.replayer cpu

# 깨끗한 상태에서 kill_media 를 60초만 재생
uv run python -m demo.replayer kill_media --reset --duration 60

# 중단하려면 Ctrl+C — 실행 이력에 status=interrupted 로 남는다
```

실행하면 다음처럼 진행 상황을 알린다:

```
재생: cpu — 파일 27개, t0=2025-11-03T22:26:01+00:00, 끝까지
완료: 1,234,567줄 → C:\chok-v2-py-sdk\var
```

> **페이싱은 실시간이다.** trace 는 `t0+126초` 이후에야 시작하는 등, 모달리티마다 첫 데이터까지
> 시간이 걸린다. 전체를 빠르게 훑고 싶으면 `--duration` 으로 구간을 자르거나, 검증 목적이라면
> 통합 테스트(fast clock)를 쓴다.

---

## 출력

콜렉터가 소유하는 모달리티 디렉터리 하나씩, **파일명과 내용은 원본 그대로다.**

```
var/
├── log/      # <Service>_.log (boost 평문 / nginx error_log / thrift)
├── metric/   # *.csv (헤더 + 행)
├── trace/    # all_traces.csv (헤더 + 행)
└── .replay/
    └── runs.csv   # 실행 이력
```

- CSV 헤더는 **파일이 없거나 0바이트일 때만** 쓴다. 시나리오를 바꿔 이어 돌려도 헤더가 파일
  중간에 끼어들지 않는다.
- `var/` 는 런타임 산출물이라 커밋하지 않는다(매 실행 타임스탬프가 바뀌어 diff 가 무의미).

### 이어 돌리기 가능

재생은 append 이고 재생 시작 시각은 매 실행 `now()` 라, 시나리오를 바꿔 다시 실행하면 앞 실행 뒤에 시각순으로 이어 쌓인다. tailer 는 파일 끝에 붙는 줄을 그대로 따라간다. `--reset` 은 깨끗한 상태에서 다시 보기 위한 **선택적 정리**기능이다. 반드시 해야하는 옵션은 아님.

### 실행 이력 — `var/.replay/runs.csv`

시나리오 실행 이력과 리셋 이력을 확인할 수 있는 파일

| 컬럼         | 뜻                                                     |
|--------------|--------------------------------------------------------|
| `scenario`   | 재생한 시나리오                                        |
| `started_at` | 재생 시작 시각 = 그 실행의 **`T0` 앵커**(원본↔재생 매핑) |
| `ended_at`   | 종료 시각                                              |
| `status`     | `running` / `completed` / `interrupted` / `reset`      |

`.replay/` 는 `--reset` 대상이 아니라 이력이 보존되며, 리셋은 `status=reset` 행으로 남는다.
강제 종료되면 행이 `running` 인 채 남는다 — 사실 그대로다.

---

## 테스트

리플레이어 테스트는 `demo/replayer/tests/` 에 있다(저장소 루트 `pytest` 기본 대상인 `tests/` 와 별개).

```bash
uv run python -m pytest demo/replayer/tests
```

> `pytest` 가 아니라 **`python -m pytest`** 다. `demo` 는 wheel 밖이라 설치 패키지가 아니고,
> `python -m` 이 CWD(저장소 루트)를 경로에 넣어줘야 `from demo.replayer ...` import 가 풀린다.

통합 테스트(`test_integration.py`)는 fast clock 으로 끝까지 돌려, 세 모달리티 전부에 대해
**누락 없음·내용 보존(바이트)·간격 보존**을 원본과 대조해 검증한다.

---

## 구성

| 모듈            | 역할                                                         |
|-----------------|--------------------------------------------------------------|
| `cli.py`        | `python -m demo.replayer` 진입점 — 인자 파싱, 오케스트레이션 |
| `scenarios.py`  | 시나리오 → 데이터셋 파일 탐색                                |
| `readers.py`    | 원본에서 **타임스탬프만** 파싱 (boost/nginx/thrift/csv)      |
| `shift.py`      | 시각 평행이동 + 줄 안 타임스탬프 바이트 치환                 |
| `scheduler.py`  | k-way 병합 + 실시간 페이싱                                   |
| `writer.py`     | `var/<모달리티>/<파일명>` 에 append (헤더 멱등)              |
| `runlog.py`     | `var/.replay/runs.csv` 실행 이력                             |
