"""로그 tailer — `<source_root>/log/*.log` 원본 라인을 {"raw": 라인} 으로 산출한다 (계획 03 N1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rca_sdk.collectors.tail import LineTailCollector
from rca_sdk.schemas.events import Modality


class LogCollector(LineTailCollector):
    modality = Modality.LOG
    pattern = "*.log"

    def _frame(self, line: str, path: Path) -> dict[str, Any] | None:
        return {"raw": line}  # boost/nginx 해석은 normalizer 소관
