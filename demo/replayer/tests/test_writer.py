"""Phase 3 검증 — 라이터가 줄을 그대로 쌓는가, `--reset` 이 대상 밖을 건드리지 않는가."""

from __future__ import annotations

import pytest

from demo.replayer.writer import MODALITIES, Writer, reset

HDR = "timestamp,value\n"


def test_creates_modality_dir_and_file(tmp_path):
    with Writer(tmp_path) as w:
        w.open("log", "MediaService_.log")
        w.write("log", "MediaService_.log", "hello\n")
    assert (tmp_path / "log" / "MediaService_.log").read_text() == "hello\n"


def test_header_written_when_file_is_new(tmp_path):
    with Writer(tmp_path) as w:
        w.open("metric", "cpu.csv", header=HDR)
        w.write("metric", "cpu.csv", "2026-07-16 16:00:00,1\n")
    assert (tmp_path / "metric" / "cpu.csv").read_text() == HDR + "2026-07-16 16:00:00,1\n"


def test_header_written_when_file_exists_but_empty(tmp_path):
    p = tmp_path / "metric" / "cpu.csv"
    p.parent.mkdir(parents=True)
    p.touch()
    with Writer(tmp_path) as w:
        w.open("metric", "cpu.csv", header=HDR)
    assert p.read_text() == HDR


def test_header_not_rewritten_when_continuing(tmp_path):
    """시나리오를 바꿔 이어 돌려도 헤더는 하나뿐이다 — 3종은 CSV 파일명도 헤더도 같다."""
    for _ in range(3):
        with Writer(tmp_path) as w:
            w.open("metric", "cpu.csv", header=HDR)
            w.write("metric", "cpu.csv", "2026-07-16 16:00:00,1\n")
    text = (tmp_path / "metric" / "cpu.csv").read_text()
    assert text.count(HDR) == 1
    assert text.startswith(HDR)
    assert len(text.splitlines()) == 4  # 헤더 1 + 행 3


def test_continuing_appends_rather_than_truncates(tmp_path):
    """리셋 없이 두 번 돌리면 줄이 2배 — append 확인 (계획 Phase 3)."""
    for _ in range(2):
        with Writer(tmp_path) as w:
            w.open("log", "a_.log")
            w.write("log", "a_.log", "line\n")
    assert (tmp_path / "log" / "a_.log").read_text() == "line\nline\n"


def test_bytes_preserved_exactly(tmp_path):
    """개행 변환도 인코딩 손실도 없어야 한다 — 리더가 준 줄이 그대로 나간다."""
    raw = b"[2025-Nov-03 22:28:07.123456] <info>: caf\xe9 \r\n2nd\n"
    line = raw.decode("utf-8", errors="surrogateescape")
    with Writer(tmp_path) as w:
        w.open("log", "x_.log")
        w.write("log", "x_.log", line)
    assert (tmp_path / "log" / "x_.log").read_bytes() == raw


def test_line_is_visible_before_close(tmp_path):
    """버퍼에 쌓아두면 tailer 가 실시간으로 못 본다 — 줄 단위 버퍼링 확인."""
    w = Writer(tmp_path)
    try:
        w.open("log", "a_.log")
        w.write("log", "a_.log", "now\n")
        assert (tmp_path / "log" / "a_.log").read_text() == "now\n"
    finally:
        w.close()


def test_unknown_modality_rejected(tmp_path):
    with Writer(tmp_path) as w, pytest.raises(ValueError, match="모달리티"):
        w.open("coverage", "x.csv")


def test_open_is_idempotent(tmp_path):
    with Writer(tmp_path) as w:
        a = w.open("log", "a_.log")
        b = w.open("log", "a_.log")
        assert a is b


# --- reset ---------------------------------------------------------------------


def test_reset_clears_modality_dir_contents(tmp_path):
    """내용은 지워지되, 디렉터리 자체는 즉시 재생성된다 (validate_source_layout 과의 호환).

    SDK 의 `build_runner()` 는 기동 시 1회 log/metric/trace 디렉터리 존재를 확인한다
    (계획 06 §3). 리셋 직후 디렉터리를 통째로 없애버리면, 리플레이어가 아직 데이터를
    안 쓴 모달리티(trace 는 t0+126초까지 지연)만큼 그 사이 rca-collect 가 기동 실패한다.
    """
    with Writer(tmp_path) as w:
        for m in MODALITIES:
            w.open(m, "f.txt")
            w.write(m, "f.txt", "x\n")
    reset(tmp_path)
    for m in MODALITIES:
        d = tmp_path / m
        assert d.is_dir()
        assert list(d.iterdir()) == []


def test_reset_keeps_run_history_and_other_entries(tmp_path):
    """`.replay/` 는 대상이 아니다 — 이력이 남는다 (`ADR-004`)."""
    (tmp_path / ".replay").mkdir()
    (tmp_path / ".replay" / "runs.csv").write_text("keep me")
    (tmp_path / "unrelated.txt").write_text("keep me too")
    (tmp_path / "log").mkdir()
    (tmp_path / "log" / "a_.log").write_text("bye")

    reset(tmp_path)

    assert (tmp_path / ".replay" / "runs.csv").read_text() == "keep me"
    assert (tmp_path / "unrelated.txt").read_text() == "keep me too"
    assert list((tmp_path / "log").iterdir()) == []


def test_reset_never_removes_source_root(tmp_path):
    root = tmp_path / "var"
    (root / "log").mkdir(parents=True)
    reset(root)
    assert root.is_dir()


def test_reset_on_first_run_creates_empty_dirs(tmp_path):
    """`var/` 가 한 번도 안 만들어진 첫 실행이라도 리셋 직후 3개 디렉터리가 생긴다.

    `--reset` 만으로도 `validate_source_layout()` 를 즉시 만족시켜, 아직 아무 모달리티도
    데이터를 안 쓴 상태에서 rca-collect 가 먼저 떠도 크래시하지 않게 한다.
    """
    reset(tmp_path)  # 예외 없음 — 처음 실행에 --reset 을 줘도 정상이다
    assert tmp_path.is_dir()
    for m in MODALITIES:
        assert (tmp_path / m).is_dir()


def test_reset_then_write_starts_clean(tmp_path):
    """--reset 두 번 실행 후 줄 수가 1회 실행과 같다 (계획 Phase 3)."""
    for _ in range(2):
        reset(tmp_path)
        with Writer(tmp_path) as w:
            w.open("metric", "cpu.csv", header=HDR)
            w.write("metric", "cpu.csv", "2026-07-16 16:00:00,1\n")
    assert (tmp_path / "metric" / "cpu.csv").read_text() == HDR + "2026-07-16 16:00:00,1\n"
