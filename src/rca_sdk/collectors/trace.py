"""트레이스 tailer (스캐폴드). span 로그(JSONL 등)에서 신규 span 을 산출한다."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from rca_sdk.collectors.base import Collector
from rca_sdk.schemas.events import Modality


class TraceCollector(Collector):
    modality = Modality.TRACE

    def __init__(self, source_root: str) -> None:
        self.source_root = source_root

    def poll(self) -> Iterator[dict[str, Any]]:
        # TODO: trace JSONL tail → 신규 span dict 산출.
        return iter(())
