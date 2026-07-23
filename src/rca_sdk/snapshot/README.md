# snapshot — ⑤ 스냅샷 번들

트리거 발화 시, pre/post-trigger 윈도의 데이터를 모아 전송 번들을 조립한다. 정상 구간에서는
번들을 만들지 않는다.

- `assembler.py` — 번들 조립 진입점(스텁).

번들 형태는 기술문서 "SnapShot 전송시 schema" 로 **확정**되었고 `schemas/snapshot.py` 의
`SnapshotBundle` 로 정의되어 있다:

```
bundle_version, company_code, window{start,end}, trigger_info{trigger_time, triggered_by[]},
modality_info{log,metric,trace: intervals[{fileName, status, start, end,
  totalCount, recordCount}]}, logs/metrics/traces: [{timestamp, service, raw}]
```

조립 로직(버퍼 → 번들 채우기)은 구현 단계에서 채운다. service 미명시 시 "" 로 보내 agent 가
서비스를 guessing 하도록 한다 (FastAPI `ModalityItem.service` 가 str 이라 null 은 422 — 2026-07-23 수정).

`company_code` 는 번들 소속 회사 코드 — 현재 SN 데이터셋 하나뿐이라 `Settings.company_code`
기본값 `"SN001"` 고정으로 보낸다. 다른 회사 데이터셋이 추가되면 배포별로
`RCA_COMPANY_CODE` 환경변수로 오버라이드한다 (2026-07-23).

### 로그 truncate (2026-07-23, bundle_version 1.1)

로그 볼륨이 서비스별로 극단적으로 불균등해(특정 서비스 하나가 burst 시 번들의 90%+ 를 차지)
번들이 MySQL 단건 INSERT 한도(64MB)를 넘는 사례가 있었다. `assembler._truncate_logs` 가
서비스별 볼륨 캡(`Settings.log_truncation_cap`, 기본 5000)을 적용한다.

- **절대 안 자르는 것**: `level != "info"`, `event_type != "normal_log"`(service_start/
  connection_error 등 detector 가 직접 스캔하는 신호), trigger 근거(`TriggerEvidence.service`)가
  지목한 서비스.
- **자르는 것**: 그 외 — 캡 초과분은 head-N 이 아니라 균등 간격(stride) 샘플링으로 줄여 창
  전체의 시간대별 모양을 유지한다.
- **backstop**: exempt 레코드를 포함한 서비스별 최종 상한(`log_truncation_backstop_cap`,
  기본 50000) — 정상 동작에서는 안 걸리지만 trigger 귀속 서비스 자체가 폭주해도 번들 크기
  상한을 보장한다.
- 잘렸는지는 `modality_info[modality].intervals[].totalCount`/`recordCount` 로 전달한다 —
  `recordCount < totalCount` 면 잘린 것이다. 별도 `truncated` bool 필드는 서버 요청으로
  뺐다(두 카운트만으로 판별 가능, 2026-07-23). `totalCount`는 원본 상태 판정
  (missing/empty/data)에 항상 쓰이는 roster 기준 값이라 truncate 와 무관하게 참값이다.
- `Settings.log_truncation_enabled=False` 로 끌 수 있다 (서버가 새 필드를 처리할 준비가 안
  됐을 때 과도기 대응용).

참고: [docs/snapshot-contract.md](../../../docs/snapshot-contract.md),
`chok_기술문서/정규화 스키마` 의 "SnapShot 전송시 schema" 절
