# metric_data — 메트릭

시나리오별 시계열 메트릭. 리플레이어가 이걸 읽어 `var/metric/<service>.jsonl` 로 재생한다. baseline 편차 감지(ADR-002)의 입력이다.

커밋된 시나리오는 MVP 3종뿐이다:

| 시나리오 | 디렉터리 |
|---|---|
| cpu | `Perf_CPU_Contention_*` |
| kill_media | `Svc_Kill_Media_*` |
| code_media | `Code_Stop_MediaService_*` |

나머지 10종은 커밋하지 않는다 (`metric_data/` 전체 54MB).

전체 구성과 받는 방법은 [../README.md](../README.md), 배치 결정은
[ADR-004](../../../docs/decisions/ADR-004-replayer-data-layout.md) 참조.
