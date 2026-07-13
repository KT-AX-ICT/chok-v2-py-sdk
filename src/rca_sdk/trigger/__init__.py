"""④ 트리거 계층 — baseline 편차 감지 + 다중 모달리티 상관으로 incident 를 수렴한다.

기존 연구 코드(AnoMod analysis/sn_db/detectors) 의 evaluate/correlate 로직을 실시간 버퍼
입력에 맞게 포팅한다. 배치 폴더 로딩(detect) 부분은 재작성 대상.
"""

from rca_sdk.trigger.models import Candidate, CandidateIncident, ModalitySignal

__all__ = ["Candidate", "CandidateIncident", "ModalitySignal"]
