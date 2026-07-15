"""트레이스 tailer (스캐폴드). span 로그(JSONL 등)에서 신규 span 을 산출한다."""

from __future__ import annotations

from rca_sdk.collectors.base import Collector
from rca_sdk.schemas.events import Modality, RawBatch


class TraceCollector(Collector):
    modality = Modality.TRACE

    def __init__(self, source_root: str) -> None:
        self.source_root = source_root

    def poll(self) -> RawBatch:
        # TODO: trace JSONL tail → 신규 span 을 RawBatch.records 로, observed_from/until 세팅.
        raise NotImplementedError("TraceCollector.poll 스캐폴드")
