"""트레이스 정규화 (스캐폴드). RawBatch(trace) → NormalizedBatch(NormalizedTrace)."""

from __future__ import annotations

from rca_sdk.normalization.base import Normalizer
from rca_sdk.schemas.events import NormalizedBatch, RawBatch


class TraceNormalizer(Normalizer):
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        # TODO: trace_id/span_id/parent_span_id/operation/duration/http_status_code/tags 추출
        #       → NormalizedTrace. canonical_service·timestamp 통일. normalization-spec §4 참조.
        raise NotImplementedError("TraceNormalizer.normalize 스캐폴드")
