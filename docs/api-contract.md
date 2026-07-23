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
{ "job_id": 2, "accepted": true }
```

`job_id` 는 서버 DB PK(int) — 2026-07-23 실물 E2E 로 확인(원래 SDK 는 문자열로 가정하고 있었다).
전송 성공 운영 로그(`번들 전송 완료: job_id=...`)에 남아 서버 쪽과 상관관계 추적에 쓴다.

서버는 `job_id` 를 생성해 FastAPI DB 에 job 진행상태를 저장하고, 멀티에이전트 RCA 를 개시한다.

## 로그 truncate 메타 (2026-07-23, bundle_version 1.1)

번들 크기 상한(MySQL 단건 INSERT 64MB) 대응으로 로그를 서비스별 볼륨 캡으로 truncate 할 수
있다. `modality_info.log.intervals[]`(=`SourceInterval`)에 아래 필드가 추가됐다 —
**서버 쪽 요청 모델이 extra field 를 거부(`extra="forbid"`)하도록 설정돼 있다면 422 가 나므로
필드 반영 필요**:

```json
{
  "fileName": "socialgraph",
  "status": "data",
  "start": "...", "end": "...",
  "totalCount": 153621,   // truncate 전 원래 건수 (참값 — roster 기준, truncate 와 무관)
  "recordCount": 5000     // 이번 번들 logs[] 에 실제로 실린 건수
}
```

`recordCount < totalCount` 인 소스는 `logs[]` 에 담긴 것이 표본(균등 간격 샘플링)이라는 뜻이다
(별도 `truncated` bool 필드는 두 카운트만으로 판별 가능해 서버 요청으로 뺐다, 2026-07-23) —
"이 서비스에 로그가 적었다/조용했다"로 해석하면 안 되고, 로그 부재를 근거로 쓰는 판단(RCA
에이전트 프롬프트/로직)이 있다면 `recordCount`/`totalCount` 를 먼저 비교해야 한다. error/warn
레벨과 `service_start`/`connection_error` 이벤트, trigger 가 지목한 서비스는 절대 안 잘리므로
이 신호들은 truncate 여부와 무관하게 항상 완전하다.

> TODO: 인증, 재시도/멱등키, 에러 코드 규약 확정.
