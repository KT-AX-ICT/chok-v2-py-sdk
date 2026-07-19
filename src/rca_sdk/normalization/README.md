# normalization — ② 정규화

`collectors/` 가 낸 원시 레코드를 파이프라인 공통 정규형(`schemas.NormalizedEvent`)으로 변환한다.

공통 처리(정규화 스키마 문서 기준):
- 서비스명 canonical 통일
- timestamp 표시 형식 통일
- 공백값 `null` 처리

모달리티별 구체 필드셋(log/metric/trace 각각 어떤 필드를 추출할지)은 **구현 단계에서 정규화 스키마
문서로 확정**한다. 현재 파일들은 시그니처만 있는 스텁이다.

참고: `chok_기술문서/정규화 스키마`, [docs/data-schema.md](../../../docs/data-schema.md)
