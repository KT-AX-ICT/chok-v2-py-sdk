"""메트릭 tailer (스캐폴드). system metric 시계열(CSV 등)에서 신규 샘플을 산출한다."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from rca_sdk.collectors.base import Collector
from rca_sdk.schemas.events import Modality


class MetricCollector(Collector):
    modality = Modality.METRIC

    def __init__(self, source_root: str) -> None:
        self.source_root = source_root

    def poll(self) -> Iterator[dict[str, Any]]:
        # TODO: metric CSV tail → 신규 샘플 dict 산출.
        return iter(())
