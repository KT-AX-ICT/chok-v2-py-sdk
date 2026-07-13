"""로그 tailer (스캐폴드). 서비스별 로그 파일을 tail 해 신규 라인을 산출한다."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from rca_sdk.collectors.base import Collector
from rca_sdk.schemas.events import Modality


class LogCollector(Collector):
    modality = Modality.LOG

    def __init__(self, source_root: str) -> None:
        self.source_root = source_root

    def poll(self) -> Iterator[dict[str, Any]]:
        # TODO: 로그 디렉터리 tail → 신규 라인 dict 산출. docs/data-schema.md 참조.
        return iter(())
