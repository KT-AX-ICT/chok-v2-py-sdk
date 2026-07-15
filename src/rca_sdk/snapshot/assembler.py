"""SnapshotManager — 트리거 이후 RCA 스냅샷 lifecycle 관리 (스캐폴드).

- register_triggers: 최초 트리거를 anchor 로 삼아 window(anchor±3분) 고정, pre 즉시 저장,
  Capture Session 생성. 이미 세션이 있으면 evidence 만 누적.
- finalize_ready: window_end 도달 시 pre+post+evidence 를 SnapshotBundle 로 조립.
  observed_until 은 개별 기준(모달리티별, 느린 모달리티 대기 안 함).

interface-contract §2.5.
"""

from __future__ import annotations

from datetime import datetime

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.snapshot import SnapshotBundle
from rca_sdk.trigger.models import TriggerEvidence


class SnapshotManager:
    def register_triggers(
        self, evidences: list[TriggerEvidence], buffer: MemoryBuffer
    ) -> None:
        """트리거 근거 등록 → 세션 생성/누적 (anchor±3분 고정, pre 즉시 저장)."""
        # TODO: Active Session 판정, anchor 선택(최초 trigger_time), window 계산, pre 스냅샷 저장.
        raise NotImplementedError("SnapshotManager.register_triggers 스캐폴드")

    def finalize_ready(
        self, observed_until: datetime, buffer: MemoryBuffer
    ) -> list[SnapshotBundle]:
        """window_end 도달한 세션을 SnapshotBundle 로 완성해 반환 (없으면 [])."""
        # TODO: 개별 기준으로 window_end 도달 판정 → post 조회 → 번들 조립.
        raise NotImplementedError("SnapshotManager.finalize_ready 스캐폴드")
