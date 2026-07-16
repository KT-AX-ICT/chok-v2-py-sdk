"""로그 정규화 (스캐폴드). RawBatch(로그) → NormalizedBatch(NormalizedLog)."""

from __future__ import annotations

from rca_sdk.normalization.base import Normalizer
from rca_sdk.schemas.events import NormalizedBatch, RawBatch


class LogNormalizer(Normalizer):
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        # TODO: level/message/code_loc/target_service/event_type 추출 → NormalizedLog.
        #       canonical_service·timestamp 통일. normalization-spec §3 참조.
        raise NotImplementedError("LogNormalizer.normalize 스캐폴드")
