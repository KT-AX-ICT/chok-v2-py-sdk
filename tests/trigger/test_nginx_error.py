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


# ── since (평가 하한) — 배치 기반 detector 도 지켜야 한다 ────────────────────
#
# 배치는 직전 번들 창 끝(since)을 **걸칠 수 있다.** 걸친 배치의 앞부분 레코드는 이미
# 번들에 실려 나갔으므로 다시 세면 안 된다 — 창 기반 detector 와 같은 규칙이다.
# 시나리오 재생에서 재발화 anchor 가 직전 번들 창 끝보다 과거로 잡히며 드러났다.


def conn_at(offset_sec: float) -> NormalizedLog:
    return NormalizedLog(
        timestamp=TS - timedelta(seconds=offset_sec),
        service="nginx",
        event_type="connection_error",
    )


def test_since_excludes_records_already_bundled():
    # 배치에 4건이지만 since 뒤는 2건뿐 → 임계(3) 미달 → 무발화
    records = [conn_at(25), conn_at(20), conn_at(10), conn_at(5)]
    detector = NginxErrorDetector(COND)
    assert detector.evaluate(batch(records), None, since=TS - timedelta(seconds=15)) == []


def test_since_is_inclusive_lower_bound():
    # since 와 같은 시각은 포함 — 직전 번들이 [.., end) 로 제외했으므로 누락 없음.
    # since 뒤 4건(20·15·10·5)이라야 임계 3 을 **초과**한다.
    records = [conn_at(25), conn_at(20), conn_at(15), conn_at(10), conn_at(5)]
    ev = NginxErrorDetector(COND).evaluate(
        batch(records), None, since=TS - timedelta(seconds=20)
    )
    assert len(ev) == 1
    assert ev[0].value == 4.0


def test_trigger_time_never_precedes_since():
    """anchor 가 직전 번들 안으로 끌려가지 않는다 — since 의 존재 이유."""
    records = [conn_at(25), conn_at(20), conn_at(12), conn_at(10), conn_at(5), conn_at(1)]
    since = TS - timedelta(seconds=15)
    [ev] = NginxErrorDetector(COND).evaluate(batch(records), None, since=since)
    assert ev.trigger_time >= since


def test_since_none_keeps_current_behavior():
    records = [conn_at(25), conn_at(20), conn_at(10), conn_at(5)]
    assert NginxErrorDetector(COND).evaluate(batch(records), None, since=None) == (
        NginxErrorDetector(COND).evaluate(batch(records), None)
    )
