"""트리거 도메인 모델.

TriggerEvidence — TriggerDetector.evaluate 산출 단위 (interface-contract §2.4).

주의: Candidate / ModalitySignal / CandidateIncident 는 correlation(모달리티 수렴)용이며,
correlation 은 엣지 SDK에서 제외되었다(§0-4). 엣지 파이프라인에서는 사용하지 않는다.
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


# [미사용 · 주석처리] Candidate / ModalitySignal / CandidateIncident
# 사유: correlation(모달리티 수렴) 전용 모델인데 correlation 이 엣지 SDK에서 제외됨(§0-4).
#       엣지 파이프라인에서 사용처가 없어 죽은 코드 → 참고용으로 남기고 주석처리. (2026-07-15)
#
# class Candidate(BaseModel):
#     service: str | None
#     signal: str
#     value: float
#     baseline: float
#     ratio: float | None = None
#     severity: float = 0.0
#     window: list | None = None
#
#
# class ModalitySignal(BaseModel):
#     modality: str
#     triggered: bool
#     candidates: list[Candidate] = Field(default_factory=list)
#     evidence: dict = Field(default_factory=dict)
#     error: str | None = None
#
#
# class CandidateIncident(BaseModel):
#     incident_id: str
#     suspect_service: str
#     modalities_triggered: list[str] = Field(default_factory=list)
#     candidates: list[Candidate] = Field(default_factory=list)
#     corroboration: int = 0
#     score: float = 0.0
#     window: list | None = None
