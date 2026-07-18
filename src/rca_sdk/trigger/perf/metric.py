"""perf · metric — cpu_spike. cpu 지표 최댓값이 임계 초과면 발화."""

from __future__ import annotations

from datetime import datetime

from rca_sdk.schemas.events import Modality, NormalizedBatch, NormalizedMetric
from rca_sdk.trigger.base import NumericThresholdDetector

CPU_METRICS = {"container_cpu", "system_cpu"}


class CpuSpikeDetector(NumericThresholdDetector):
    MODALITY = Modality.METRIC
    DETECTOR_TYPE = "cpu_spike"

    def _value_and_meta(
        self, new_batch: NormalizedBatch
    ) -> tuple[float, str | None, datetime] | None:
        # cpu 지표 레코드만 골라 배치 내 최댓값을 추적. isinstance 로 union 좁힘(mypy 안전).
        best: tuple[float, str | None, datetime] | None = None
        for rec in new_batch.records:
            if isinstance(rec, NormalizedMetric) and rec.metric_name in CPU_METRICS:
                if rec.value is not None and (best is None or rec.value > best[0]):
                    best = (float(rec.value), rec.canonical_service, rec.timestamp)
        return best  # cpu 레코드 없으면 None → 무발화
