"""Phase 4 검증 — 시나리오 탐색."""

from __future__ import annotations

from pathlib import Path

import pytest

from demo.replayer.scenarios import SCENARIOS, discover

DATASET = Path("datasets/sn")


def _skip_if_absent(scenario: str):
    if not discover(DATASET, scenario):
        pytest.skip(f"{scenario} 데이터셋 없음 (MVP 3종만 커밋됨)")


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_discovers_three_modalities(scenario):
    _skip_if_absent(scenario)
    mods = {s.modality for s in discover(DATASET, scenario)}
    assert mods == {"log", "metric", "trace"}


def test_cpu_has_twelve_logs_fifteen_metrics_one_trace():
    _skip_if_absent("cpu")
    src = discover(DATASET, "cpu")
    assert sum(s.modality == "log" for s in src) == 12
    assert sum(s.modality == "metric" for s in src) == 15
    assert sum(s.modality == "trace" for s in src) == 1


def test_code_media_missing_media_service_log():
    """서비스가 죽은 시나리오라 MediaService_.log 가 없다 — 탐색은 있는 것만 담는다."""
    _skip_if_absent("code_media")
    src = discover(DATASET, "code_media")
    names = {s.filename for s in src if s.modality == "log"}
    assert "MediaService_.log" not in names
    assert sum(s.modality == "log" for s in src) == 11


def test_nginx_detected_by_name():
    _skip_if_absent("cpu")
    nginx = [s for s in discover(DATASET, "cpu") if s.kind == "nginx"]
    assert [s.filename for s in nginx] == ["NginxThrift_.log"]


def test_boost_logs_are_kind_boost():
    _skip_if_absent("cpu")
    media = [s for s in discover(DATASET, "cpu") if s.filename == "MediaService_.log"]
    assert media and media[0].kind == "boost"


def test_csv_sources_carry_ts_column():
    _skip_if_absent("cpu")
    src = discover(DATASET, "cpu")
    metric = next(s for s in src if s.modality == "metric")
    trace = next(s for s in src if s.modality == "trace")
    assert metric.ts_column == "timestamp"
    assert trace.ts_column == "start_time"


def test_filename_is_output_basename():
    _skip_if_absent("cpu")
    for s in discover(DATASET, "cpu"):
        assert s.filename == s.path.name


def test_missing_dataset_returns_empty(tmp_path):
    assert discover(tmp_path, "cpu") == []
