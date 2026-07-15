"""Collector 추상 인터페이스. 모달리티별 tailer 가 이를 구현한다."""

from __future__ import annotations

from abc import ABC, abstractmethod

from rca_sdk.schemas.events import Modality, RawBatch


class Collector(ABC):
    """원천 소스를 관측해 원시 레코드 배치를 산출한다.

    산출물(RawBatch)은 아직 정규화 이전(모달리티 고유 형태)이며, normalization 계층이
    표준 스키마로 변환한다. 소스 present/missing 판정은 collector 가 아니라 normalizer 가 전담한다.
    """

    modality: Modality

    @abstractmethod
    def poll(self) -> RawBatch:
        """직전 관측 이후 새로 유입된 원시 레코드를 RawBatch 로 반환한다 (30초 루프마다 호출)."""
        raise NotImplementedError
