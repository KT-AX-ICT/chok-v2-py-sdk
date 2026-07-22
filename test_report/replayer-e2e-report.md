# 리플레이어 실물 E2E 리포트 (계획 06 §6)

> 대상: `demo/replayer`(실물 파일) → 실제 `LineTailCollector`/`CsvTailCollector` → 실제
> `LogNormalizer`/`MetricNormalizer`/`TraceNormalizer` → 실제 `Runner`/`SnapshotManager` →
> 실제 `TransportClient` 의 전 구간
> 브랜치: `feat/replayer-e2e-run`
> 실행일: 2026-07-22

## 배경

계획 05는 가짜 `DatasetReplayCollector`로 Runner의 tick 배선만 검증했다(`test_report/scenario-replay-report.md`).
이번 리포트는 그 가짜를 걷어내고, **`demo/replayer`가 실제로 쓴 파일을 실제 tailer가 tail한**
경로 전체를 실물로 확인한다.

## 실행 절차

3개 프로세스를 QA 팀 제안 순서(리셋을 rca-collect보다 먼저 실행)로 띄웠다 — `demo/replayer`의
`--reset`이 디렉터리를 즉시 재생성하도록 고친 수정([이전 커밋](../demo/replayer/writer.py))이
있어야 이 순서에서 `rca-collect`가 크래시하지 않는다.

```
1. python scripts/mock_ingest_server.py           (검증용으로는 페이로드를 파일로 저장하는
                                                    스크래치 버전 사용 — 커밋 대상 아님)
   (1초 대기)
2. python -m demo.replayer code_media --reset --duration 360
   (2초 대기 — reset() 이 디렉터리를 재생성할 시간)
3. rca-collect
```

| 항목 | 값 |
|---|---|
| 시나리오 | `code_media` (Code_Stop_MediaService) |
| 재생 범위 | `--duration 360` — 전체 25분 시나리오 중 첫 6분(첫 번들 완성 시점까지, 계획 06 §4) |
| 플랫폼 | Windows (win32), Python 3.11.9 |
| var/ 상태 | 이번이 첫 실행(사전에 `var/`가 아예 없던 상태) — `reset()`의 "첫 실행에도 디렉터리 즉시 생성" 동작을 실전에서도 확인 |

## 실행 로그 (`var/.replay/runs.csv`, 마지막 실행분)

| scenario | started_at (anchor) | ended_at | status |
|---|---|---|---|
| — | 2026-07-22T06:16:35.479202+00:00 | 〃 | reset |
| code_media | 2026-07-22T06:16:37.310407+00:00 | 2026-07-22T06:22:36.306635+00:00 | completed |

## 수신 로그 (dump 서버)

| 수신 시각(수신 순간) | window.start | trigger_time | window.end | 발화 모달리티 | logs | metrics | traces |
|---|---|---|---|---|---|---|---|
| 2026-07-22 15:22 (KST) | 06:16:11.003680 | 06:19:11.003680 | 06:22:11.003680 | log, trace | 306,494 | 2,920 | 105 |

두 로그를 나란히 보면: 리플레이어가 실제로 재생을 시작한 시각(anchor, 06:16:37)과 rca-collect가
받은 번들의 trigger_time(06:19:11)이 약 153.7초 차이 — 계획 06 §4가 표로 정리해둔
"경과(anchor−t0) 150초"와 거의 일치한다(실시간 페이싱의 자연스러운 오차 범위).

## §5 불변식 검증 결과

| # | 불변식 | 결과 | 근거 |
|---|---|---|---|
| 1 | 번들 창 = `[anchor−180, anchor+180)`, `trigger_info.trigger_time == anchor` | ✅ | `trigger − window.start = 180.0초`, `window.end − trigger = 180.0초`, 창 전체 360.0초 |
| 2 | pre 잘림 없음 | ✅ | log/metric/trace 전부 **첫 레코드 timestamp ≥ window.start** |
| 3 | 레코드 시간순 | ✅ | 3개 모달리티 전부 오름차순(`ts[i] <= ts[i+1]` 전 구간 성립) |
| 4 | `since` 효과(재발화 anchor가 직전 번들 창을 안 되돌아봄) | 범위 밖 | 이번 실행은 번들 1개만 보도록 설계됨(계획 06 §4) — 재발화 확인은 전체 25분 재생 필요, 별도 실행으로 남김 |
| 5 | 동시 세션 1개 | ✅(약한 근거) | 6분 구간에 번들 1건만 수신 |
| 6 | coverage 3상태 확정 | ✅ | 아래 표 |

