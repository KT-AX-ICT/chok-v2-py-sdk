"""정규화·전송 데이터 계약. buffer/trigger/snapshot/transport 가 공유한다.

의존 방향은 단방향: collectors → normalization → schemas ← (buffer, trigger, snapshot, transport)
schemas 는 어떤 상위 모듈도 import 하지 않는다.
"""

from rca_sdk.schemas.events import (
    Modality,
    MultimodalSnapshot,
    NormalizedBatch,
    NormalizedLog,
    NormalizedMetric,
    NormalizedRecord,
    NormalizedTrace,
    RawBatch,
)
from rca_sdk.schemas.snapshot import (
    BundleRecord,
    ModalityInfo,
    SnapshotBundle,
    SourceInterval,
    SubmissionResult,
    TriggerInfo,
    Window,
)

__all__ = [
    "Modality",
    "NormalizedLog",
    "NormalizedTrace",
    "NormalizedMetric",
    "NormalizedRecord",
    "RawBatch",
    "NormalizedBatch",
    "MultimodalSnapshot",
    "Window",
    "TriggerInfo",
    "SourceInterval",
    "ModalityInfo",
    "BundleRecord",
    "SnapshotBundle",
    "SubmissionResult",
]
