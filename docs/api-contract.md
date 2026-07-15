# 수집 API 계약 (SDK ↔ 중앙 FastAPI)

SDK `transport.client` 가 스냅샷 번들을 POST 하는 인터페이스. **서버 팀과 합의 필요.**

## 엔드포인트 (잠정)

```
POST /v1/ingest
Content-Type: application/json
Body: SnapshotBundle (schemas/snapshot.py 직렬화)
```

## 응답 (잠정)

```json
{ "job_id": "…", "accepted": true }
```

서버는 `job_id` 를 생성해 FastAPI DB 에 job 진행상태를 저장하고, 멀티에이전트 RCA 를 개시한다.

> TODO: 인증, 재시도/멱등키, 에러 코드 규약 확정.
