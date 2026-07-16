"""시간 기반 롤링 메모리 버퍼 (스캐폴드).

NormalizedBatch 를 append 하며 timestamp 기준 3분 30초 rolling window 를 유지한다.
get_snapshot(start, end) 은 반열림 구간 [start, end) 의 모달리티별 정규화 레코드를
독립 복사본(MultimodalSnapshot)으로 반환한다 (interface-contract §2.3).
"""

from __future__ import annotations

from datetime import datetime

from rca_sdk.schemas.events import MultimodalSnapshot, NormalizedBatch


class MemoryBuffer:
    def __init__(self, window_sec: int = 210) -> None:
        self.window_sec = window_sec

    def append(self, batch: NormalizedBatch) -> None:
        """정규화 배치를 버퍼에 적재하고 오래된 레코드를 축출한다."""
        # TODO: 모달리티별 시계열 적재 + window_sec 초과분 축출.
        raise NotImplementedError("MemoryBuffer.append 스캐폴드")

    def get_snapshot(self, start_ts: datetime, end_ts: datetime) -> MultimodalSnapshot:
        """반열림 구간 [start_ts, end_ts) 의 모달리티별 레코드를 독립 복사본으로 반환한다."""
        # TODO: 구간 필터 + deep copy 로 독립성 보장.
        raise NotImplementedError("MemoryBuffer.get_snapshot 스캐폴드")
