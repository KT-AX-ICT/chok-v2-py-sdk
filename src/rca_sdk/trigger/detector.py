"""TriggerDetector 추상 인터페이스 (스캐폴드).

새로 들어온 NormalizedBatch 를 버퍼 맥락과 함께 평가해 낱개 근거(TriggerEvidence)를 반환한다.
트리거 없으면 빈 리스트. 각 detector 는 자기 트리거 조건(threshold)을 직접 들고 있다
(정상구간 baseline 산출 없음, interface-contract §0-5).

실시간 detector 목록: cpu_spike / trace_5xx / restart_marker(svc_kill) (§0-6, ADR-003).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.events import NormalizedBatch
from rca_sdk.trigger.models import TriggerEvidence


class TriggerDetector(ABC):
    def __init__(self, condition: dict[str, Any]) -> None:
        self.condition = condition                 # 각 trigger별 조건(threshold)

    @abstractmethod
    def evaluate(self, new_batch: NormalizedBatch, buffer: MemoryBuffer) -> list[TriggerEvidence]:
        """신규 배치 + 버퍼 → 낱개 트리거 근거 목록 (없으면 [])."""
        raise NotImplementedError
