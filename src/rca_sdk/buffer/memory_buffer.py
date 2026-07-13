"""시간 기반 롤링 메모리 버퍼 (스캐폴드).

윈도 길이(기본 210초 = 3분 30초)를 넘어선 오래된 이벤트는 자동 축출한다.
트리거 발화 시 이 버퍼 내용이 pre-trigger 근거가 된다 (docs/decisions/ADR-001).
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from rca_sdk.schemas.events import NormalizedEvent


class MemoryBuffer:
    def __init__(self, window_sec: int = 210) -> None:
        self.window = timedelta(seconds=window_sec)
        self._events: deque[NormalizedEvent] = deque()

    def add(self, event: NormalizedEvent) -> None:
        self._events.append(event)
        self._evict(now=event.timestamp)

    def _evict(self, now: datetime) -> None:
        cutoff = now - self.window
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()

    def window_events(self) -> list[NormalizedEvent]:
        """현재 윈도에 남아있는 이벤트 스냅샷."""
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)
