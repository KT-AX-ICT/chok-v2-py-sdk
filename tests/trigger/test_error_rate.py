"""error_rate (perf/log) 단위 테스트 — error 건수 임계."""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.schemas.events import Modality, NormalizedBatch, NormalizedLog
from rca_sdk.trigger.perf.log import ErrorRateDetector

TS = datetime(2025, 11, 3, 22, 28, 31)
ERR_COND = {"baseline": 5.0, "ratio": 2.5, "floor": 3.0}  # threshold = 12.5


def batch(records: list) -> NormalizedBatch:
    return NormalizedBatch(
        modality=Modality.LOG,
        observed_from=TS - timedelta(seconds=30),
        observed_until=TS,
        records=records,
    )


def errlog(level: str = "error") -> NormalizedLog:
    return NormalizedLog(timestamp=TS, service="user", level=level)


def test_error_rate_fires_on_count_above_threshold():
    ev = ErrorRateDetector(ERR_COND).evaluate(batch([errlog() for _ in range(13)]), None)
    assert len(ev) == 1
    assert ev[0].detector_type == "error_rate"
    assert ev[0].value == 13.0
    assert ev[0].trigger_time == TS  # observed_until


def test_error_rate_silent_on_low_count():
    recs = [errlog() for _ in range(5)] + [errlog(level="info") for _ in range(5)]
    assert ErrorRateDetector(ERR_COND).evaluate(batch(recs), None) == []


def test_error_rate_silent_when_no_error():
    assert ErrorRateDetector(ERR_COND).evaluate(batch([errlog(level="info")]), None) == []
