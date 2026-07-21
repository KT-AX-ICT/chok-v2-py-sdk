"""숫자 임계 detector 공통 base (설계 §3).

무상태: 이번 배치에서 대표값을 뽑아 condition 기반 임계와 비교, 초과 시 1건 발화.
임계는 코드에 박지 않고 condition 으로만 주입한다(계약 §0-5).
서브클래스는 MODALITY / DETECTOR_TYPE 과 _value_and_meta() 를 정의한다.
"""

from __future__ import annotations

from datetime import datetime

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.events import Modality, NormalizedBatch
from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence


class NumericThresholdDetector(TriggerDetector):
    MODALITY: Modality
    DETECTOR_TYPE: str

    def _value_and_meta(
        self, new_batch: NormalizedBatch
    ) -> tuple[float, str | None, datetime] | None:
        """이번 배치의 (대표값, service, trigger_time). 신호 없으면 None."""
        raise NotImplementedError

    def _threshold(self) -> float:
        # 임계 = max(baseline×ratio, floor). count 계열(baseline≈0)은 floor 가 실질 임계.
        baseline = float(self.condition["baseline"])
        ratio = float(self.condition.get("ratio", 1.0))
        floor = float(self.condition.get("floor", 0.0))
        return max(baseline * ratio, floor)

    def evaluate(
        self,
        new_batch: NormalizedBatch,
        buffer: MemoryBuffer,
        since: datetime | None = None,
    ) -> list[TriggerEvidence]:
        # buffer·since 는 시그니처용 — 숫자 detector 는 이번 배치만 보므로 되돌아보기가 없다.
        # 배치는 항상 직전 번들 이후라 자를 것도 없다.
        if new_batch.modality != self.MODALITY:
            return []  # 자기 모달리티 배치만 평가 (metric detector 는 log 배치 무시)
        result = self._value_and_meta(new_batch)
        if result is None:
            return []  # 배치에 이 신호 자체가 없음 → 무발화
        value, service, trigger_time = result
        threshold = self._threshold()
        if value <= threshold:
            return []  # 임계 이하 = 정상 → 무발화
        # 임계 초과 → 낱개 근거(TriggerEvidence) 1건. 수렴은 중앙 RCA 몫.
        return [
            TriggerEvidence(
                trigger_time=trigger_time,
                modality=self.MODALITY,
                service=service,
                detector_type=self.DETECTOR_TYPE,
                value=value,
                baseline=float(self.condition["baseline"]),  # 정적 baseline 그대로(재산출 안 함)
                threshold=threshold,
                extra={},
            )
        ]
