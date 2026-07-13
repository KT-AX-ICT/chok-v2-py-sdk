# ADR-002 — baseline 프로파일 출처

- 상태: 제안 (blocker)
- 날짜: 2026-07-13

## 맥락

기존 연구 detector 는 baseline **실험 폴더 전체**와 시나리오 폴더를 비교한다. 하지만 엣지 SDK 의
실시간 30초 루프에는 비교할 폴더가 없다. baseline 을 어디서 가져올지 결정해야 detector 인터페이스가
확정된다.

## 대안

1. **사전 계산 프로파일 동봉** — 정상 구간(Normal_Baseline)에서 산출한 기준치 JSON 을 SDK 리소스로
   포함(`resources/baselines/sn_normal.json`). 로더는 `trigger/baseline.py`.
2. **롤링 self-baseline** — 관측 초기 N분을 정상으로 가정해 실시간으로 기준치를 학습.
3. 혼합 — 동봉 프로파일 + 런타임 보정.

## 결정

미정. MVP 는 (1) 동봉 프로파일로 출발 예정(placeholder JSON 존재). 실제 값 산출 절차 필요.

## 결과/영향

`trigger/detector.py` 의 입력 시그니처(`baseline: dict`)와 프로파일 스키마가 여기 종속.
