"""④ 트리거 계층 — 각 trigger별 조건으로 이상을 감지해 낱개 근거(TriggerEvidence)를 낸다.

모달리티 수렴(correlation)은 엣지에서 제외되어 중앙 RCA가 담당한다(§0-4).
"""

from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence

# [미사용 · 주석처리] correlation 전용 모델 export
# 사유: correlation 엣지 제외(§0-4)로 Candidate/CandidateIncident/ModalitySignal 이 죽은 코드.
#       models.py 에서 주석처리됨 → 여기 import/export 도 함께 주석처리. (2026-07-15)
# from rca_sdk.trigger.models import (
#     Candidate,
#     CandidateIncident,
#     ModalitySignal,
# )

__all__ = [
    "TriggerDetector",
    "TriggerEvidence",
]
