"""트레이스 tailer — 임시 raw 프레이밍 (Task 3 에서 CsvTailCollector 로 교체 예정)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rca_sdk.collectors.tail import LineTailCollector
from rca_sdk.schemas.events import Modality


class TraceCollector(LineTailCollector):
    modality = Modality.TRACE
    pattern = "*.csv"

    def _frame(self, line: str, path: Path) -> dict[str, Any] | None:
        return {"raw": line}
