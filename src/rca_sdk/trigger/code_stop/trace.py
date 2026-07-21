"""code_stop · trace — trace_5xx. 배치 내 500 span 건수가 임계 초과면 발화.

죽은 하위 서비스는 span 을 못 남겨 실패가 nginx 게이트웨이 500 으로 집계된다(설계 §5.5).
"""

from __future__ import annotations

from datetime import datetime

from rca_sdk.schemas.events import Modality, NormalizedBatch, NormalizedTrace
from rca_sdk.trigger.base import NumericThresholdDetector


class TraceFivexxDetector(NumericThresholdDetector):
    MODALITY = Modality.TRACE
    DETECTOR_TYPE = "trace_5xx"

    def _value_and_meta(
        self, new_batch: NormalizedBatch
    ) -> tuple[float, str | None, datetime] | None:
        # 배치 내 500 span 건수를 센다 (정확히 500만 — 설계 §1-5 "500 span만").
        count = sum(
            1
            for rec in new_batch.records
            if isinstance(rec, NormalizedTrace) and rec.http_status_code == 500
        )
        if count == 0:
            return None  # 500 span 0건 → 무발화
        # service="nginx": 500 은 게이트웨이 span 이 주인. 죽은 하위 서비스는 중앙 RCA 국소화.
        return (float(count), "nginx", new_batch.observed_until)
