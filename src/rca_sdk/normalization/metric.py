"""메트릭 정규화 (스캐폴드). RawBatch(metric) → NormalizedBatch(NormalizedMetric)."""

from __future__ import annotations

from rca_sdk.normalization.base import Normalizer
from rca_sdk.schemas.events import NormalizedBatch, RawBatch


class MetricNormalizer(Normalizer):
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        # TODO: metric_name/value/dimension/unit 추출 → NormalizedMetric.
        #       canonical_service(노드 지표는 __node__)·timestamp 통일. normalization-spec §5 참조.
        raise NotImplementedError("MetricNormalizer.normalize 스캐폴드")
