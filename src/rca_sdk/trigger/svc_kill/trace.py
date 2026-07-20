"""svc_kill · trace — placeholder. 신호 없음(설계 §6)."""

from __future__ import annotations

from datetime import datetime

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.events import NormalizedBatch
from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence


class SvcKillTraceDetector(TriggerDetector):
    def evaluate(
        self,
        new_batch: NormalizedBatch,
        buffer: MemoryBuffer,
        since: datetime | None = None,
    ) -> list[TriggerEvidence]:
        return []  # 신호 없음(설계 §6): trace 는 끝만 보여 실시간 트리거 불가 → 무발화
