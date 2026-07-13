"""트리거 도메인 모델. 기존 analysis/detectors/types.py 를 pydantic 으로 승격.

Candidate → ModalitySignal(모달리티별) → CandidateIncident(모달리티 간 수렴).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    service: str | None
    signal: str
    value: float
    baseline: float
    ratio: float | None = None
    severity: float = 0.0
    window: list | None = None


class ModalitySignal(BaseModel):
    modality: str
    triggered: bool
    candidates: list[Candidate] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    error: str | None = None


class CandidateIncident(BaseModel):
    incident_id: str
    suspect_service: str
    modalities_triggered: list[str] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    corroboration: int = 0
    score: float = 0.0
    window: list | None = None
