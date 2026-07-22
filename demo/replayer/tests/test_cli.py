"""Phase 4 검증 — CLI 파싱과 경로 검증."""

from __future__ import annotations

import pytest

from demo.replayer.cli import build_parser, main


def test_parser_lists_three_scenarios(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--help"])
    out = capsys.readouterr().out
    assert "cpu" in out and "kill_media" in out and "code_media" in out
    assert "--duration" in out


def test_parser_rejects_unknown_scenario(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["nonsense"])


def test_parser_defaults():
    args = build_parser().parse_args(["cpu"])
    assert args.scenario == "cpu"
    assert args.duration is None
    assert args.reset is False


def test_missing_dataset_fails_with_path_and_cwd(tmp_path, monkeypatch, capsys):
    """엉뚱한 CWD 에서 실행하면 해석된 절대경로와 CWD 를 함께 알리고 실패한다 (ADR-004)."""
    monkeypatch.chdir(tmp_path)  # datasets/sn 이 없는 곳
    monkeypatch.delenv("RCA_DATASET_ROOT", raising=False)
    monkeypatch.delenv("RCA_SOURCE_ROOT", raising=False)

    rc = main(["cpu"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "dataset_root" in out
    assert "CWD" in out or "작업 디렉터리" in out
    assert str(tmp_path) in out
