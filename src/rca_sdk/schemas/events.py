"""정규화된 표준 이벤트 스키마. 모든 모달리티가 이 형태로 버퍼에 쌓인다.

주의(스캐폴드): 필드는 잠정안이다. docs/data-schema.md 와 팀 설계에서 확정한다.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Modality(StrEnum):
    LOG = "log"
    METRIC = "metric"
    TRACE = "trace"


class NormalizedEvent(BaseModel):
    """모달리티 무관 공통 정규화 레코드.

    모달리티별 세부 필드는 `attributes` 에 담아 확장한다 (예: trace 의 span_id/duration_us,
    metric 의 name/value, log 의 level/message).
    """

    modality: Modality
    timestamp: datetime
    service: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    # 정규화 이전 원본 참조 (디버그/추적용, 선택)
    raw_ref: str | None = None
