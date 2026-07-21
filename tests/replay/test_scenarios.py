"""시나리오 3종 재생 — 발화·침묵·번들 불변식 (계획 05 §4·§5).

데이터셋이 없는 클론에서는 통째로 skip 한다.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from rca_sdk.schemas.events import Modality
from rca_sdk.schemas.snapshot import SnapshotBundle
from rca_sdk.snapshot.assembler import POST_SEC, PRE_SEC
from tests.replay.report import render
from tests.replay.scenarios import ReplayResult, dataset_available, run_scenario

pytestmark = pytest.mark.skipif(not dataset_available(), reason="datasets/sn 미커밋 클론")

_CACHE: dict[str, ReplayResult] = {}


def replay(name: str) -> ReplayResult:
    """시나리오 1회 재생은 ~7초라 테스트 사이에 결과를 재사용한다."""
    if name not in _CACHE:
        _CACHE[name] = run_scenario(name)
    return _CACHE[name]


@pytest.fixture(scope="module")
def svc_kill() -> ReplayResult:
    return replay("Svc_Kill_Media")


@pytest.fixture(scope="module")
def code_stop() -> ReplayResult:
    return replay("Code_Stop_MediaService")


@pytest.fixture(scope="module")
def perf_cpu() -> ReplayResult:
    return replay("Perf_CPU_Contention")


# ── Svc_Kill_Media ──────────────────────────────────────────────────────────


def test_svc_kill_fires_restart_marker_on_media(svc_kill):
    fire = svc_kill.first_fire("restart_marker")
    assert fire is not None
    assert fire.evidence.service == "media"
    # ADR-006 이 근거로 든 2번째 부팅 시각. 1번째(00:01:57)가 아니라 threshold 번째다.
    assert fire.evidence.trigger_time == svc_kill.origin.replace(
        hour=0, minute=3, second=41, microsecond=500315
    )


def test_svc_kill_is_silent_on_cpu(svc_kill):
    """svc_kill 시 metric 은 끊김·변화 없음 — cpu_spike 가 울면 오탐이다 (ADR-006)."""
    assert "cpu_spike" not in svc_kill.fired_types()


def test_svc_kill_emits_one_bundle(svc_kill):
    """단일 세션 + since 로, 부팅이 계속 창에 남아도 번들은 1개다."""
    assert len(svc_kill.bundles) == 1
    assert svc_kill.bundles[0].trigger_info.triggered_by == ["log"]


# ── Code_Stop_MediaService ──────────────────────────────────────────────────


def test_code_stop_fires_trace_and_nginx_signals(code_stop):
    fired = code_stop.fired_types()
    assert "trace_5xx" in fired
    assert "nginx_error" in fired


def test_code_stop_is_silent_on_cpu(code_stop):
    """죽은 컨테이너가 목록에 잔존해 CPU 는 변화 없다 (ADR-006 §설계 6)."""
    assert "cpu_spike" not in code_stop.fired_types()


def test_code_stop_reports_media_as_missing_or_empty(code_stop):
    """MediaService 가 죽어 로그가 끊긴다 — 중앙 RCA 의 국소화 근거 (계약 §0-11)."""
    states = set()
    for bundle in code_stop.bundles:
        for interval in bundle.modality_info.get("log", []).intervals:
            if interval.fileName == "media":
                states.add(interval.status)
    assert states & {"missing", "empty"}, f"media 가 계속 data 로 보고됨: {states}"


def test_code_stop_reopens_sessions_after_each_bundle(code_stop):
    """조건이 지속되면 번들 전송 후 재발화해 다음 번들을 연다 (중복 허용)."""
    assert len(code_stop.bundles) >= 2


# ── Perf_CPU_Contention ─────────────────────────────────────────────────────


def test_perf_cpu_fires_cpu_spike_on_node(perf_cpu):
    fire = perf_cpu.first_fire("cpu_spike")
    assert fire is not None
    assert fire.evidence.service == "__node__"  # host 지표
    assert fire.evidence.extra["max_cpu"] > 50.0


def test_perf_cpu_is_silent_on_restart_marker(perf_cpu):
    """CPU 경합은 서비스를 죽이지 않는다 — 부팅 마커가 늘면 안 된다."""
    assert "restart_marker" not in perf_cpu.fired_types()


# ── 불변식 (계획 05 §5) ─────────────────────────────────────────────────────

ALL = ["Svc_Kill_Media", "Code_Stop_MediaService", "Perf_CPU_Contention"]


def all_bundles() -> list[tuple[str, SnapshotBundle]]:
    return [(name, b) for name in ALL for b in replay(name).bundles]


@pytest.mark.parametrize("name", ALL)
def test_window_is_anchor_plus_minus_three_minutes(name):
    for bundle in replay(name).bundles:
        anchor = bundle.trigger_info.trigger_time
        assert bundle.window.start == anchor - timedelta(seconds=PRE_SEC)
        assert bundle.window.end == anchor + timedelta(seconds=POST_SEC)


@pytest.mark.parametrize("name", ALL)
def test_records_stay_inside_window(name):
    """창 메타와 내용이 어긋나면 중앙 RCA 가 없는 구간을 있다고 읽는다."""
    for bundle in replay(name).bundles:
        for records in (bundle.logs, bundle.metrics, bundle.traces):
            for record in records:
                assert bundle.window.start <= record.timestamp < bundle.window.end


@pytest.mark.parametrize("name", ALL)
def test_records_are_time_sorted(name):
    for bundle in replay(name).bundles:
        for records in (bundle.logs, bundle.metrics, bundle.traces):
            stamps = [r.timestamp for r in records]
            assert stamps == sorted(stamps)


@pytest.mark.parametrize("name", ALL)
def test_bundles_do_not_repeat_the_same_anchor(name):
    """같은 anchor 로 번들이 두 번 나오면 세션 종료·since 배선이 깨진 것이다."""
    anchors = [b.trigger_info.trigger_time for b in replay(name).bundles]
    assert len(anchors) == len(set(anchors))


@pytest.mark.parametrize("name", ALL)
def test_bundle_anchors_advance(name):
    anchors = [b.trigger_info.trigger_time for b in replay(name).bundles]
    assert anchors == sorted(anchors)


@pytest.mark.parametrize("name", ALL)
def test_refire_anchor_does_not_reach_back_into_previous_bundle(name):
    """since 의 실데이터 확인 — 재발화 anchor 가 직전 번들 안으로 끌려가면 안 된다.

    "트리거는 번들 전송 이후의 배치부터 다시 검사한다" 는 요구를 창 기반·배치 기반
    **양쪽**이 지켜야 성립한다. 한때 이 단정이 배치 기반 detector 때문에 깨졌고,
    당시 허용 하한을 한 틱 넓혀 통과시켰다 — 잘못된 대응이었다. `NumericThresholdDetector`
    가 `since` 이전 레코드를 걸러내도록 고쳐 원래 단정으로 되돌렸다.
    """
    bundles = replay(name).bundles
    for previous, current in zip(bundles, bundles[1:], strict=False):
        assert current.trigger_info.trigger_time >= previous.window.end


@pytest.mark.parametrize("name", ALL)
def test_every_source_gets_a_three_state_verdict(name):
    for bundle in replay(name).bundles:
        for info in bundle.modality_info.values():
            for interval in info.intervals:
                assert interval.status in {"missing", "empty", "data"}


# ── 연속성 (계획 05 §6) ─────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ALL)
def test_replay_runs_to_completion_without_exception(name):
    """끊김 없이 도는가 — tick() 이 던지면 재생이 거기서 멈춰 틱 수가 모자란다."""
    result = replay(name)
    assert result.ticks >= 40


@pytest.mark.parametrize("name", ALL)
def test_batches_are_contiguous_across_the_run(name):
    """배치 N.observed_until == N+1.observed_from — 끊기면 coverage 겹침 판정이 무너진다."""
    assert replay(name).gaps == []


@pytest.mark.parametrize("name", ALL)
def test_normalization_drops_nothing(name):
    """정규화가 조용히 버리는 레코드가 없어야 한다.

    boost 로그의 func 패턴이 `operator()` 를 못 읽어 시나리오당 400줄이 사라지던 것을
    이 검증이 잡았다 (계획 05 §6).
    """
    result = replay(name)
    for modality in Modality:
        assert result.dropped(modality) == 0, f"{modality.value} {result.dropped(modality)}건 유실"


# ── 리포트 (계획 05 §6) ─────────────────────────────────────────────────────


def test_report_renders_every_scenario():
    """리포트 생성기가 깨지지 않는지 — 파일은 쓰지 않고 렌더만 확인한다."""
    text = render([replay(name) for name in ALL])
    for name in ALL:
        assert f"## {name}" in text
    assert "번들 payload" in text  # 실측 발견 절이 붙는다
