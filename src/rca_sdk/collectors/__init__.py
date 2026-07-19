"""① 수집 계층 — 원천 log/metric/trace 를 지속 관측(tail)해 원시 레코드를 흘려보낸다."""

from rca_sdk.collectors.base import Collector
from rca_sdk.collectors.log import LogCollector
from rca_sdk.collectors.metric import MetricCollector
from rca_sdk.collectors.tail import (
    CsvTailCollector,
    LineTailCollector,
    SourceLayoutError,
    validate_source_layout,
)
from rca_sdk.collectors.trace import TraceCollector

__all__ = [
    "Collector",
    "CsvTailCollector",
    "LineTailCollector",
    "LogCollector",
    "MetricCollector",
    "TraceCollector",
    "SourceLayoutError",
    "validate_source_layout",
]
