"""Normalizer 추상 인터페이스. 모달리티별 정규화기가 이를 구현한다.

RawBatch 를 받아 모달리티별 정규화 레코드로 변환하고, 배치 메타(observed_from/until)는 유지한다.
소스 present/missing 판정도 이 계층이 전담한다 (정규화 스펙 §2, roster 원천, 계획 03 N2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Sequence

from rca_sdk.schemas.events import NormalizedBatch, RawBatch, SourceStatus


class Normalizer(ABC):
    def __init__(self, expected_services: Sequence[str] = ()) -> None:
        self.expected_services = list(expected_services)  # canonical 목록 (Settings 주입)

    @abstractmethod
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        """RawBatch → NormalizedBatch (모달리티별 정규화 스키마 + roster)."""
        raise NotImplementedError

    def _build_roster(
        self, expected: Sequence[str], present: set[str], counts: Counter[str]
    ) -> list[SourceStatus]:
        """expected × 관측(present)·건수 → SourceStatus 목록 (missing/empty/data 재료)."""
        return [
            SourceStatus(source=svc, present=svc in present, record_count=counts.get(svc, 0))
            for svc in expected
        ]
