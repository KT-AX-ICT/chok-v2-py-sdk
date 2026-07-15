# coverage_data — 코드 커버리지

시나리오 실행 후 남는 커버리지 아티팩트. 연구 단계에서 `coverage_dir_missing` 신호의 근거였다.

**데이터를 커밋하지 않는다** (135MB). [ADR-003](../../../docs/decisions/ADR-003-realtime-signal-scope.md) 에서 이 신호를 실시간 파이프라인 **제외**로 결정했다 — 시나리오 종료 후에만 관측 가능해 30초 루프가 볼 수 없기 때문이다. 이 폴더는 구조 유지용 README 만 둔다.

전체 구성과 받는 방법은 [../README.md](../README.md), 배치 결정은
[ADR-004](../../../docs/decisions/ADR-004-replayer-data-layout.md) 참조.
