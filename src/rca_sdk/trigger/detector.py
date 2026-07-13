"""모달리티별 baseline 편차 감지 (스캐폴드).

기존 analysis/detectors 의 evaluate() 순수 함수 로직을 실시간 버퍼 입력으로 포팅한다.
입력: buffer.window_events() 의 NormalizedEvent 목록 + baseline 프로파일.
출력: 모달리티별 ModalitySignal.

미해결(ADR-003): coverage_dir_missing 처럼 실시간에 관측 불가한 신호는 여기서 제외하고,
svc_kill(재시작 마커) / code_stop(trace 5xx·TTransportException) 을 실시간 신호로 재정의해야 한다.
"""

from __future__ import annotations

from typing import Any

from rca_sdk.schemas.events import NormalizedEvent
from rca_sdk.trigger.models import ModalitySignal


def detect_all(events: list[NormalizedEvent], baseline: dict[str, Any]) -> list[ModalitySignal]:
    """전체 모달리티 감지 → ModalitySignal 목록 (스캐폴드)."""
    # TODO: log/metric/trace 각 evaluate 구현 후 취합.
    return []
