# 계획 06 — 리플레이어 실연동 E2E 검증

계획 05 R5("파일 재생(E2E)은 이번 범위 밖")에서 미뤄둔 부분을 다룬다. 계획 05는 가짜
`DatasetReplayCollector`로 Runner의 tick 배선과 시나리오별 발화를 검증했다 — 이번 계획은
**진짜 리플레이어(`demo/replayer`, PR #4 `feat/replayer`)가 `var/`에 쓴 실제 파일을 실제
`Collector`가 tail하는** 경로 전체가 실제로 동작하는지를 1x 실시간 기준으로 확인한다.

- 선행: [계획 05](05-runner-scenario-replay.md) (Runner 배선·시나리오 매트릭스), [계획 02](02-collector-normalization-buffer.md) (Runner 통합·경로 검증을 이 단계로 미뤄둠)
- 관련: [ADR-004](../decisions/ADR-004-replayer-data-layout.md) (경로 레이아웃·기동 시 경로 검증 요구)
- 전제: `demo/replayer`는 PR #4에 존재하며(아직 `main` 미병합), 이 계획에서는 그 코드가 이미
  받아와져 있다고 가정하고 진행한다.

## 범위

**포함**: `rca-collect` CLI 배선, Runner 기동 시 경로 검증, mock ingest 서버, 시나리오 3종 수동
E2E 실행 절차, 계획 05 §5 불변식의 실제 파일 기준 재확인.

**범위 밖**: 리플레이어 배속 정책(R1 — 근거는 아래), 자동화된 pytest E2E(계획 05 R5와 같은
이유 — 실시간 20분+ 소요는 CI에 부적합).

## 결정 사항

| # | 결정 | 근거 |
|---|---|---|
| R1 | 배속(1x/5x/10x)은 다루지 않는다 — 1x 실시간만 검증 | `demo/replayer/scheduler.py`의 `replay()`를 직접 확인한 결과 배속 인자 자체가 없다. `new_ts = anchor + (원본_ts − t0)`로 항상 실제 시각에 맞춰 `sleep`한다. ADR-004의 "배속 미결"은 아직 없는 기능에 대한 질문이라 지금은 판단 대상이 아니다 |
| R2 | `cli.py:main()`을 `build_runner(settings).run(once=args.once)` 호출로 교체 | 현재 `cli.py:21-23`은 print만 하고 반환한다. `runtime/runner.py`의 `build_runner()` 팩토리는 이미 완성돼 있고 `test_runner_wiring.py`로 검증도 됐는데 CLI가 그걸 호출하지 않는다 — 이 상태로는 애초에 연동할 대상이 없다 |
| R3 | `build_runner()` 기동 시 `settings.source_root` 및 그 하위 `log/`·`metric/`·`trace/` 디렉터리 존재를 검증한다. 실패 시 해석된 절대경로와 CWD를 메시지에 담아 즉시 실패 | ADR-004가 이미 요구한 사항("경로 부재 = 설정 오류, 기동 시 실패")인데 `runner.py`에는 아직 없다. `Collector.poll()`은 없는 경로를 봐도 예외 없이 0건을 내므로, 검증이 없으면 "경로가 틀림"과 "이상 없음"이 로그만 봐서는 구분되지 않는다 |
| R4 | `collect_endpoint`(기본 `http://localhost:8000/ingest`) 자리에 표준 라이브러리만 쓴 최소 mock HTTP 서버를 둔다. 요청을 받으면 200을 돌려주고, 번들 요약(window, 발화 detector, 모달리티별 레코드 수)을 stdout에 로그로 남긴다 | 지금 `collect_endpoint`에는 실제로 받을 서버가 없다. mock 서버를 두면 `SubmissionResult` 계약까지 실제로 검증된다 |
| R5 | 실행은 3개 터미널 수동 절차로 한다 — ① mock 서버 ② `python -m demo.replayer <scenario>` ③ `rca-collect` | `demo/replayer/cli.py`는 의도적으로 `pyproject.toml`에 콘솔 스크립트로 등록돼 있지 않다("등록하면 wheel에 들어가 실서비스 설치본에 `rca-replay`가 생긴다"). 그 설계를 그대로 따른다 |

## §1. mock ingest 서버

표준 라이브러리(`http.server` 등)만 사용하는 별도 스크립트로 둔다 — `demo/replayer`가 `pyproject.toml`에
등록되지 않은 것과 같은 이유로, 이것도 패키지 설치본에 딸려가면 안 된다. 위치는 `scripts/mock_ingest_server.py`.

- `POST /ingest` 수신 → `SnapshotBundle` JSON을 파싱해 `window`, 발화한 `trigger_info`, 모달리티별
  레코드 수를 한 줄로 stdout에 남기고 `200`을 돌려준다.
- 포트는 `collect_endpoint` 기본값(`8000`)에 맞춘다. 별도 설정 파일 없이 고정 포트로 시작 — 이번
  계획은 로컬 수동 검증이 목적이라 설정 가능성보다 즉시 실행 가능성이 우선이다.

## §2. CLI 배선

`cli.py:18-24`를 아래 형태로 교체한다.

```python
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    runner = build_runner(settings)
    runner.run(once=args.once)
    return 0
```

`Runner(settings)` 형태의 기존 TODO 예시 주석은 현재 `Runner.__init__` 시그니처(`sources`/`buffer`/
`detectors`/`snapshot`/`transport` 키워드 인자 요구)와 맞지 않으므로 함께 제거한다.

## §3. Runner 경로 검증

`build_runner()` 진입 시점(구성요소 조립 전)에 아래를 확인한다.

```
resolved = Path(settings.source_root).resolve()
for modality in ("log", "metric", "trace"):
    if not (resolved / modality).is_dir():
        raise RuntimeError(
            f"source_root 하위 디렉터리 없음: {resolved / modality}\n"
            f"  CWD = {Path.cwd()}\n"
            f"  저장소 루트에서 실행하고 있는지 확인하세요."
        )
```

디렉터리는 있으나 파일이 없거나 신규 라인이 없는 경우는 정상(0건)으로 그대로 둔다 — ADR-004가 이미
구분해 둔 기준 그대로다. 검증은 기동 시 1회만 하고 `tick()` 루프 안에서는 반복하지 않는다(설정은
실행 중 바뀌지 않음).

## §4. 시나리오별 실행 절차

계획 05 §1·§4의 시나리오 매트릭스를 그대로 쓴다. 첫 번들의 anchor 시각은 이미
`test_report/scenario-replay-report.md`(계획 05 실측 결과)에 나와 있다 — `anchor − 기준시(t0)`는
어느 Collector가 읽든 데이터셋 자체가 갖는 값이라, 가짜 Collector로 잰 것이라도 실제 리플레이어의
1x 재생에 그대로 옮겨 쓸 수 있다. 새로 스트리밍해서 실측할 필요는 없다.

| 시나리오 | 전체 스팬 | 기준시(t0) | 첫 번들 anchor | 경과(anchor−t0) | 최소 재생 시간(경과+post 180초) |
|---|---|---|---|---|---|
| `Svc_Kill_Media` | 20분 | `00:01:50` | `00:03:41` | 111초 | 291초 (4분 51초) |
| `Code_Stop_MediaService` | 25분 | `02:56:21` | `02:58:51` | 150초 | 330초 (5분 30초) |
| `Perf_CPU_Contention` | 20분 | `22:26:39` | `22:28:45` | 126초 | 306초 (5분 6초) |

전체 시나리오를 끝까지 재생할 필요는 없다 — 번들 1개(anchor±180초 창)가 완성되는 시점까지만
봐도 계획 05 §5의 불변식을 확인할 수 있다. 세 시나리오 모두 6분(`--duration 360`)이면 여유
있게 첫 번들이 완성된다.

실행 순서(저장소 루트에서):

```
# 터미널 1
python scripts/mock_ingest_server.py

# 터미널 2 — var/ 초기화 후 재생
python -m demo.replayer <scenario> --reset --duration 360

# 터미널 3 — 실제 관측 루프
rca-collect
```

`rca-collect`는 터미널 2가 첫 줄을 쓰기 시작한 뒤에 띄운다 — 먼저 띄워도 §3 경로 검증만 통과하면
디렉터리 자체는 있으므로 실패하지 않지만, 파일이 아직 없으면 tail이 0건만 내다가 리플레이어가
파일을 만든 이후에야 관측이 시작된다.

## §5. 검증할 불변식

계획 05 §5의 불변식 목록을 그대로 가져와, 이번에는 **전 구간을 실물로** 재확인한다. 계획 05는
Runner의 tick 배선만 검증하면 됐기 때문에 `DatasetReplayCollector`라는 가짜 Collector로 정규화
배치를 직접 주입했다 — 실제 파일도, 실제 tailer도 거치지 않았다. 이번 계획은 그 가짜를 걷어내고
실제 `demo/replayer`가 쓴 파일을 실제 `LogCollector`/`MetricCollector`/`TraceCollector`가 tail한
결과로 아래를 확인한다.

1. 번들 창 = `[anchor−180, anchor+180)`, `trigger_info.trigger_time == anchor`
2. pre 잘림 없음
3. 레코드 시간순
4. `since` 효과 — 번들 N+1의 발화 근거가 번들 N의 창 안에 있지 않음
5. 동시 세션 1개
6. coverage 3상태 확정

계획 05와 다른 점은 시각 처리 경로다 — 계획 05 R3는 "타임스탬프를 시프트하지 않는다"(버퍼가
watermark 기준이라 원본 시각 그대로 재생)였지만, 이번엔 **리플레이어가 실제로 시각을 현재로
재기록**한 파일을 실제 tailer가 읽는다. 계획 02 C4(`observed_from/until`은 poll 시각 기준)가
"poll 시각 ≈ 데이터 시각"이라 가정한 부분이 실제로 성립하는지가 이번에 처음 실측된다.

## §6. 결과 기록

리플레이어의 실행 로그(`RunLog` — 재생 시작/종료 시각)와 mock 서버의 수신 로그(수신 시각, window,
trigger)를 나란히 남긴다. 두 로그의 타임스탬프를 대조하면 "언제 재생했고 언제 몇 번째 번들을
받았는지"가 눈으로 확인된다. 위치는 `test_report/replayer-e2e-report.md` — 계획 05가 만든
`test_report/scenario-replay-report.md`와 같은 디렉터리, 다른 파일.

## §7. 작업 순서

1. mock ingest 서버 작성 (§1)
2. `cli.py` 배선 (§2)
3. `Runner`/`build_runner()` 경로 검증 추가 (§3)
4. 시나리오 3종 각 1회 수동 E2E 실행, 불변식 확인 (§4·§5)
5. 결과 리포트 작성 (§6)
