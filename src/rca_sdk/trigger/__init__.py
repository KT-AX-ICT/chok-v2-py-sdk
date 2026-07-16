"""④ 트리거 계층 — 각 trigger별 조건으로 이상을 감지해 낱개 근거(TriggerEvidence)를 낸다.

모달리티 수렴(correlation)은 엣지에서 제외되어 중앙 RCA가 담당한다(§0-4).
"""

from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence

__all__ = ["TriggerDetector", "TriggerEvidence"]
