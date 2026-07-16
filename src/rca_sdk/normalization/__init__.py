"""② 정규화 계층 — 모달리티별 RawBatch → NormalizedBatch 변환.

Normalizer ABC 를 모달리티별 정규화기가 구현한다. 소스 present/missing 판정도 이 계층이 전담.
"""

from rca_sdk.normalization.base import Normalizer
from rca_sdk.normalization.log import LogNormalizer
from rca_sdk.normalization.metric import MetricNormalizer
from rca_sdk.normalization.trace import TraceNormalizer

__all__ = ["Normalizer", "LogNormalizer", "MetricNormalizer", "TraceNormalizer"]
