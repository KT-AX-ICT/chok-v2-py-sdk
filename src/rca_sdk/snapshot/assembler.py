"""스냅샷 번들 조립 (스캐폴드).

트리거 발화 시:
  1. buffer.window_events() → pre_events (트리거 직전 3분 30초)
  2. post_trigger_wait_sec(기본 180초) 동안 계속 수집 → post_events
  3. SnapshotBundle 로 묶어 transport 로 넘김
윈도 정의는 docs/decisions/ADR-001 에서 확정한다.
"""

from __future__ import annotations

import uuid

from rca_sdk.schemas.events import NormalizedEvent
from rca_sdk.schemas.snapshot import SnapshotBundle, TriggerInfo


class SnapshotAssembler:
    def __init__(self, post_trigger_wait_sec: int = 180) -> None:
        self.post_trigger_wait_sec = post_trigger_wait_sec

    def assemble(
        self,
        trigger: TriggerInfo,
        pre_events: list[NormalizedEvent],
        post_events: list[NormalizedEvent],
    ) -> SnapshotBundle:
        events = pre_events + post_events
        if events:
            window_start = min(e.timestamp for e in events)
            window_end = max(e.timestamp for e in events)
        else:
            window_start = window_end = trigger.fired_at
        return SnapshotBundle(
            bundle_id=uuid.uuid4().hex,
            trigger=trigger,
            window_start=window_start,
            window_end=window_end,
            pre_events=pre_events,
            post_events=post_events,
        )
