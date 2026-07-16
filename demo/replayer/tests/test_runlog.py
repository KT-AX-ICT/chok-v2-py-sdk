"""Phase 3 검증 — 실행 기록이 무엇을 언제 돌렸는지 남기는가."""

from __future__ import annotations

import csv
from datetime import UTC, datetime

from demo.replayer.runlog import COMPLETED, HEADER, INTERRUPTED, RESET, RUNNING, RunLog

T0 = datetime(2026, 7, 16, 16, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 7, 16, 16, 20, 30, tzinfo=UTC)


def rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return [r for r in csv.reader(f) if r]


def test_start_writes_running_row(tmp_path):
    log = RunLog(tmp_path)
    log.start("cpu", T0)
    assert rows(log.path) == [
        list(HEADER),
        ["cpu", T0.isoformat(), "", RUNNING],
    ]


def test_started_at_is_the_t0_anchor(tmp_path):
    """기록된 started_at 으로 원본 시각 → 재생 시각 매핑을 되짚을 수 있어야 한다."""
    log = RunLog(tmp_path)
    log.start("cpu", T0)
    assert datetime.fromisoformat(rows(log.path)[1][1]) == T0


def test_finish_updates_the_row_in_place(tmp_path):
    log = RunLog(tmp_path)
    log.start("cpu", T0)
    log.finish(COMPLETED, T1)
    assert rows(log.path) == [
        list(HEADER),
        ["cpu", T0.isoformat(), T1.isoformat(), COMPLETED],
    ]


def test_finish_can_mark_interrupted(tmp_path):
    log = RunLog(tmp_path)
    log.start("cpu", T0)
    log.finish(INTERRUPTED, T1)
    assert rows(log.path)[1][3] == INTERRUPTED


def test_finish_without_start_is_noop(tmp_path):
    log = RunLog(tmp_path)
    log.finish(COMPLETED, T1)
    assert not log.path.exists()


def test_continued_runs_accumulate(tmp_path):
    """시나리오를 바꿔 이어 돌리면 행이 쌓이고, started_at 이 증가한다."""
    a, b = RunLog(tmp_path), RunLog(tmp_path)
    a.start("cpu", T0)
    a.finish(COMPLETED, T1)
    b.start("code_media", T1)
    b.finish(COMPLETED, datetime(2026, 7, 16, 16, 40, tzinfo=UTC))

    r = rows(b.path)
    assert len(r) == 3  # 헤더 + 2회
    assert [x[0] for x in r[1:]] == ["cpu", "code_media"]
    assert all(x[3] == COMPLETED for x in r[1:])
    assert r[1][1] < r[2][1]


def test_reset_row_has_empty_scenario(tmp_path):
    log = RunLog(tmp_path)
    log.reset(T0)
    assert rows(log.path)[1] == ["", T0.isoformat(), T0.isoformat(), RESET]


def test_reset_preserves_prior_history(tmp_path):
    """기록과 실제 데이터가 어긋나 보일 때 reset 행이 이유가 된다."""
    a = RunLog(tmp_path)
    a.start("cpu", T0)
    a.finish(COMPLETED, T1)

    b = RunLog(tmp_path)
    b.reset(T1)
    b.start("code_media", T1)

    r = rows(b.path)
    assert [x[0] for x in r[1:]] == ["cpu", "", "code_media"]
    assert [x[3] for x in r[1:]] == [COMPLETED, RESET, RUNNING]


def test_finish_after_reset_updates_the_right_row(tmp_path):
    """reset 행이 사이에 끼어도 갱신 대상이 밀리지 않는다."""
    log = RunLog(tmp_path)
    log.reset(T0)
    log.start("cpu", T0)
    log.finish(COMPLETED, T1)

    r = rows(log.path)
    assert r[1][3] == RESET
    assert r[2] == ["cpu", T0.isoformat(), T1.isoformat(), COMPLETED]
