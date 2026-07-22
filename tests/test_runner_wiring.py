"""build_runner() 기본 배선 — Settings 만으로 실제 Runner 를 조립할 수 있어야 한다.

주입 가능한 생성자만 있으면 테스트는 되지만 실운용에서 아무도 못 만든다. 배선의
정답(어떤 detector 를, 어떤 condition 으로, 어떤 보존값으로)을 코드 한 곳에 고정한다.
"""

from __future__ import annotations

import pytest

from rca_sdk.collectors.tail import SourceLayoutError
from rca_sdk.config import Settings
from rca_sdk.runtime.runner import build_runner
from rca_sdk.schemas.events import Modality


@pytest.fixture
def source_root(tmp_path):
    """유효한 var/ 레이아웃(log/metric/trace 하위 디렉터리)을 만든다."""
    for modality in ("log", "metric", "trace"):
        (tmp_path / modality).mkdir()
    return tmp_path


def test_raises_on_missing_source_layout(tmp_path):
    """source_root 하위 log/metric/trace 가 없으면 기동 시 즉시 실패한다 (계획 06 §3).

    Collector.poll() 은 없는 경로도 예외 없이 0 건을 내므로, 여기서 막지 않으면
    "경로가 틀림"과 "이상 없음"이 로그만 봐서는 구분되지 않는다.
    """
    with pytest.raises(SourceLayoutError):
        build_runner(Settings(source_root=str(tmp_path)))


def test_wires_three_modalities(source_root):
    runner = build_runner(Settings(source_root=str(source_root)))
    assert {collector.modality for collector, _ in runner.sources} == {
        Modality.LOG,
        Modality.METRIC,
        Modality.TRACE,
    }


def test_buffer_uses_configured_retention(source_root):
    runner = build_runner(Settings(source_root=str(source_root), buffer_retention_sec=240))
    assert runner.buffer.retention_sec == 240


def test_normalizers_get_expected_services(source_root):
    settings = Settings(source_root=str(source_root), expected_services=["media", "nginx"])
    runner = build_runner(settings)
    for _, normalizer in runner.sources:
        assert normalizer.expected_services == ["media", "nginx"]


def test_detectors_get_conditions_from_settings(source_root):
    runner = build_runner(Settings(source_root=str(source_root)))
    by_type = {d.DETECTOR_TYPE: d for d in runner.detectors}
    # ADR-006 확정치가 실제로 주입되는가 (임계를 코드에 박지 않는다 — 계약 §0-5)
    assert by_type["cpu_spike"].condition["min_over"] == 5
    assert by_type["restart_marker"].condition["threshold"] == 2


def test_every_configured_condition_reaches_a_detector(source_root):
    """Settings 에 조건만 적어두고 detector 를 안 다는 실수를 막는다."""
    settings = Settings(source_root=str(source_root))
    runner = build_runner(settings)
    wired = {d.DETECTOR_TYPE for d in runner.detectors}
    assert set(settings.trigger_conditions) <= wired


def test_transport_targets_configured_endpoint(source_root):
    settings = Settings(source_root=str(source_root), collect_endpoint="http://x/ingest")
    assert build_runner(settings).transport.endpoint == "http://x/ingest"


def test_tick_on_empty_source_root_is_quiet(source_root):
    """파일이 하나도 없어도 예외 없이 한 바퀴 돈다 (수집 시작 전 상태)."""
    runner = build_runner(Settings(source_root=str(source_root)))
    assert runner.tick() == []
