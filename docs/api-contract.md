# 수집 API 계약 (SDK ↔ 중앙 FastAPI)

SDK `transport.client` 가 스냅샷 번들을 POST 하는 인터페이스. **서버 팀과 합의 필요.**

## 엔드포인트 (잠정)

```
POST /ingest
Content-Type: application/json
Body: SnapshotBundle (schemas/snapshot.py 직렬화)
```

## 응답 (잠정)

```json
{ "job_id": "…", "accepted": true }
```

서버는 `job_id` 를 생성해 FastAPI DB 에 job 진행상태를 저장하고, 멀티에이전트 RCA 를 개시한다.

## companyCode (2026-07-23)

`SnapshotBundle` 최상위에 `companyCode` 필드 추가 — 번들이 어느 회사(고객사) 데이터인지
식별. 현재는 SN 데이터셋 하나뿐이라 `"SN001"` 고정값만 보낸다. 다른 회사 데이터셋은 추후
추가 예정 — 그때는 `Settings.company_code`(env `RCA_COMPANY_CODE`)를 배포별로 다르게 설정.

```json
{ "bundleVersion": "1.0", "companyCode": "SN001", "window": { "...": "..." } }
```

서버 쪽 요청 모델이 extra field 를 거부(`extra="forbid"`)하도록 설정돼 있다면 이 필드도
반영이 필요하다.

> TODO: 인증, 재시도/멱등키, 에러 코드 규약 확정.
