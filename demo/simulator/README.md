# 무한 데모 시뮬레이터

`datasets/sn`에 포함된 AnoMod SN 원본을 이용해 normal과 장애 3종을 계속 흘리는 데모
producer다. 기존 단발 `demo.replayer`와 실서비스 진입점 `rca-collect`는 변경하지 않는다.

```text
Normal_Baseline 60초 → cpu 330초
→ Normal_Baseline 60초 → kill_media 330초
→ Normal_Baseline 60초 → code_media 330초 → 반복
```

normal은 전체 원본 시간축을 연속 소비하고 끝에서만 처음으로 돌아간다. 장애 구간 330초는
현재 detector의 첫 발화와 post window 180초를 포함한다. 파일은
`RCA_SOURCE_ROOT/{log,metric,trace}`에 append만 하며 실행 중 삭제하거나 truncate하지 않는다.
원본 CSV header가 같은 파일명끼리 다를 때는 행이나 header를 변형하지 않고, 충돌하는 쪽만
`<원본명>__<장애명>.csv`로 분리한다. 현재 AnoMod 원본에서는 `kill_media`의
`socialnet_container_memory.csv`가 이에 해당한다.

각 AnoMod 세트는 독립 환경을 기동해 수집했으므로 첫머리에 cold-start `Starting...` 로그가
있다. 이를 그대로 이어 붙이면 baseline과 CPU의 정상 기동 1회씩이 restart 2회로 오인된다.
simulator는 원본 파일을 수정하지 않고 **baseline 출력에서만** 이 cold-start 줄을 생략한다.
`kill_media` 원본에는 이 필터를 적용하지 않아 media의 실제 기동+재기동 2회는 그대로 탐지된다.

## 실행

저장소 루트에서 한 명령으로 simulator와 collector를 함께 실행한다.

```bash
scripts/run_demo_server.sh
```

정상 구간 길이만 바꾸려면:

```bash
scripts/run_demo_server.sh --baseline-sec 300
```

스크립트는 `RCA_SOURCE_ROOT`가 없으면 `var/demo-runs/<실행ID>`를 새로 만들고 두 프로세스에
공유한다. 사용자가 직접 지정한 경로는 비어 있어야 한다. 이는 collector의 tail offset이
프로세스 메모리에만 있어 기존 파일을 재실행 때 처음부터 읽는 문제를 막기 위한 정책이다.

> TODO(timestamp-contract): SDK/FastAPI/Spring timestamp wire 계약은 담당 서비스에서 별도로
> 정리해야 한다. 현재 계약 상태에서는 SDK trigger와 bundle 생성까지 성공해도 Spring 저장이
> 422로 끝날 수 있다. 이 simulator 변경은 timestamp 직렬화 계약을 수정하지 않는다.
