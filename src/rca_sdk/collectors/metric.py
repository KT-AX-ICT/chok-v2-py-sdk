"""메트릭 tailer — `<source_root>/metric/*.csv` 행을 컬럼 dict 로 산출한다 (계획 03 N1)."""

from __future__ import annotations

from rca_sdk.collectors.tail import CsvTailCollector
from rca_sdk.schemas.events import Modality


class MetricCollector(CsvTailCollector):
    modality = Modality.METRIC
