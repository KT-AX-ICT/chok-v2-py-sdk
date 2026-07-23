"""로그 truncate(서비스별 볼륨 캡) 단위 테스트 — assembler._truncate_logs / SnapshotManager 연동.

exempt 규칙(level!=info, event_type!=normal_log, trigger 귀속 서비스)과 cap/backstop_cap,
modality_info 의 totalCount/recordCount 전달까지 검증한다. truncate 여부는 별도 bool 필드
없이 record_count < total_count 로 판별한다(서버 요청으로 필드 제거, 2026-07-23).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.schemas.events import Modality, MultimodalSnapshot, NormalizedLog, SourceStatus
from rca_sdk.snapshot.assembler import POST_SEC, SnapshotManager
from rca_sdk.trigger.models import TriggerEvidence

ANCHOR = datetime(2026, 1, 15, 10, 1, 30)


class FakeBuffer:
    def __init__(self, logs=None, coverage=None) -> None:
        self._logs = logs or []
        self._coverage = coverage or {}

    def get_snapshot(self, start_ts: datetime, end_ts: datetime) -> MultimodalSnapshot:
        # 실제 MemoryBuffer 는 pre/post 각 질의 구간과 겹치는 배치만 roster 에 반영한다
        # (_aggregate_roster). 이 픽스처의 로그는 전부 Pre 구간에 있으므로, coverage 도
        # Pre 질의(end_ts<=anchor)에만 실어야 pre+post 합산 시 record_count 가 중복되지 않는다.
        coverage = self._coverage if end_ts <= ANCHOR else {}
        return MultimodalSnapshot(
            logs=[r for r in self._logs if start_ts <= r.timestamp < end_ts],
            coverage=coverage,
        )


def evidence(service: str | None, trigger_time: datetime = ANCHOR) -> TriggerEvidence:
    return TriggerEvidence(
        trigger_time=trigger_time,
        modality=Modality.LOG,
        service=service,
        detector_type="x",
        value=1.0,
        baseline=0.0,
        threshold=0.0,
    )


def make_logs(
    n: int,
    service: str = "socialgraph",
    level: str = "info",
    event_type: str = "normal_log",
    start: datetime = ANCHOR - timedelta(seconds=170),
) -> list[NormalizedLog]:
    return [
        NormalizedLog(
            timestamp=start + timedelta(seconds=i),
            service=service,
            level=level,
            event_type=event_type,
        )
        for i in range(n)
    ]


def _run(
    logs: list[NormalizedLog],
    *,
    cap: int = 5,
    backstop_cap: int = 10,
    exempt=(),
    service: str = "socialgraph",
) -> object:
    # coverage 의 source 는 실제 로그 service 명과 일치해야 modality_info 의
    # record_count(=included count)가 제대로 매칭된다 (assembler._modality_info 참고).
    coverage = {"log": [SourceStatus(source=service, present=True, record_count=len(logs))]}
    buf = FakeBuffer(logs=logs, coverage=coverage)
    m = SnapshotManager(log_truncation_cap=cap, log_truncation_backstop_cap=backstop_cap)
    m.register_triggers([evidence(s) for s in exempt] or [evidence(None)], buf)
    return m.finalize_ready(ANCHOR + timedelta(seconds=POST_SEC), buf)[0]


def test_under_cap_is_noop():
    logs = make_logs(3)
    b = _run(logs, cap=5)
    assert len(b.logs) == 3
    interval = b.modality_info["log"].intervals[0]
    assert interval.total_count == 3
    assert interval.record_count == 3


def test_over_cap_is_sampled_down_to_cap():
    logs = make_logs(20)
    b = _run(logs, cap=5, backstop_cap=50)
    assert len(b.logs) == 5
    interval = b.modality_info["log"].intervals[0]
    assert interval.total_count == 20
    assert interval.record_count == 5
    assert interval.record_count < interval.total_count


def test_exempt_service_ignores_tight_cap():
    logs = make_logs(20, service="media")
    b = _run(logs, cap=5, backstop_cap=50, exempt=["media"], service="media")
    assert len(b.logs) == 20  # trigger 귀속 서비스라 tight cap 무시
    interval = b.modality_info["log"].intervals[0]
    assert interval.record_count == interval.total_count


def test_non_info_level_is_never_capped():
    # cap=2 인데 error 레벨 5건 — 전부 보존
    logs = make_logs(5, level="error")
    b = _run(logs, cap=2, backstop_cap=50)
    assert len(b.logs) == 5


def test_non_normal_log_event_type_is_never_capped():
    # service_start(restart_marker 원천) 는 info 레벨이어도 cap 대상이 아니다
    logs = make_logs(5, level="info", event_type="service_start")
    b = _run(logs, cap=2, backstop_cap=50)
    assert len(b.logs) == 5


def test_mixed_level_only_caps_info_normal_log():
    protected = make_logs(3, level="error", start=ANCHOR - timedelta(seconds=170))
    candidates = make_logs(20, level="info", start=ANCHOR - timedelta(seconds=100))
    b = _run(protected + candidates, cap=5, backstop_cap=50)
    assert len(b.logs) == 3 + 5  # error 3건 그대로 + info 20건 -> 5건


def test_backstop_caps_even_exempt_service():
    # exempt 서비스라도 backstop_cap 은 넘지 못한다 (미지의 폭주 대비 상한)
    logs = make_logs(100, service="media")
    b = _run(logs, cap=5, backstop_cap=10, exempt=["media"], service="media")
    assert len(b.logs) == 10
    interval = b.modality_info["log"].intervals[0]
    assert interval.total_count == 100
    assert interval.record_count == 10
    assert interval.record_count < interval.total_count


def test_result_stays_time_sorted():
    logs = make_logs(30)
    b = _run(logs, cap=7, backstop_cap=50)
    timestamps = [r.timestamp for r in b.logs]
    assert timestamps == sorted(timestamps)


def test_truncation_can_be_disabled():
    logs = make_logs(50)
    coverage = {"log": [SourceStatus(source="socialgraph", present=True, record_count=50)]}
    buf = FakeBuffer(logs=logs, coverage=coverage)
    m = SnapshotManager(log_truncation_enabled=False, log_truncation_cap=5)
    m.register_triggers([evidence(None)], buf)
    bundle = m.finalize_ready(ANCHOR + timedelta(seconds=POST_SEC), buf)[0]
    assert len(bundle.logs) == 50
    interval = bundle.modality_info["log"].intervals[0]
    assert interval.record_count == interval.total_count


def test_default_cap_matches_config_default():
    from rca_sdk.config import Settings

    assert Settings().log_truncation_cap == 5000
    assert Settings().log_truncation_backstop_cap == 50000
    assert Settings().log_truncation_enabled is True
