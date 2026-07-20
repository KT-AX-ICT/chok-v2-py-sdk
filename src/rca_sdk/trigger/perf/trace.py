"""perf · trace — latency_spike. span duration(ms) 최댓값이 임계 초과면 발화."""

from __future__ import annotations

from datetime import datetime

from rca_sdk.schemas.events import Modality, NormalizedBatch, NormalizedTrace
from rca_sdk.trigger.base import NumericThresholdDetector


class LatencySpikeDetector(NumericThresholdDetector):
    MODALITY = Modality.TRACE
    DETECTOR_TYPE = "latency_spike"

    def _value_and_meta(
        self, new_batch: NormalizedBatch
    ) -> tuple[float, str | None, datetime] | None:
        # span 레코드 중 duration(ms) 최댓값을 추적 = 배치에서 가장 느린 요청.
        best: tuple[float, str | None, datetime] | None = None
        for rec in new_batch.records:
            if isinstance(rec, NormalizedTrace) and rec.duration_ms is not None:
                if best is None or rec.duration_ms > best[0]:
                    best = (float(rec.duration_ms), rec.service, rec.timestamp)
        return best  # span 없으면 None → 무발화
