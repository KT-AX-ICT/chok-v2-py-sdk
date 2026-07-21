# normalization — ② 정규화

collector 의 원시 레코드를 표준 스키마(`NormalizedLog/Metric/Trace`)로 변환하고,
기대 로스터 대조로 소스 상태(roster)를 판정한다.
설계 근거는 [계획 03](../../../docs/plans/03-tail-rework-normalization.md) §2 참조.

- `common.canonical_service()` — 서비스명 정규화 (스펙 §1-1, 인프라 예외·nginx ALIASES).
- `common.parse_timestamp()` — boost 영문월·nginx·ISO 공백형 → **naive** datetime (C6).
- `log.LogNormalizer` — `{"raw": 라인}` 을 boost/nginx 정규식으로 분해.
  `event_type`(service_start = restart_marker 원천 / connection_error / normal_log),
  `code_loc`, `target_service`(Could not connect to 패턴만, 익명 resolve-host 는 None) 파생.
- `metric.MetricNormalizer` — CSV 컬럼 dict. container_label → canonical,
  `instance`(system_*) → `__node__`(cpu_spike 원천), unit 상수 테이블.
- `trace.TraceNormalizer` — all_traces.csv 컬럼 직행 매핑, 공백 → None, tags/logs JSON 파싱.
- roster — `Normalizer(expected_services)` × `batch.sources` × 서비스별 건수 →
  `SourceStatus(source=canonical, present, record_count)`.
  missing(파일 없음) / empty(있는데 0건) / data 구분 재료 (Code_Stop 국소화, 계획 03 N2).

레코드 단위 파싱 실패는 skip + warning (N3) — 한 줄 오염이 30초 루프를 멈추지 않는다.
