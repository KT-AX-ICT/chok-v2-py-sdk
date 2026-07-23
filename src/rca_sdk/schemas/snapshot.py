"""SnapshotBundle — 중앙 FastAPI 전송 계약 (고정 형식).

interface-contract §2.6. 이 구조는 서버와 합의된 고정 형식이다. `raw` 는 원본 JSON 을
문자열로 감싼 형태(str)로 담는다.

전송 JSON 은 camelCase (`bundleVersion`, `triggerInfo`, `triggerTime`, `triggeredBy`,
`modalityInfo`). Python 쪽 속성명은 snake_case 그대로 유지하고 `alias_generator` 로만
변환하므로, `model_dump_json(by_alias=True)` 를 쓸 때만 camelCase 가 나간다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Window(_CamelModel):
    start: datetime
    end: datetime


class TriggerInfo(_CamelModel):
    trigger_time: datetime
    triggered_by: list[str] = Field(default_factory=list)  # 발화 모달리티 목록(다중 가능)
    # raw: dict — 지금은 제외, 추후 추가 여지


class SourceInterval(_CamelModel):
    """roster_status(normalization-spec §2)에서 직렬화된 소스 구간 상태."""

    fileName: str
    status: str                          # "missing" | "empty" | "data"
    start: datetime | None = None
    end: datetime | None = None


class ModalityInfo(_CamelModel):
    intervals: list[SourceInterval] = Field(default_factory=list)


class BundleRecord(_CamelModel):
    """전송용 얇은 레코드."""

    timestamp: datetime
    service: str = ""                    # 없으면 "" (중앙 agent 가 guessing). FastAPI 쪽
                                          # ModalityItem.service 가 str(널 불허)라 null 은 422.
    raw: str                             # 원본 JSON 을 문자열로 감싼 형태


class SnapshotBundle(_CamelModel):
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
