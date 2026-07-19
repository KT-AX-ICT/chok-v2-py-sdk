# collectors — ① 수집

원천 소스(log·metric·trace)를 tail 해 **정규화 이전의 원시 레코드**(`RawBatch`)를 산출한다.
설계 근거는 [계획 03](../../../docs/plans/03-tail-rework-normalization.md) §1 참조.

- `base.Collector` — 추상 인터페이스. `poll() -> RawBatch` 를 30초 루프마다 호출한다.
- `tail.LineTailCollector` — 공통 구현. `<source_root>/<modality>/<pattern>` 을 파일별
  **byte offset** 으로 이어 읽는다 (미완성 줄 유예, truncate 복구, 삭제 레이스 방어).
  라인 해석은 서브클래스 훅 `_frame` 이 담당하고, `_source`(파일명) 주입과
  `RawBatch.sources`(존재 파일 목록) 전달은 공통층이 한다.
- `tail.CsvTailCollector` — 파일 맨 앞 헤더를 기억해 각 행을 `{컬럼명: 값}` dict 로
  프레이밍한다. 헤더는 offset 이어읽기 특성상 첫 배치에만 나타나므로 상태를 가진
  collector 가 기억한다 (계획 03 N1). truncate 시 헤더 재학습.
- `log.LogCollector`(`*.log`, `{"raw": 라인}`) / `metric.MetricCollector`·
  `trace.TraceCollector`(`*.csv`, 컬럼 dict) — 프로덕션 전환은 `poll()` 교체로 흡수 (ADR-004).
- `tail.validate_source_layout()` — 기동 시 경로 검증 헬퍼 (호출은 Runner 소관, ADR-004
  "디렉터리 부재 체크").

소스 present/missing **판정**은 여기서 하지 않는다 — 관측 사실만 전달하고 판정은
`normalization/` 이 전담한다 (ADR-005).
