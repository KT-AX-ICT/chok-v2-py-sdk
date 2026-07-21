"""TriggerDetector 추상 인터페이스 (스캐폴드).

새로 들어온 NormalizedBatch 를 버퍼 맥락과 함께 평가해 낱개 근거(TriggerEvidence)를 반환한다.
트리거 없으면 빈 리스트. 각 detector 는 자기 트리거 조건(threshold)을 직접 들고 있다
(정상구간 baseline 산출 없음, interface-contract §0-5).

실시간 detector 목록: cpu_spike / trace_5xx / restart_marker(svc_kill) (§0-6, ADR-003).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.events import NormalizedBatch
from rca_sdk.trigger.models import TriggerEvidence


class TriggerDetector(ABC):
    def __init__(self, condition: dict[str, Any]) -> None:
        self.condition = condition                 # 각 trigger별 조건(threshold)

    @abstractmethod
    def evaluate(
        self,
        new_batch: NormalizedBatch,
        buffer: MemoryBuffer,
        since: datetime | None = None,
    ) -> list[TriggerEvidence]:
        """신규 배치 + 버퍼 → 낱개 트리거 근거 목록 (없으면 []).

        `since` 는 **평가 구간 하한**이다. 직전 번들이 담아 전송한 구간을 다시 세면 k번째
        샘플(= trigger_time)이 과거로 끌려가 pre 가 잘리므로, 창 기반 detector 는 되돌아보기
        시작점을 여기서 자른다(계획 04 §7-3). 포함 경계 — `get_snapshot` 이 `[start, end)` 라
        직전 번들이 제외한 `window_end` 를 여기서 집어 누락도 중복도 없다.

        detector 는 이 값이 번들에서 왔다는 걸 모른다. 시각 하나를 받을 뿐이므로 무상태가
        유지된다(ADR-006). 번들 이력을 아는 것은 Runner 다.
        배치만 보는 detector 는 되돌아보기가 없어 이 값을 무시한다.
        """
        raise NotImplementedError

    def _lookback_start(self, anchor: datetime, since: datetime | None) -> datetime:
        """되돌아보기 시작점 — 창 시작과 `since` 중 늦은 쪽. since 가 창보다 과거면 창이 이긴다."""
        lookback = int(self.condition.get("window_sec", 210))
        start = anchor - timedelta(seconds=lookback)
        return start if since is None else max(start, since)
