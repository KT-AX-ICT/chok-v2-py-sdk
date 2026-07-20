"""cpu_spike (perf/metric, plateau) 단위 테스트.

host cpu(system_cpu_usage) 중 bar 초과 샘플이 buffer 윈도에서 min_over 이상 누적되면 발화.
단일 봉우리가 아니라 지속(plateau)으로 판정 (ADR-006).

여기 있는 것은 **알고리즘(plateau 판정) 테스트**라 대상 metric_name 을 하드코딩하지 않고
운영 상수 `CPU_METRIC` 을 그대로 쓴다. 그 상수가 Normalizer 실출력과 맞는지(계약)는
`test_realdata.py::test_cpu_metric_name_matches_normalizer_output` 이 따로 고정한다 —
둘을 갈라두지 않으면 이름이 어긋나도 여기 테스트가 통과해 무발화를 못 잡는다
(ADR-006 미결 §metric_name).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.schemas.events import (
    Modality,
    MultimodalSnapshot,
    NormalizedBatch,
    NormalizedMetric,
)
from rca_sdk.trigger.perf.metric import CPU_METRIC, CpuSpikeDetector

TS = datetime(2025, 11, 3, 22, 30, 0)
COND = {"bar": 50.0, "min_over": 5}


class FakeBuffer:
    """계약(get_snapshot)만 흉내내는 대역 — window_sec 같은 내부 속성은 없다."""

    def __init__(self, metrics: list[NormalizedMetric]) -> None:
        self._metrics = metrics

    def get_snapshot(self, start_ts: datetime, end_ts: datetime) -> MultimodalSnapshot:
        metrics = [m for m in self._metrics if start_ts <= m.timestamp < end_ts]
        return MultimodalSnapshot(metrics=metrics)

    def scan(self, start_ts: datetime, end_ts: datetime, modality: Modality):
        return sorted(
            (m for m in self._metrics if start_ts <= m.timestamp < end_ts),
            key=lambda r: r.timestamp,
        )


def samples(values: list[float], name: str = CPU_METRIC) -> list[NormalizedMetric]:
    start = TS - timedelta(seconds=200)  # 윈도 [TS-210, TS) 안
    return [
        NormalizedMetric(
            timestamp=start + timedelta(seconds=15 * i),
            service="__node__",
            metric_name=name,
            value=v,
        )
        for i, v in enumerate(values)
    ]


def metric_batch() -> NormalizedBatch:
    return NormalizedBatch(
        modality=Modality.METRIC, observed_from=TS - timedelta(seconds=30), observed_until=TS
    )


def test_fires_on_sustained_plateau():
    # >50 샘플 6개 = min_over(5) 이상 → 발화
    buffer = FakeBuffer(samples([4, 60, 70, 88, 92, 99, 97, 8]))
    ev = CpuSpikeDetector(COND).evaluate(metric_batch(), buffer)
    assert len(ev) == 1
    assert ev[0].detector_type == "cpu_spike"
    assert ev[0].modality == Modality.METRIC
    assert ev[0].value == 6.0  # 초과 샘플 수
    assert ev[0].threshold == 5.0
    assert ev[0].extra["max_cpu"] == 99.0


def test_silent_on_sporadic_spikes():
    # >50 샘플 3개(<5) = 산발 노이즈 → 무발화
    buffer = FakeBuffer(samples([4, 81, 5, 6, 70, 4, 55, 3]))
    assert CpuSpikeDetector(COND).evaluate(metric_batch(), buffer) == []


def test_ignores_container_cpu():
    # container_cpu 는 트리거 대상 아님 — host cpu 만 카운트
    buffer = FakeBuffer(samples([99, 99, 99, 99, 99, 99], name="container_cpu"))
    assert CpuSpikeDetector(COND).evaluate(metric_batch(), buffer) == []


def test_ignores_non_metric_batch():
    buffer = FakeBuffer(samples([99, 99, 99, 99, 99, 99]))
    log_batch = NormalizedBatch(
        modality=Modality.LOG, observed_from=TS - timedelta(seconds=30), observed_until=TS
    )
    assert CpuSpikeDetector(COND).evaluate(log_batch, buffer) == []


def test_trigger_time_is_confirmation_sample():
    recs = samples([60, 70, 80, 90, 95, 99])  # 전부 >50, 6개
    ev = CpuSpikeDetector(COND).evaluate(metric_batch(), FakeBuffer(recs))
    # min_over=5 → 5번째 초과 샘플에서 plateau 확증
    assert ev[0].trigger_time == recs[4].timestamp


# ── since (평가 하한) — 계획 04 §7-3 ─────────────────────────────────────────
# 직전 번들이 담아 전송한 구간을 다시 세지 않게 되돌아보기 시작점을 자른다.


def test_since_clips_lookback_and_suppresses_refire():
    # 6개 전부 초과지만, since 를 5번째 샘플 시각으로 두면 셀 수 있는 건 2개뿐 → 무발화
    recs = samples([60, 70, 80, 90, 95, 99])
    ev = CpuSpikeDetector(COND).evaluate(
        metric_batch(), FakeBuffer(recs), since=recs[4].timestamp
    )
    assert ev == []


def test_since_is_inclusive_lower_bound():
    # since 와 정확히 같은 시각의 샘플은 포함된다 — 직전 번들이 [.., end) 로 제외했으므로
    # 누락도 중복도 없다. since=recs[1] 이면 recs[1..5] 5개가 남아 min_over(5) 충족.
    recs = samples([60, 70, 80, 90, 95, 99])
    ev = CpuSpikeDetector(COND).evaluate(
        metric_batch(), FakeBuffer(recs), since=recs[1].timestamp
    )
    assert len(ev) == 1
    assert ev[0].value == 5.0
    assert ev[0].trigger_time == recs[5].timestamp  # 5번째 초과 = 마지막 = 최신


def test_since_older_than_window_does_not_widen_lookback():
    # since 가 창보다 과거면 창이 이긴다 — max() 라 되돌아보기가 넓어지지 않는다
    recs = samples([60, 70, 80, 90, 95, 99])
    far_past = TS - timedelta(days=1)
    with_since = CpuSpikeDetector(COND).evaluate(metric_batch(), FakeBuffer(recs), since=far_past)
    without = CpuSpikeDetector(COND).evaluate(metric_batch(), FakeBuffer(recs))
    assert with_since == without


def test_since_none_keeps_current_behavior():
    recs = samples([60, 70, 80, 90, 95, 99])
    assert CpuSpikeDetector(COND).evaluate(
        metric_batch(), FakeBuffer(recs), since=None
    ) == CpuSpikeDetector(COND).evaluate(metric_batch(), FakeBuffer(recs))
