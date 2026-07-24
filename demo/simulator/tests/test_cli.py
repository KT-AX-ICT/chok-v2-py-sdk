from __future__ import annotations

from pathlib import Path

import pytest

from demo.simulator.cli import build_parser, ensure_empty_source_layout


def test_parser_defaults_to_infinite_sixty_second_baseline():
    args = build_parser().parse_args([])
    assert args.baseline_sec == 60.0
    assert args.cycles is None


def test_parser_accepts_finite_smoke_cycle():
    args = build_parser().parse_args(["--baseline-sec", "5", "--cycles", "1"])
    assert args.baseline_sec == 5.0
    assert args.cycles == 1


@pytest.mark.parametrize("args", [["--baseline-sec", "0"], ["--cycles", "0"]])
def test_parser_rejects_non_positive_values(args):
    with pytest.raises(SystemExit):
        build_parser().parse_args(args)


def test_source_layout_must_be_empty(tmp_path: Path):
    ensure_empty_source_layout(tmp_path)
    assert all((tmp_path / name).is_dir() for name in ("log", "metric", "trace"))

    (tmp_path / "log" / "old.log").write_text("old\n", encoding="utf-8")
    with pytest.raises(ValueError, match="빈 실행 경로"):
        ensure_empty_source_layout(tmp_path)
