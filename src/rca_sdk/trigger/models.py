"""트리거 도메인 모델.

TriggerEvidence — TriggerDetector.evaluate 산출 단위 (interface-contract §2.4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from rca_sdk.schemas.events import Modality


class TriggerEvidence(BaseModel):
    """단일 트리거 근거. 정규화 스키마 기준으로 증거 자료를 형성한다."""

    trigger_time: datetime
    modality: Modality
    service: str | None = None
    detector_type: str                     # 예: "cpu_spike", "trace_5xx", "restart_marker"
    value: float
    baseline: float
    threshold: float
    extra: dict[str, Any] = Field(default_factory=dict)
