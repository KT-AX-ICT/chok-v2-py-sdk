"""perf · metric — cpu_spike (plateau).

host CPU(`system_cpu_usage`)가 bar(기본 50%)를 넘는 샘플이 최근 창(condition window_sec, 기본 210초)
안에서 min_over(기본 5)개 이상 누적되면 발화한다. 단일 봉우리(1회 초과)가 아니라 "높은 샘플의
지속(plateau)"으로 판정한다 — 실측상 median/단일절대는 판별 불가고, baseline은 3/80 산발 vs
주입은 23/80 연속이다(ADR-006). container_cpu 는 국소화용이라 트리거 대상이 아니다.
무상태: 매 evaluate 마다 buffer.get_snapshot 으로 창을 다시 센다(restart_marker 와 동형).
"""

from __future__ import annotations

from datetime import datetime

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.events import Modality, NormalizedBatch, NormalizedMetric
from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence

# host CPU (node-exporter). container_cpu 는 트리거 아님(ADR-006).
# 값은 MetricNormalizer 가 파일명에서 유도하는 metric_name 과 정확히 일치해야 한다
# (`system_cpu_usage.csv` → `system_cpu_usage`). 어긋나면 예외 없이 조용히 0건이 된다.
CPU_METRIC = "system_cpu_usage"


class CpuSpikeDetector(TriggerDetector):
    MODALITY = Modality.METRIC
    DETECTOR_TYPE = "cpu_spike"

    def evaluate(
        self,
        new_batch: NormalizedBatch,
        buffer: MemoryBuffer,
        since: datetime | None = None,
    ) -> list[TriggerEvidence]:
        if new_batch.modality != self.MODALITY:
            return []  # metric 배치만 평가

        bar = float(self.condition.get("bar", 50.0))         # 샘플을 '높음'으로 치는 기준선(%)
        min_over = int(self.condition.get("min_over", 5))    # 윈도 내 초과 샘플 최소 개수(plateau)

        # 이번 배치가 아니라 최근 window_sec 구간을 계약의 get_snapshot 으로만 조회한다
        # (buffer 내부 속성에 의존하지 않음 — 계약 §2.3).
        # since 가 있으면 그 뒤만 센다 — 직전 번들이 담아 간 샘플로 재발화하지 않게 (계획 04 §7-3).
        anchor = new_batch.observed_until
        start = self._lookback_start(anchor, since)
        snapshot = buffer.get_snapshot(start, anchor)

        # 윈도 내 system_cpu_usage 샘플 중 bar 초과분을 모은다.
        over = [
            rec
            for rec in snapshot.metrics
            if isinstance(rec, NormalizedMetric)
            and rec.metric_name == CPU_METRIC
            and rec.value is not None
            and rec.value > bar
        ]
        if len(over) < min_over:
            return []  # 산발 스파이크(초과 소수)는 무시 → 지속(plateau)만 발화

        over_sorted = sorted(over, key=lambda r: r.timestamp)
        confirm = over_sorted[min_over - 1]  # min_over 번째 초과 = plateau 확증 시점
        peak = max(rec.value for rec in over if rec.value is not None)
        return [
            TriggerEvidence(
                trigger_time=confirm.timestamp,
                modality=self.MODALITY,
                service=confirm.service,  # 호스트 지표면 "__node__"
                detector_type=self.DETECTOR_TYPE,
                value=float(len(over)),  # 초과 샘플 수 = plateau 강도
                baseline=float(self.condition.get("baseline", 0.0)),
                threshold=float(min_over),
                extra={"bar": bar, "max_cpu": float(peak)},
            )
        ]
