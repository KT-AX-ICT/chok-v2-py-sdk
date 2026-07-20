"""build_runner() 기본 배선 — Settings 만으로 실제 Runner 를 조립할 수 있어야 한다.

주입 가능한 생성자만 있으면 테스트는 되지만 실운용에서 아무도 못 만든다. 배선의
정답(어떤 detector 를, 어떤 condition 으로, 어떤 보존값으로)을 코드 한 곳에 고정한다.
"""

from __future__ import annotations

from rca_sdk.config import Settings
from rca_sdk.runtime.runner import build_runner
from rca_sdk.schemas.events import Modality


def test_wires_three_modalities(tmp_path):
    runner = build_runner(Settings(source_root=str(tmp_path)))
    assert {collector.modality for collector, _ in runner.sources} == {
        Modality.LOG,
        Modality.METRIC,
        Modality.TRACE,
    }


def test_buffer_uses_configured_retention(tmp_path):
    runner = build_runner(Settings(source_root=str(tmp_path), buffer_retention_sec=240))
    assert runner.buffer.retention_sec == 240


def test_normalizers_get_expected_services(tmp_path):
    settings = Settings(source_root=str(tmp_path), expected_services=["media", "nginx"])
    runner = build_runner(settings)
    for _, normalizer in runner.sources:
        assert normalizer.expected_services == ["media", "nginx"]


def test_detectors_get_conditions_from_settings(tmp_path):
    runner = build_runner(Settings(source_root=str(tmp_path)))
    by_type = {d.DETECTOR_TYPE: d for d in runner.detectors}
    # ADR-006 확정치가 실제로 주입되는가 (임계를 코드에 박지 않는다 — 계약 §0-5)
    assert by_type["cpu_spike"].condition["min_over"] == 5
    assert by_type["restart_marker"].condition["threshold"] == 2


def test_every_configured_condition_reaches_a_detector(tmp_path):
    """Settings 에 조건만 적어두고 detector 를 안 다는 실수를 막는다."""
    settings = Settings(source_root=str(tmp_path))
    runner = build_runner(settings)
    wired = {d.DETECTOR_TYPE for d in runner.detectors}
    assert set(settings.trigger_conditions) <= wired


def test_transport_targets_configured_endpoint(tmp_path):
    settings = Settings(source_root=str(tmp_path), collect_endpoint="http://x/ingest")
    assert build_runner(settings).transport.endpoint == "http://x/ingest"


def test_tick_on_empty_source_root_is_quiet(tmp_path):
    """파일이 하나도 없어도 예외 없이 한 바퀴 돈다 (수집 시작 전 상태)."""
    for modality in ("log", "metric", "trace"):
        (tmp_path / modality).mkdir()
    runner = build_runner(Settings(source_root=str(tmp_path)))
    assert runner.tick() == []
