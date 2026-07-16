# chok-v2-py-sdk

RCA 시스템의 **엣지 수집기 Python SDK**. 실서비스 측에서 log·metric·trace를 지속 관측하다가,
트리거 조건에 이상이 걸리면 **pre/post-trigger 스냅샷 번들**을 구성해 중앙 FastAPI 수집 API로 전송한다.

- import 패키지명: `rca_sdk`  (배포명 `chok-v2-py-sdk`와 다름)
- 실행 진입점: `rca-collect`

## 파이프라인 (아키텍처 대응)

```
collectors ─▶ normalization ─▶ schemas ◀─ buffer ◀─ trigger ─▶ snapshot ─▶ transport
   ①              ②           (계약)      ③          ④          ⑤           ⑥
                                       runtime.runner 가 30초 루프로 위 전부를 오케스트레이션
```

1. **collectors** — log/metric/trace 지속 유입 (tailer)
2. **normalization** — 표준 스키마(`schemas/events`)로 정규화
3. **buffer** — 3분 30초 롤링 메모리 버퍼
4. **trigger** — 각 detector 조건으로 이상 감지 → 낱개 근거(TriggerEvidence). 수렴(correlation)은 중앙 RCA 담당
5. **snapshot** — pre-trigger + (3분 대기) post-trigger 번들 조립
6. **transport** — FastAPI 수집 API로 POST

## 개발 세팅

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1      # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## MVP 범위

SN(SocialNetwork) 데이터 기준, DB 관련 에러 제외, 세 결함군 탐지 검증:
`Perf CPU Contention`, `Svc_Kill_Media`, `Code_Stop_Media`.

## 문서

- [docs/architecture.md](docs/architecture.md) — 전체 구조
- [docs/trigger-policy.md](docs/trigger-policy.md) — baseline/임계/윈도 정책
- [docs/decisions/](docs/decisions/) — 설계 결정(ADR). **미해결 모호점이 여기 있음.**
