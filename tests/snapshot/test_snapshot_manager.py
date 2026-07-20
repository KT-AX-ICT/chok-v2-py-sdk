"""SnapshotManager 단위 테스트. FakeBuffer(계약 get_snapshot만)로 검증."""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.config import Settings
from rca_sdk.normalization.log import LogNormalizer
from rca_sdk.schemas.events import (
    Modality,
    MultimodalSnapshot,
    NormalizedLog,
    NormalizedMetric,
    RawBatch,
    SourceStatus,
)
from rca_sdk.snapshot.assembler import POST_SEC, PRE_SEC, SnapshotManager
from rca_sdk.trigger.models import TriggerEvidence

ANCHOR = datetime(2026, 1, 15, 10, 1, 30)
NGINX_LINE = "2025/11/04 02:58:25 [error] 9#9: *816 compose failure"


class FakeBuffer:
    """계약 get_snapshot 만 흉내내는 대역 — timestamp 로 구간 필터."""

    def __init__(self, logs=None, metrics=None, traces=None, coverage=None) -> None:
        self._logs = logs or []
        self._metrics = metrics or []
        self._traces = traces or []
        self._coverage = coverage or {}

    def get_snapshot(self, start_ts: datetime, end_ts: datetime) -> MultimodalSnapshot:
        return MultimodalSnapshot(
            logs=[r for r in self._logs if start_ts <= r.timestamp < end_ts],
            metrics=[r for r in self._metrics if start_ts <= r.timestamp < end_ts],
            traces=[r for r in self._traces if start_ts <= r.timestamp < end_ts],
            coverage=self._coverage,
        )


def evidence(modality: Modality, trigger_time: datetime = ANCHOR) -> TriggerEvidence:
    return TriggerEvidence(
        trigger_time=trigger_time,
        modality=modality,
        service=None,
        detector_type="x",
        value=1.0,
        baseline=0.0,
        threshold=0.0,
    )


def log_at(ts: datetime) -> NormalizedLog:
    return NormalizedLog(timestamp=ts, service="nginx", event_type="normal_log")


def metric_at(ts: datetime) -> NormalizedMetric:
    return NormalizedMetric(
        timestamp=ts,
        service="__node__",
        metric_name="system_cpu_usage",
        value=9.0,
    )


def test_window_constants_match_configured_design():
    """계약 고정: PRE_SEC/POST_SEC 가 설계값(ADR-001)·config 와 같은지.

    다른 테스트들은 PRE_SEC 을 import 해 쓰므로 값이 틀려도 통과한다(창 계산 로직만 검증).
    실제 초 수가 설계와 맞는지는 여기서만 깨진다.

    현재는 앞뒤 대칭 180/180. Pre 를 210 으로 두는 비대칭 안은 검증 중이다(ADR-001).
    """
    settings = Settings()
    assert PRE_SEC == settings.buffer_window_sec == 180
    assert POST_SEC == settings.post_trigger_wait_sec == 180
    # 버퍼 보존은 pre+post 를 담을 만큼이어야 한다 (ADR-001 §19)
    assert MemoryBuffer().retention_sec >= PRE_SEC + POST_SEC


def test_register_opens_session_and_captures_pre():
    # pre 구간 [anchor-PRE_SEC, anchor) 에 로그 1건
    buf = FakeBuffer(logs=[log_at(ANCHOR - timedelta(seconds=60))])
    m = SnapshotManager()
    m.register_triggers([evidence(Modality.METRIC)], buf)
    s = m._session
    assert s is not None
    assert s.anchor == ANCHOR
    assert s.window_start == ANCHOR - timedelta(seconds=PRE_SEC)
    assert s.window_end == ANCHOR + timedelta(seconds=POST_SEC)
    assert s.triggered_by == {Modality.METRIC}
    assert len(s.pre.logs) == 1  # Pre 즉시 캡처됨


def test_register_uses_earliest_trigger_as_anchor():
    buf = FakeBuffer()
    m = SnapshotManager()
    early = ANCHOR - timedelta(seconds=5)
    m.register_triggers([evidence(Modality.LOG, ANCHOR), evidence(Modality.LOG, early)], buf)
    assert m._session.anchor == early


def test_reregister_accumulates_without_changing_window():
    buf = FakeBuffer()
    m = SnapshotManager()
    m.register_triggers([evidence(Modality.METRIC, ANCHOR)], buf)
    m.register_triggers([evidence(Modality.LOG, ANCHOR + timedelta(seconds=30))], buf)
    s = m._session
    assert s.anchor == ANCHOR  # window/anchor 불변
    assert s.window_end == ANCHOR + timedelta(seconds=POST_SEC)
    assert s.triggered_by == {Modality.METRIC, Modality.LOG}
    assert len(s.evidences) == 2


def test_empty_evidences_is_noop():
    m = SnapshotManager()
    m.register_triggers([], FakeBuffer())
    assert m._session is None


def test_finalize_returns_empty_before_window_end():
    buf = FakeBuffer()
    m = SnapshotManager()
    m.register_triggers([evidence(Modality.METRIC, ANCHOR)], buf)
    assert m.finalize_ready(ANCHOR + timedelta(seconds=POST_SEC - 1), buf) == []
    assert m._session is not None  # 아직 세션 유지


def test_finalize_returns_empty_when_no_session():
    assert SnapshotManager().finalize_ready(ANCHOR, FakeBuffer()) == []


