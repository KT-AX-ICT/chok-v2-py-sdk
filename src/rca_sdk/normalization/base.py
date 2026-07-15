"""Normalizer 추상 인터페이스. 모달리티별 정규화기가 이를 구현한다.

RawBatch 를 받아 모달리티별 정규화 레코드로 변환하고, 배치 메타(observed_from/until)는 유지한다.
소스 present/missing 판정도 이 계층이 전담한다 (normalization-spec §2, roster_status 원천).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from rca_sdk.schemas.events import NormalizedBatch, RawBatch


class Normalizer(ABC):
    @abstractmethod
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        """RawBatch → NormalizedBatch (모달리티별 정규화 스키마)."""
        raise NotImplementedError
