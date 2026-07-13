"""정규화 출력 = 표준 이벤트 계약. buffer/trigger/snapshot/transport 가 공유한다.

의존 방향은 단방향: collectors → normalization → schemas ← (buffer, trigger, snapshot, transport)
schemas 는 어떤 상위 모듈도 import 하지 않는다.
"""

from rca_sdk.schemas.events import Modality, NormalizedEvent
from rca_sdk.schemas.snapshot import SnapshotBundle, TriggerInfo

__all__ = ["Modality", "NormalizedEvent", "SnapshotBundle", "TriggerInfo"]