def test_finalize_assembles_bundle_and_closes_session():
    # pre 구간에 metric 1건, post 구간에 log 1건
    pre_metric = metric_at(ANCHOR - timedelta(seconds=60))
    post_log = log_at(ANCHOR + timedelta(seconds=60))
    buf = FakeBuffer(logs=[post_log], metrics=[pre_metric])
    m = SnapshotManager()
    m.register_triggers([evidence(Modality.METRIC, ANCHOR), evidence(Modality.LOG, ANCHOR)], buf)

    bundles = m.finalize_ready(ANCHOR + timedelta(seconds=POST_SEC), buf)
    assert len(bundles) == 1
    b = bundles[0]
    assert b.window.start == ANCHOR - timedelta(seconds=PRE_SEC)
    assert b.window.end == ANCHOR + timedelta(seconds=POST_SEC)
    assert b.trigger_info.trigger_time == ANCHOR
    assert b.trigger_info.triggered_by == ["log", "metric"]  # 정렬·중복제거
    assert len(b.metrics) == 1  # pre
    assert len(b.logs) == 1     # post
    assert b.metrics[0].service == "__node__"
    assert '"metric_name":"system_cpu_usage"' in b.metrics[0].raw.replace(" ", "")
    assert m._session is None  # 세션 종료


def _bundle_with_coverage(cov: dict) -> object:
    buf = FakeBuffer(coverage=cov)
    m = SnapshotManager()
    m.register_triggers([evidence(Modality.METRIC, ANCHOR)], buf)
    return m.finalize_ready(ANCHOR + timedelta(seconds=POST_SEC), buf)[0]


def test_modality_info_three_states_from_coverage():
    # 소스 상태 3종. present 와 record_count 조합이 각각을 가른다:
    #   data    = 이 창에 레코드가 있었다
    #   empty   = 파일은 있었는데 레코드가 0건이었다
    #   missing = 파일 자체가 없었다 (중앙 RCA 의 죽은 서비스 국소화 근거)
    cov = {
        "log": [
            SourceStatus(source="NginxThrift_.log", present=True, record_count=5),   # data
            SourceStatus(source="MediaService_.log", present=True, record_count=0),   # empty
            SourceStatus(source="UserService_.log", present=False, record_count=0),   # missing
        ]
    }
    info = _bundle_with_coverage(cov).modality_info["log"]
    intervals = {i.fileName: i.status for i in info.intervals}
    assert intervals == {
        "NginxThrift_.log": "data",
        "MediaService_.log": "empty",
        "UserService_.log": "missing",
    }


def test_modality_info_missing_requires_absent_source():
    # empty(파일 있음·0건)와 missing(파일 없음)이 섞이지 않는지 — 국소화 근거라 구분이 핵심
    cov = {"metric": [SourceStatus(source="system_cpu_usage.csv", present=True, record_count=0)]}
    assert _bundle_with_coverage(cov).modality_info["metric"].intervals[0].status == "empty"

    cov = {"metric": [SourceStatus(source="system_cpu_usage.csv", present=False, record_count=0)]}
    assert _bundle_with_coverage(cov).modality_info["metric"].intervals[0].status == "missing"


def test_modality_info_folds_pre_and_post_with_present_or():
    # Pre+Post 를 접을 때 present 는 OR — 창 중간에 생긴 소스는 missing 이 아니다.
    # FakeBuffer 는 pre/post 조회에 같은 coverage 를 주므로, present=False 단독이면 missing 유지.
    cov = {"trace": [SourceStatus(source="all_traces.csv", present=False, record_count=0)]}
    assert _bundle_with_coverage(cov).modality_info["trace"].intervals[0].status == "missing"

    # 같은 소스에 레코드가 있으면 present 여부와 무관하게 data (레코드가 존재의 증거)
    cov = {"trace": [SourceStatus(source="all_traces.csv", present=False, record_count=3)]}
    assert _bundle_with_coverage(cov).modality_info["trace"].intervals[0].status == "data"


def test_missing_flows_from_real_normalizer_roster_through_real_buffer():
    """계약 고정: 실제 Normalizer 의 roster(present=False) → 번들 `missing` 까지 이어지는지.

    위 테스트들은 SourceStatus 를 손으로 만들어 FakeBuffer 에 넣으므로, 정규화가 실제로
    present=False 를 내는지·버퍼 집계가 그걸 보존하는지는 검증하지 못한다. 대역을 걷어내고
    LogNormalizer → MemoryBuffer → SnapshotManager 를 그대로 잇는다.
    """
    normalized = LogNormalizer(["nginx", "media", "user"]).normalize(
        RawBatch(
            modality=Modality.LOG,
            observed_from=ANCHOR - timedelta(seconds=200),
            observed_until=ANCHOR + timedelta(seconds=200),
            # nginx 파일만 관측됨 — media/user 는 파일 자체가 없다
            records=[{"raw": NGINX_LINE, "_source": "NginxThrift_.log"}],
            sources=["NginxThrift_.log"],
        )
    )
    buf = MemoryBuffer(retention_sec=100_000)  # 축출은 buffer 테스트 소관
    buf.append(normalized)

    m = SnapshotManager()
    m.register_triggers([evidence(Modality.LOG, ANCHOR)], buf)
    bundle = m.finalize_ready(ANCHOR + timedelta(seconds=POST_SEC), buf)[0]

    statuses = {i.fileName: i.status for i in bundle.modality_info["log"].intervals}
    assert statuses == {"nginx": "data", "media": "missing", "user": "missing"}


def test_finalize_after_close_needs_new_session():
    buf = FakeBuffer()
    m = SnapshotManager()
    m.register_triggers([evidence(Modality.METRIC, ANCHOR)], buf)
    m.finalize_ready(ANCHOR + timedelta(seconds=POST_SEC), buf)
    # 세션 종료 후 finalize → []
    assert m.finalize_ready(ANCHOR + timedelta(seconds=300), buf) == []
