"""svc_kill · log — restart_marker.

buffer 윈도(210초) 안의 부팅 마커(event_type=="service_start")를 canonical_service 별로
세어 threshold(기본 2) 이상이면 발화. 발화 서비스명이 곧 kill 후 재시작된 서비스.
무상태: 매 evaluate 마다 buffer 윈도를 다시 센다(설계 §5.4).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.events import Modality, NormalizedBatch
from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence


class RestartMarkerDetector(TriggerDetector):
    MODALITY = Modality.LOG
    DETECTOR_TYPE = "restart_marker"
    BOOT_EVENT_TYPE = "service_start"

    def evaluate(self, new_batch: NormalizedBatch, buffer: MemoryBuffer) -> list[TriggerEvidence]:
        if new_batch.modality != self.MODALITY:
            return []  # log 배치만 평가

        threshold = max(1, int(self.condition.get("threshold", 2)))  # 최소 1 보장(음수/0 방어)
        baseline = float(self.condition.get("baseline", 1.0))

        # 부팅 2회가 배치를 가로지르므로 이번 배치가 아니라 buffer 210초 윈도 전체를 본다.
        anchor = new_batch.observed_until
        start = anchor - timedelta(seconds=buffer.window_sec)
        snapshot = buffer.get_snapshot(start, anchor)

        # 윈도 내 부팅 마커(service_start)를 서비스별로 모은다.
        boots: dict[str, list[datetime]] = {}
        for rec in snapshot.logs:
            if rec.event_type == self.BOOT_EVENT_TYPE and rec.canonical_service is not None:
                boots.setdefault(rec.canonical_service, []).append(rec.timestamp)

        # 부팅 마커가 threshold(2) 이상인 서비스 = kill 후 재시작된 대상 → 발화.
        evidences: list[TriggerEvidence] = []
        for service, times in boots.items():
            if len(times) >= threshold:
                nth = sorted(times)[threshold - 1]  # trigger_time = 2회째(N번째) 부팅 시각
                evidences.append(
                    TriggerEvidence(
                        trigger_time=nth,
                        modality=self.MODALITY,
                        service=service,
                        detector_type=self.DETECTOR_TYPE,
                        value=float(len(times)),
                        baseline=baseline,
                        threshold=float(threshold),
                        extra={"boot_marker_count": len(times)},
                    )
                )
        return evidences
