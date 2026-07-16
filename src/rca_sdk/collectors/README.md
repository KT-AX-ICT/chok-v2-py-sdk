# collectors — ① 수집

원천 소스(log·metric·trace)를 tail 해 **정규화 이전의 원시 레코드**(`RawBatch`)를 산출한다.
설계 근거는 [계획 02](../../../docs/plans/02-collector-normalization-buffer.md) §① 참조.

- `base.Collector` — 추상 인터페이스. `poll() -> RawBatch` 를 30초 루프마다 호출한다.
- `tail.JsonlTailCollector` — 공통 구현. `<source_root>/<modality>/*.jsonl` 을 파일별
  **byte offset** 으로 이어 읽는다 (미완성 줄 유예, truncate 복구, 깨진 줄 스킵).
  각 레코드 dict 에 `_source`(파일명)를 주입하고, 존재한 파일 목록을 `RawBatch.sources` 로 전달한다.
- `log.py` / `metric.py` / `trace.py` — modality 만 지정하는 얇은 서브클래스.
  프로덕션 전환(metric scrape, trace OTLP 등)은 해당 클래스의 `poll()` 교체로 흡수한다 (ADR-004).
- `tail.validate_source_layout()` — 기동 시 경로 검증 헬퍼 (호출은 Runner 소관, ADR-004
  "디렉터리 부재 체크").

소스 present/missing **판정**은 여기서 하지 않는다 — 관측 사실만 전달하고 판정은
`normalization/` 이 전담한다 (ADR-005).
