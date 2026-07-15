"""로그 tailer (스캐폴드). 서비스별 로그 파일을 tail 해 신규 라인을 산출한다."""

from __future__ import annotations

from rca_sdk.collectors.base import Collector
from rca_sdk.schemas.events import Modality, RawBatch


class LogCollector(Collector):
    modality = Modality.LOG

    def __init__(self, source_root: str) -> None:
        self.source_root = source_root

    def poll(self) -> RawBatch:
        # TODO: 로그 디렉터리 tail → 신규 라인을 RawBatch.records 로, observed_from/until 세팅.
        raise NotImplementedError("LogCollector.poll 스캐폴드")
