from __future__ import annotations

from pathlib import Path

from demo.simulator.catalog import INCIDENT_PREFIXES, load_all

DATASET_ROOT = Path(__file__).resolve().parents[3] / "datasets" / "sn"


def test_sdk_clone_contains_baseline_and_incident_catalog():
    baseline, incidents = load_all(DATASET_ROOT)
    assert baseline.prefix == "Normal_Baseline"
    assert baseline.end is not None
    assert set(incidents) == set(INCIDENT_PREFIXES)
    assert all(dataset.loaded for dataset in [baseline, *incidents.values()])
    assert incidents["kill_media"].output_names == {
        ("metric", "socialnet_container_memory.csv"):
        "socialnet_container_memory__kill_media.csv"
    }
    assert not baseline.output_names
    assert not incidents["cpu"].output_names
    assert not incidents["code_media"].output_names


def test_normal_baseline_files_are_tracked_in_existing_layout():
    expected = {
        "log": "Normal_Baseline_20251103_220228_logs_2025-11-03_22-22-55",
        "metric": "Normal_Baseline_20251103_220228_metrics_2025-11-03_22-22-55",
        "trace": "Normal_Baseline_20251103_220228_traces_2025-11-03_22-22-55",
    }
    for modality, directory in expected.items():
        assert (DATASET_ROOT / f"{modality}_data" / directory).is_dir()
