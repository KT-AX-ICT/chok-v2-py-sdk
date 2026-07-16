# SDK 아키텍처

RCA 시스템의 실서비스 측 엣지 수집기. 30초 주기로 원천 데이터를 관측하다가 트리거 조건에
이상이 걸리면 스냅샷 번들을 중앙 서버로 전송한다. **정상 구간은 전송하지 않는다.**

## 파이프라인

```
collectors ─▶ normalization ─▶ schemas ◀─ buffer ◀─ trigger ─▶ snapshot ─▶ transport
   ①              ②           (계약)      ③          ④          ⑤           ⑥
```

| 단계 | 패키지 | 책임 |
|---|---|---|
| ① 수집 | `collectors/` | log/metric/trace tail (신규 레코드 산출) |
| ② 정규화 | `normalization/` | 원시 → `schemas.NormalizedEvent` |
| ③ 버퍼 | `buffer/` | 3분 30초 롤링 윈도 유지 |
| ④ 트리거 | `trigger/` | 각 detector 조건으로 이상 감지 → 낱개 근거(TriggerEvidence) |
| ⑤ 스냅샷 | `snapshot/` | pre/post-trigger 번들 조립 |
| ⑥ 전송 | `transport/` | FastAPI 수집 API POST |
| 루프 | `runtime/` | 위 전부를 30초 주기로 오케스트레이션 |

## 의존 방향

`schemas/` 를 중심 계약으로 두어 단방향 의존을 유지한다. 상위 계층은 `schemas` 를 import 하지만
`schemas` 는 어떤 상위도 import 하지 않는다.

## 기존 연구 코드와의 관계

`AnoMod/analysis/sn_db/detectors` 의 evaluate 순수 로직을 참고하되, 폴더 전체를 읽는 배치형
`detect()` 는 실시간 버퍼 입력으로 재작성한다. correlate(모달리티 수렴)는 엣지에서 제외 —
중앙 RCA 가 담당한다(ADR-005).
