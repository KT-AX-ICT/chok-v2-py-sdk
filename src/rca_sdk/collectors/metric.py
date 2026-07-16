"""메트릭 tailer — `<source_root>/metric/*.jsonl` 의 신규 라인을 산출한다."""

from __future__ import annotations

from rca_sdk.collectors.tail import JsonlTailCollector
from rca_sdk.schemas.events import Modality


class MetricCollector(JsonlTailCollector):
    modality = Modality.METRIC
