# snapshot — ⑤ 스냅샷 번들

트리거 발화 시, pre/post-trigger 윈도의 데이터를 모아 전송 번들을 조립한다. 정상 구간에서는
번들을 만들지 않는다.

- `assembler.py` — 번들 조립 진입점(스텁).

번들 형태는 기술문서 "SnapShot 전송시 schema" 로 **확정**되었고 `schemas/snapshot.py` 의
`SnapshotBundle` 로 정의되어 있다:

```
bundle_version, company_code, window{start,end}, trigger_info{trigger_time, triggered_by[]},
modality_info{log,metric,trace: intervals[]}, logs/metrics/traces: [{timestamp, service, raw}]
```

조립 로직(버퍼 → 번들 채우기)은 구현 단계에서 채운다. service 미명시 시 "" 로 보내 agent 가
서비스를 guessing 하도록 한다 (FastAPI `ModalityItem.service` 가 str 이라 null 은 422 — 2026-07-23 수정).

`company_code` 는 번들 소속 회사 코드 — 현재 SN 데이터셋 하나뿐이라 `Settings.company_code`
기본값 `"SN001"` 고정으로 보낸다. 다른 회사 데이터셋이 추가되면 배포별로
`RCA_COMPANY_CODE` 환경변수로 오버라이드한다 (2026-07-23).

참고: [docs/snapshot-contract.md](../../../docs/snapshot-contract.md),
`chok_기술문서/정규화 스키마` 의 "SnapShot 전송시 schema" 절
