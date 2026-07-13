"""스냅샷 번들 스키마. snapshot.assembler 가 생성하고 transport.client 가 직렬화한다.

이 계약은 중앙 FastAPI 수집 API 와 공유된다 → docs/api-contract.md, docs/snapshot-contract.md.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from rca_sdk.schemas.events import NormalizedEvent


class TriggerInfo(BaseModel):
    """번들을 유발한 트리거 요약."""

    fired_at: datetime
    dataset: str = "SN"
    modalities_triggered: list[str] = Field(default_factory=list)
    suspect_service: str | None = None
    score: float = 0.0
    note: str | None = None


class SnapshotBundle(BaseModel):
    """pre/post-trigger 윈도의 정규화 이벤트 + 트리거 근거."""

    bundle_id: str
    trigger: TriggerInfo
    window_start: datetime
    window_end: datetime
    pre_events: list[NormalizedEvent] = Field(default_factory=list)
    post_events: list[NormalizedEvent] = Field(default_factory=list)
