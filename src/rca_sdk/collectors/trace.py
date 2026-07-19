"""트레이스 tailer — `<source_root>/trace/*.csv`(all_traces) 행을 컬럼 dict 로 산출한다 (N1)."""

from __future__ import annotations

from rca_sdk.collectors.tail import CsvTailCollector
from rca_sdk.schemas.events import Modality


class TraceCollector(CsvTailCollector):
    modality = Modality.TRACE
