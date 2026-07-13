# 데이터 스키마 (정규화 계약)

`schemas/events.py` 의 `NormalizedEvent` 가 모든 모달리티 공통 정규형이다. 모달리티 고유 필드는
`attributes` dict 로 확장한다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `modality` | `log` / `metric` / `trace` | 모달리티 구분 |
| `timestamp` | datetime(aware) | 이벤트 시각 |
| `service` | str \| None | 서비스명 (정규화 전 원본 표기) |
| `attributes` | dict | 모달리티 고유 필드 |
| `raw_ref` | str \| None | 원본 참조(디버그) |

## 모달리티별 attributes (잠정 — 확정 필요)

- **log**: `level`, `message`
- **metric**: `name`, `value`
- **trace**: `span_id`, `parent_id`, `duration_us`, `status`

> TODO: SN 원천 데이터 실제 필드에 맞춰 확정. `AnoMod/analysis/sn_db/loaders.py` 참조.
