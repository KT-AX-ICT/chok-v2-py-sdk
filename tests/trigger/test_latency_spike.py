"""latency_spike (perf/trace) 단위 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.schemas.events import Modality, NormalizedBatch, NormalizedTrace
from rca_sdk.trigger.perf.trace import LatencySpikeDetector

TS = datetime(2025, 11, 3, 22, 28, 31)
LAT_COND = {"baseline": 2.0, "ratio": 1.6, "floor": 3.0}  # threshold = 3.2


def batch(records: list) -> NormalizedBatch:
    return NormalizedBatch(
        modality=Modality.TRACE,
        observed_from=TS - timedelta(seconds=30),
        observed_until=TS,
        records=records,
    )


def trace(duration_ms: float, svc: str = "compose") -> NormalizedTrace:
    return NormalizedTrace(timestamp=TS, service=svc, duration_ms=duration_ms)


def test_latency_spike_fires_above_threshold():
    ev = LatencySpikeDetector(LAT_COND).evaluate(batch([trace(21.9)]), None)
    assert len(ev) == 1
    assert ev[0].detector_type == "latency_spike"
    assert ev[0].value == 21.9
    assert ev[0].service == "compose"


def test_latency_spike_silent_below_threshold():
    assert LatencySpikeDetector(LAT_COND).evaluate(batch([trace(1.8)]), None) == []


def test_latency_spike_picks_max_duration():
    ev = LatencySpikeDetector(LAT_COND).evaluate(batch([trace(1.8), trace(21.9), trace(5.0)]), None)
    assert ev[0].value == 21.9


def test_latency_spike_ignores_non_trace_batch():
    metric_only = NormalizedBatch(
        modality=Modality.METRIC, observed_from=TS, observed_until=TS
    )
    assert LatencySpikeDetector(LAT_COND).evaluate(metric_only, None) == []
