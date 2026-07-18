"""svc_kill · metric — placeholder. 신호 없음(설계 §6)."""

from __future__ import annotations

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.events import NormalizedBatch
from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence


class SvcKillMetricDetector(TriggerDetector):
    def evaluate(self, new_batch: NormalizedBatch, buffer: MemoryBuffer) -> list[TriggerEvidence]:
        return []  # 신호 없음(설계 §6): svc_kill 시 metric 은 끊김·변화 없음 → 항상 무발화
