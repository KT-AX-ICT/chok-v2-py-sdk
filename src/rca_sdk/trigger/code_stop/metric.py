"""code_stop · metric — placeholder. 신호 없음(설계 §6)."""

from __future__ import annotations

from datetime import datetime

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.events import NormalizedBatch
from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence


class CodeStopMetricDetector(TriggerDetector):
    def evaluate(
        self,
        new_batch: NormalizedBatch,
        buffer: MemoryBuffer,
        since: datetime | None = None,
    ) -> list[TriggerEvidence]:
        return []  # 신호 없음(설계 §6): 죽은 컨테이너가 목록에 잔존, span_rate 변화 없음 → 무발화
