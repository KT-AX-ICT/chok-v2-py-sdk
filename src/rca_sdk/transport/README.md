# transport — ⑥ 전송

조립된 스냅샷 번들을 중앙 FastAPI 수집 API로 전송한다. 트리거 발화 시에만 호출된다.

- `client.TransportClient` — 번들 POST 클라이언트(최소 구현).
- **엔드포인트 = `POST /ingest`** — 기획서 v0.3 §수집 API 기준으로 확정
  (`/v1/ingest` 였던 것을 `fc6fda3` 에서 정정). 주입 경로는
  `Settings.collect_endpoint` ← `RCA_COLLECT_ENDPOINT` ← `${FASTAPI_ROOT_URL}/ingest`.
  경로를 바꿀 땐 `.env.example`·`config.py` 기본값·[api-contract](../../../docs/api-contract.md)
  세 곳이 함께 움직여야 한다.

**미확정(서버 팀과 합의):** 인증, 재시도/멱등키, 에러 코드 규약.

참고: [docs/api-contract.md](../../../docs/api-contract.md)
