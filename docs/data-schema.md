# 데이터 스키마 (정규화 계약)

> **이 문서는 대체되었습니다.** 단일 `NormalizedEvent`(+`attributes` dict, `raw_ref`)는
> 모달리티별 3개 스키마(`NormalizedLog` / `NormalizedTrace` / `NormalizedMetric`)로 교체되었다.
> `raw_ref`는 사용하지 않는다 (원본은 전송 번들의 `raw` JSON 문자열로만 전달).
>
> 현행 정규화 계약(정규화 스펙 · 인터페이스 계약)은 **노션에서 확인**한다.
