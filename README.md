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

## 로컬에서 테스트하려면

`rca-collect`는 실서비스 진입점이라 `var/{log,metric,trace}`가 이미 존재하는 실제 로그
경로라고 가정하고, 없으면 즉시 실패한다(`SourceLayoutError`). 빈 디렉터리만 만들어도 죽지는
않지만, 안에 아무 데이터도 안 들어오면 트리거가 영원히 안 붙는다.

로컬 SN 데이터셋으로 그 자리를 실시간으로 채워주는 게 `demo/replayer`다. 이건 로컬 개발용
도구라 `pyproject.toml`에 등록돼 있지 않고(실서비스 설치본엔 안 딸려간다), `rca-collect`가
자동으로 같이 실행해주지도 않는다 — 그래서 리플레이어와 `rca-collect`를 **별도 프로세스로
동시에** 띄워야 하고, 편의상 `scripts/run_local_demo.sh`가 그 둘을 한 번에 묶어준다.

`rca-collect`가 번들을 보낼 대상은 `RCA_COLLECT_ENDPOINT` 환경변수(기본값
`http://localhost:8000/ingest`)로 정해진다. 이 대상에 따라 준비가 두 가지로 갈린다.

### A. mock 서버로 테스트 (받는 쪽 구현 없이 파이프라인만 확인)

터미널 2개 필요 — mock 서버는 켜둔 채로 둔다.

```bash
# 터미널 1: mock ingest 서버 (계속 실행 상태 유지)
source .venv/bin/activate
python scripts/mock_ingest_server.py

# 터미널 2: 리플레이어 + rca-collect 동시 실행
source .venv/bin/activate
scripts/run_local_demo.sh cpu   # <scenario: cpu|kill_media|code_media> [duration_sec]
```

터미널 2에 `트리거 발화: ...` → `번들 전송 완료: ...`가 뜨면, 터미널 1에도 같은 순간
`[수신] window=... trigger=...(...)` 요약이 찍힌다. 이게 왕복이 됐다는 뜻이다.

### B. 실제(원격) FastAPI 서버로 테스트

이미 어딘가에 떠 있는 실제 서버로 보낼 때는 mock 서버가 필요 없다 — `RCA_COLLECT_ENDPOINT`만
그 서버 주소로 지정해서 터미널 1개로 끝낸다.

```bash
source .venv/bin/activate
RCA_COLLECT_ENDPOINT=http://<서버 주소>:8000/ingest scripts/run_local_demo.sh cpu
```

`번들 전송 완료`가 뜨면 서버가 정상 응답(2xx)한 것이고, `번들 전송 실패 (...): <에러>`가
뜨면 그 에러 메시지(타임아웃/422/connection reset 등)로 원인을 좁힌다 — 대량 페이로드(로그
30만 건대, 수십~백여 MB)라 서버 응답이 늦으면 `TransportClient`의 기본 타임아웃(10초,
`src/rca_sdk/transport/client.py`)에 걸릴 수 있다는 점을 참고한다.

`run_local_demo.sh`는 리플레이어로 `var/`를 채우면서 동시에 `rca-collect`를 띄우고,
`Ctrl+C` 한 번으로 둘 다 종료한다. `duration_sec`을 생략하면 데이터셋 끝까지 재생한다.

### 시나리오 선택 없는 연속 데모

SDK 저장소에 포함된 AnoMod 정상 baseline과 장애 3종을
`normal → cpu → normal → kill_media → normal → code_media` 순서로 계속 재생하려면:

```bash
scripts/run_demo_server.sh
```

별도 설정이 없으면 실행마다 `var/demo-runs/<실행ID>`를 만들고 기존 `rca-collect`와 새
simulator가 같은 경로를 사용한다. 자세한 순환 시간과 옵션은
[demo/simulator/README.md](demo/simulator/README.md)를 참고한다.

> TODO(timestamp-contract): SDK/FastAPI/Spring timestamp 계약은 담당 서비스에서 별도로
> 정리해야 한다. 계약 수정 전에는 SDK report bundle 생성 뒤 Spring 저장이 422로 실패할 수 있다.

## MVP 범위

SN(SocialNetwork) 데이터 기준, DB 관련 에러 제외, 세 결함군 탐지 검증:
`Perf CPU Contention`, `Svc_Kill_Media`, `Code_Stop_Media`.

## 문서

- [docs/architecture.md](docs/architecture.md) — 전체 구조
- [docs/trigger-policy.md](docs/trigger-policy.md) — baseline/임계/윈도 정책
- [docs/decisions/](docs/decisions/) — 설계 결정(ADR). **미해결 모호점이 여기 있음.**
