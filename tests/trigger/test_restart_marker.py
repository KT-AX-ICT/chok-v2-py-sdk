"""RestartMarkerDetector 단위 테스트.

실데이터 기반 시각(Svc_Kill_Media): media 부팅 00:01:57 / 00:03:41 (104초 간격, 210초 윈도 안).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.schemas.events import (
    Modality,
    MultimodalSnapshot,
    NormalizedBatch,
    NormalizedLog,
)
from rca_sdk.trigger.svc_kill.log import RestartMarkerDetector


class FakeBuffer:
    """계약(get_snapshot)만 흉내내는 대역 — window_sec 같은 내부 속성은 없다."""

    def __init__(self, logs: list[NormalizedLog]) -> None:
        self._logs = logs

    def get_snapshot(self, start_ts: datetime, end_ts: datetime) -> MultimodalSnapshot:
        logs = [rec for rec in self._logs if start_ts <= rec.timestamp < end_ts]
        return MultimodalSnapshot(logs=logs)


def boot(service: str, ts: datetime) -> NormalizedLog:
    return NormalizedLog(timestamp=ts, service=service, event_type="service_start")


def log_batch(observed_until: datetime) -> NormalizedBatch:
    return NormalizedBatch(
        modality=Modality.LOG,
        observed_from=observed_until - timedelta(seconds=30),
        observed_until=observed_until,
    )


BOOT1 = datetime(2025, 11, 4, 0, 1, 57)
BOOT2 = datetime(2025, 11, 4, 0, 3, 41)
ANCHOR = datetime(2025, 11, 4, 0, 4, 0)


def test_fires_on_second_boot_marker():
    buffer = FakeBuffer([boot("media", BOOT1), boot("media", BOOT2)])
    detector = RestartMarkerDetector({"threshold": 2, "baseline": 1.0})
    ev = detector.evaluate(log_batch(ANCHOR), buffer)
    assert len(ev) == 1
    assert ev[0].detector_type == "restart_marker"
    assert ev[0].service == "media"
    assert ev[0].value == 2.0
    assert ev[0].baseline == 1.0
    assert ev[0].threshold == 2.0
    assert ev[0].trigger_time == BOOT2


def test_normal_single_boot_does_not_fire():
    buffer = FakeBuffer([boot("media", BOOT1), boot("user", BOOT1), boot("nginx", BOOT1)])
    assert RestartMarkerDetector({"threshold": 2}).evaluate(log_batch(ANCHOR), buffer) == []


def test_identifies_only_the_restarted_service():
    buffer = FakeBuffer(
        [boot("media", BOOT1), boot("media", BOOT2), boot("user", BOOT1), boot("nginx", BOOT1)]
    )
    ev = RestartMarkerDetector({"threshold": 2}).evaluate(log_batch(ANCHOR), buffer)
    assert [e.service for e in ev] == ["media"]


def test_ignores_non_log_batch():
    buffer = FakeBuffer([boot("media", BOOT1), boot("media", BOOT2)])
    metric_batch = NormalizedBatch(
        modality=Modality.METRIC,
        observed_from=ANCHOR - timedelta(seconds=30),
        observed_until=ANCHOR,
    )
    assert RestartMarkerDetector({"threshold": 2}).evaluate(metric_batch, buffer) == []


def test_only_counts_service_start_event_type():
    logs = [
        boot("media", BOOT1),
        NormalizedLog(timestamp=BOOT2, service="media", event_type="normal_log"),
    ]
    result = RestartMarkerDetector({"threshold": 2}).evaluate(log_batch(ANCHOR), FakeBuffer(logs))
    assert result == []


def test_boot_outside_window_not_counted():
    old_boot = datetime(2025, 11, 3, 23, 59, 0)
    buffer = FakeBuffer([boot("media", old_boot), boot("media", BOOT2)])
    assert RestartMarkerDetector({"threshold": 2}).evaluate(log_batch(ANCHOR), buffer) == []
