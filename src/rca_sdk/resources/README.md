# resources — 동봉 리소스

패키지에 함께 배포하는 정적 리소스를 둔다.

- `baselines/` — baseline 프로파일 JSON. `trigger/baseline.py` 로더가 읽는다.

> baseline 을 동봉 프로파일로 할지, 런타임 self-baseline 으로 할지, 프로파일 스키마를 어떻게
> 잡을지는 **미확정(ADR-002)**. 현재 JSON 은 로더 동작 확인용 최소 placeholder 이며 실제
> 기준치·필드는 팀 확정 후 채운다.

참고: [docs/decisions/ADR-002-baseline-source.md](../../../docs/decisions/ADR-002-baseline-source.md)
