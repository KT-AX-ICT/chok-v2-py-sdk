"""trace_5xx (code_stop/trace) 단위 테스트 — 500 span 건수 임계."""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.schemas.events import Modality, NormalizedBatch, NormalizedTrace
from rca_sdk.trigger.code_stop.trace import TraceFivexxDetector

TS = datetime(2025, 11, 4, 3, 0, 0)
COND = {"baseline": 0.0, "floor": 3.0}  # threshold = 3.0


def batch(records: list) -> NormalizedBatch:
    return NormalizedBatch(
        modality=Modality.TRACE,
        observed_from=TS - timedelta(seconds=30),
        observed_until=TS,
        records=records,
    )


def span(code: int) -> NormalizedTrace:
    return NormalizedTrace(timestamp=TS, service="nginx", http_status_code=code)


def test_trace_5xx_fires_on_500_count():
    ev = TraceFivexxDetector(COND).evaluate(batch([span(500) for _ in range(4)]), None)
    assert len(ev) == 1
    assert ev[0].detector_type == "trace_5xx"
    assert ev[0].service == "nginx"
    assert ev[0].value == 4.0


def test_trace_5xx_silent_when_no_500():
    assert TraceFivexxDetector(COND).evaluate(batch([span(200) for _ in range(10)]), None) == []


def test_trace_5xx_ignores_non_trace_batch():
    log_batch = NormalizedBatch(modality=Modality.LOG, observed_from=TS, observed_until=TS)
    assert TraceFivexxDetector(COND).evaluate(log_batch, None) == []
