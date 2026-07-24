# datasets/sn — SN 전체 데이터셋

리플레이어가 읽는 원본이다 (`RCA_DATASET_ROOT`). 리플레이어는 이걸 타임시프트 재생해 `var/` 로
원천 로그를 만들어내고, SDK tailer 가 그 `var/` 를 관측한다. 배치와 역할은 [ADR-004](../../docs/decisions/ADR-004-replayer-data-layout.md) 참조.

## 구성

13개 시나리오 × 5개 모달리티. 디렉터리명은 `<시나리오>_<수집시각>_<종류>_<종료시각>` 형태다.

| 폴더 | 내용 | git |
|---|---|---|
| `log_data/` | 서비스별 로그 | 정상 baseline + MVP 3종 |
| `metric_data/` | 시계열 메트릭 | 정상 baseline + MVP 3종 |
| `trace_data/` | 분산 트레이스 스팬 | 정상 baseline + MVP 3종 |
| `api_responses/` | OpenAPI 응답 기록 | 커밋 안 함 |
| `coverage_data/` | 코드 커버리지 아티팩트 | 커밋 안 함 |

## 출처와 라이선스

- 출처: [EvoTestOps/AnoMod](https://github.com/EvoTestOps/AnoMod) — TT(Train-ticket,
  기차표 예매)·SN(Social Network, SNS)을 실제 구동해 장애를 주입·수집한 데이터셋
- 본체: [Zenodo DOI 10.5281/zenodo.18342898](https://doi.org/10.5281/zenodo.18342898)
- 라이선스: MIT, Copyright (c) 2025 EvoTestOps
  ([원문](LICENSE-AnoMod))

이 저장소에는 SN의 정상 baseline과 MVP 장애 3종에서 실시간 SDK가 사용하는
log/metric/trace만 원본 바이트 그대로 포함한다. 원본 timestamp는 파일에서 바꾸지 않고,
데모 실행 시 replayer/simulator가 런타임 출력(`var/`)에만 현재 시각으로 이동해 쓴다.

## 커밋 범위

전체는 833MB / 9,009 파일이라 git 에 넣지 않는다. **MVP 3종 시나리오의 log/metric/trace 만** 커밋한다
(기존 95 파일). 여기에 무한 데모의 정상 흐름을 위해 `Normal_Baseline_*`의
log/metric/trace 32개 파일(57,968,366 bytes)을 추가한다. 클론만으로 정상→장애 순환 데모가
도는 것이 기준선이다.

| 시나리오 | 디렉터리 접두어 | 대응 결함 |
|---|---|---|
| cpu | `Perf_CPU_Contention_*` | CPU 경합 |
| kill_media | `Svc_Kill_Media_*` | MediaService 강제 종료 |
| code_media | `Code_Stop_MediaService_*` | MediaService 코드 결함 |

정상 baseline의 디렉터리 접두어는 `Normal_Baseline_*`이다. simulator는 이 시간축을
연속 소비하고 끝에 도달했을 때만 처음으로 돌아간다.

`api_responses/`, `coverage_data/` 는 시나리오 무관하게 전부 제외한다. 리플레이어가 읽지 않고,
coverage 신호는 [ADR-003](../../docs/decisions/ADR-003-realtime-signal-scope.md) 에서 실시간 파이프라인
제외로 결정했다.

제외 규칙은 저장소 루트 `.gitignore` 에 있다. 시나리오를 추가하려면 거기에 `!datasets/sn/<모달리티>/<접두어>_*/`
를 더한다.

## 나머지 데이터 받기

커밋되지 않은 시나리오와 모달리티는 별도 공유한다. 받아서 이 디렉터리 구조 그대로 풀면 된다 —
`.gitignore` 가 무시하므로 커밋에 섞이지 않는다.

> TODO: 공유 위치(사내 스토리지/드라이브 링크)와 받는 절차를 여기에 적는다.
