"""SnapshotBundle — 중앙 FastAPI 전송 계약 (고정 형식).

interface-contract §2.6. 이 구조는 서버와 합의된 고정 형식이다. `raw` 는 원본 JSON 을
문자열로 감싼 형태(str)로 담는다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Window(BaseModel):
    start: datetime
    end: datetime


class TriggerInfo(BaseModel):
    trigger_time: datetime
    triggered_by: list[str] = Field(default_factory=list)  # 발화 모달리티 목록(다중 가능)
    # raw: dict — 지금은 제외, 추후 추가 여지


class SourceInterval(BaseModel):
    """roster_status(normalization-spec §2)에서 직렬화된 소스 구간 상태."""

    fileName: str
    status: str                          # "missing" | "empty" | "data"
    start: datetime | None = None
    end: datetime | None = None


class ModalityInfo(BaseModel):
    intervals: list[SourceInterval] = Field(default_factory=list)


class BundleRecord(BaseModel):
    """전송용 얇은 레코드."""

    timestamp: datetime
    service: str | None = None           # 없으면 None/"" (중앙 agent 가 guessing)
    raw: str                             # 원본 JSON 을 문자열로 감싼 형태


class SnapshotBundle(BaseModel):
    bundle_version: str = "1.0"
    window: Window
    trigger_info: TriggerInfo
    modality_info: dict[str, ModalityInfo] = Field(default_factory=dict)  # log/metric/trace
    logs: list[BundleRecord] = Field(default_factory=list)
    metrics: list[BundleRecord] = Field(default_factory=list)
    traces: list[BundleRecord] = Field(default_factory=list)


class SubmissionResult(BaseModel):
    """Transport.send 결과."""

    accepted: bool
    job_id: str | None = None
    error: str | None = None
