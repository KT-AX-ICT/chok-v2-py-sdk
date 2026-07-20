"""nginx_error (code_stop/log) 단위 테스트 — connection_error 건수 임계."""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.schemas.events import Modality, NormalizedBatch, NormalizedLog
from rca_sdk.trigger.code_stop.log import NginxErrorDetector

TS = datetime(2025, 11, 4, 3, 0, 0)
COND = {"baseline": 0.0, "floor": 3.0}  # threshold = 3.0


def batch(records: list) -> NormalizedBatch:
    return NormalizedBatch(
        modality=Modality.LOG,
        observed_from=TS - timedelta(seconds=30),
        observed_until=TS,
        records=records,
    )


def connlog() -> NormalizedLog:
    return NormalizedLog(timestamp=TS, service="nginx", event_type="connection_error")


def test_nginx_error_fires_on_conn_error_count():
    ev = NginxErrorDetector(COND).evaluate(batch([connlog() for _ in range(4)]), None)
    assert len(ev) == 1
    assert ev[0].detector_type == "nginx_error"
    assert ev[0].service == "nginx"
    assert ev[0].value == 4.0


def test_nginx_error_silent_without_conn_error():
    recs = [NormalizedLog(timestamp=TS, service="nginx", event_type="normal_log")]
    assert NginxErrorDetector(COND).evaluate(batch(recs), None) == []
