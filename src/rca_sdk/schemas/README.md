# schemas — 파이프라인 공통 계약

파이프라인이 공유하는 데이터 계약을 정의한다. 단방향 의존의 중심이며, 어떤 상위 모듈도
import 하지 않는다.

- `events.py` — `Modality`, `NormalizedEvent`(모달리티 무관 공통 정규형). 모달리티별 세부 필드는
  `attributes` 로 확장하며, 그 필드셋은 정규화 스키마 문서에서 확정한다.
- `snapshot.py` — 전송 번들 스키마. 기술문서 "SnapShot 전송시 schema" 로 **형태 확정**
  (`SnapshotBundle`: bundle_version·window·trigger_info·modality_info·logs·metrics·traces).
  조립 로직은 `snapshot/assembler.py` 에서 채운다.

의존 방향: `collectors → normalization → schemas ← (buffer, trigger, snapshot, transport)`

참고: [docs/data-schema.md](../../../docs/data-schema.md),
[docs/snapshot-contract.md](../../../docs/snapshot-contract.md)
