"""perf · log — error_rate. 배치 내 error 로그 건수가 임계 초과면 발화."""

from __future__ import annotations

from datetime import datetime

from rca_sdk.schemas.events import Modality, NormalizedBatch, NormalizedLog
from rca_sdk.trigger.base import NumericThresholdDetector


class ErrorRateDetector(NumericThresholdDetector):
    MODALITY = Modality.LOG
    DETECTOR_TYPE = "error_rate"

    def _value_and_meta(
        self, new_batch: NormalizedBatch
    ) -> tuple[float, str | None, datetime] | None:
        # 배치 내 error 레벨 로그 건수를 센다 (대표값 = 건수).
        count = sum(
            1
            for rec in new_batch.records
            if isinstance(rec, NormalizedLog) and rec.level == "error"
        )
        if count == 0:
            return None  # error 로그 0건 → 무발화
        # service=None: 배치 전역 카운트라 특정 서비스에 귀속 안 함. 시각은 배치 watermark.
        return (float(count), None, new_batch.observed_until)
