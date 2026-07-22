"""Phase 4 검증 — 병합/페이싱/duration. 합성 소스로 결정론적으로 돌린다 (재우지 않음)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from demo.replayer.readers import Record
from demo.replayer.scenarios import Source
from demo.replayer.scheduler import Loaded, measure_start, merged, replay
from demo.replayer.writer import Writer

BASE = datetime(2025, 11, 3, 22, 26, 39, tzinfo=UTC)
ANCHOR = datetime(2026, 7, 16, 16, 0, 0, tzinfo=UTC)


def rec(sec: int, text: str) -> Record:
    return Record(BASE + timedelta(seconds=sec), text)


def log_loaded(name: str, recs: list[Record]) -> Loaded:
    """로그 스트림 흉내 — rows 를 그대로 흘리도록 감싼다 (실제로는 파일에서 스트리밍)."""
    lo = Loaded(Source("log", name, name, "boost"), None, recs, None)
    return lo


def csv_loaded(name: str, recs: list[Record], header: str) -> Loaded:
    return Loaded(Source("metric", name, name, "csv", ts_column="timestamp"), header, recs, 0)


# --- 병합 순서 ------------------------------------------------------------------


def test_merge_interleaves_by_ts_across_streams():
    a = log_loaded("a_.log", [rec(0, "a0\n"), rec(2, "a2\n"), rec(4, "a4\n")])
    b = log_loaded("b_.log", [rec(1, "b1\n"), rec(3, "b3\n")])
    order = [r.line for r, _ in merged([a, b])]
    assert order == ["a0\n", "b1\n", "a2\n", "b3\n", "a4\n"]


def test_merge_preserves_within_stream_order_even_if_unsorted():
    """로그의 마이크로초 역전 — 스트림 안 순서는 절대 바꾸지 않는다 (0-6')."""
    a = log_loaded("a_.log", [rec(3, "a3\n"), rec(1, "a1\n"), rec(5, "a5\n")])  # 역전
    b = log_loaded("b_.log", [rec(2, "b2\n"), rec(4, "b4\n")])
    lines = [(r.line, lo.source.filename) for r, lo in merged([a, b])]
    a_order = [x[0] for x in lines if x[1] == "a_.log"]
    assert a_order == ["a3\n", "a1\n", "a5\n"]  # 파일 순서 그대로


# --- t0 측정 --------------------------------------------------------------------


def test_measure_start_is_global_min():
    a = log_loaded("a_.log", [rec(30, "a\n")])
    b = csv_loaded("m.csv", [rec(5, "m\n"), rec(50, "m\n")], "timestamp,v\n")
    assert measure_start([a, b]) == BASE + timedelta(seconds=5)


def test_measure_start_ignores_empty_sources():
    a = log_loaded("a_.log", [rec(10, "a\n")])
    empty = log_loaded("e_.log", [])
    assert measure_start([a, empty]) == BASE + timedelta(seconds=10)


# --- 재생: 페이싱 없이 (fast clock) ------------------------------------------------


def _fast_clock():
    """항상 먼 미래를 돌려줘 wait<=0 → 재우지 않는다."""
    return datetime(2099, 1, 1, tzinfo=UTC)


def test_replay_writes_all_lines_shifted(tmp_path):
    a = log_loaded("a_.log", [rec(0, "[x] a0\n"), rec(2, "[x] a2\n")])
    t0 = measure_start([a])
    slept = []
    with Writer(tmp_path) as w:
        n = replay([a], w, ANCHOR, t0, clock=_fast_clock, sleep=slept.append)
    assert n == 2
    assert not slept  # 이미 지난 시각이라 재우지 않음
    assert (tmp_path / "log" / "a_.log").read_text() == "[x] a0\n[x] a2\n"


def test_replay_sleeps_until_new_ts():
    """현재 시각이 new_ts 에 못 미치면 그 차이만큼 잔다."""
    a = log_loaded("a_.log", [rec(0, "a0\n"), rec(10, "a10\n")])
    t0 = measure_start([a])
    slept = []

    class W:
        def open(self, *a, **k): pass
        def write(self, *a): pass

    # clock 을 anchor 에 고정 → 첫 줄 wait=0, 둘째 줄 wait=10초
    replay([a], W(), ANCHOR, t0, clock=lambda: ANCHOR, sleep=slept.append)
    assert slept == [10.0]


def test_duration_stops_at_replay_deadline():
    """--duration 은 재생 시간축 기준 — new_ts 가 anchor+duration 을 넘으면 멈춘다."""
    a = log_loaded("a_.log", [rec(0, "a0\n"), rec(5, "a5\n"), rec(20, "a20\n")])
    t0 = measure_start([a])
    written = []

    class W:
        def open(self, *a, **k): pass
        def write(self, m, f, line): written.append(line)

    n = replay([a], W(), ANCHOR, t0, duration_sec=10, clock=_fast_clock, sleep=lambda s: None)
    assert n == 2  # 0s, 5s 통과 / 20s 는 deadline(10s) 초과
    assert written == ["a0\n", "a5\n"]


def test_replay_stops_at_end_no_repeat(tmp_path):
    a = log_loaded("a_.log", [rec(0, "a0\n")])
    t0 = measure_start([a])
    with Writer(tmp_path) as w:
        n = replay([a], w, ANCHOR, t0, clock=_fast_clock, sleep=lambda s: None)
    assert n == 1  # 끝에서 멈춘다. 반복하지 않는다


def test_replay_writes_csv_header_once(tmp_path):
    m = csv_loaded("cpu.csv", [rec(0, "2025-11-03 22:26:39,1\n")], "timestamp,v\n")
    t0 = measure_start([m])
    with Writer(tmp_path) as w:
        replay([m], w, ANCHOR, t0, clock=_fast_clock, sleep=lambda s: None)
    text = (tmp_path / "metric" / "cpu.csv").read_text()
    assert text.count("timestamp,v\n") == 1
    assert text.startswith("timestamp,v\n")