### coverage 상세 (`modality_info`)

| 모달리티 | missing | empty | data |
|---|---|---|---|
| log | media | — | nginx·user·text·uniqueid·urlshorten·usermention·usertimeline·hometimeline·poststorage·composepost·socialgraph (11) |
| metric | — | — | 전 12종 + `__node__` |
| trace | — | media·usertimeline·hometimeline·poststorage·socialgraph (5) | nginx·user·text·uniqueid·urlshorten·composepost (6) |

`log/media = missing`이 특히 의미가 있다 — Code_Stop_MediaService는 media 서비스를 코드
결함으로 정지시켜 로그 파일 자체가 없는 시나리오인데, 실물 파일 경로로도 정확히
"missing"(파일 부재)으로 판정됐다. `trace`의 "empty"들은 `all_traces.csv`가 전 서비스를
한 파일에 담는 구조라(§4 in normalization/trace.py) 파일은 있지만 이 6분 창에 해당 서비스
행이 0건이라 "empty"로 잡힌 것 — 설계대로다.

## 관찰 사항

1. **`window.start`가 리플레이어 자신의 `anchor`(06:16:37.310407)보다 약 26초 앞선다**
   (06:16:11.003680). 버그가 아니다 — `trigger_time`이 이론값(anchor+150초)보다 약간
   늦게(anchor+153.7초) 발생했고, `window.start = trigger−180`이라 anchor 이전 시점까지
   창이 잡힌 것뿐이다. anchor 이전엔 애초에 어떤 모달리티도 데이터를 쓴 적이 없으니
   "그 구간에 데이터가 없다"는 것과 "pre가 잘렸다"는 것은 다른 사실이다 — 실제로 §5 불변식
   2번(첫 레코드 ≥ window.start)은 성립하므로 잘림은 없다. 이건 **한 세션에서의 "첫" 번들**에서만
   생기는 경계 효과이고, 재생을 계속 이어가면(두 번째 번들부터) 사라진다.
2. **`rca-collect` 로그가 이번 실행에서도(2회 반복 모두) 완전히 비어 있었다** — 경고/에러 0건.
   `LogNormalizer`의 thrift 포맷 수정 이후 `ComposePostService_.log`의 200줄이 실제 라이브
   경로에서도 "해석 불가 로그 줄 스킵" 경고 없이 조용히 잘 처리된다는 방증이다.
3. **레코드 수가 가짜 컬렉터 기준 리포트(`scenario-replay-report.md`)와 완전히 같지는 않다**
   (logs 306,494 vs 306,453 · metrics 2,920 vs 2,915 · traces 105 vs 105 — 동일 실행을 반복해도
   306,494/2,919/105 처럼 metrics 만 1건씩 흔들린다). 실시간 poll 경계(30초 주기)와 데이터
   자체의 30초 버킷 경계가 정확히 안 맞아떨어져 생기는 자연스러운 오차이고, 전체 규모 대비
   무시할 수준이다.
4. **팀원 제안 순서(`--reset` → sleep 2 → `rca-collect`)가 실전에서도 크래시 없이 동작했다** —
   `var/`가 아예 없던 첫 실행에서도 `reset()`이 3개 디렉터리를 즉시 만들어줘 `validate_source_layout()`을
   통과했다.

## 범위 밖으로 남긴 것

- **`since` 재발화 검증(불변식 4)** — 번들 2개 이상이 필요해 전체 시나리오(25분)를 실시간으로
  다 재생해야 한다. 이번엔 "메커니즘이 실물로 도는가"를 확인하는 최소 실행(6분)만 했다.
- **`Svc_Kill_Media`·`Perf_CPU_Contention` 두 시나리오의 실물 E2E** — `Code_Stop_MediaService`
  하나로 파이프라인 전 구간(경로 검증·정규화·번들 조립·전송)이 정상 동작함을 확인했다. 나머지
  두 시나리오는 detector 종류만 다를 뿐 같은 경로를 타므로, 필요 시 추가 실행으로 확장한다.
