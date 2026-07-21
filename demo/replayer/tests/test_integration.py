"""Phase 5 통합 검증 — 재생 산출물이 원본에 충실한가 (계획 0-5).

CLI 는 실시간 페이싱이라 trace(t0+126s 이후)까지 보려면 오래 걸린다. 여기서는 `replay()` 를
fast clock 으로 끝까지 돌려, 세 모달리티 전부에 대해 누락 없음·내용 보존·간격 보존을 확인한다.

검증의 축은 **"기대 출력 = 원본 줄을 시프트한 것"**이다. 원본 레코드마다 기대 출력 줄을 만들어
실제 출력과 대조하면, 누락 없음(줄 수·집합)과 내용 보존(바이트)이 한 번에 걸린다.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from demo.replayer.readers import read_csv, read_log, read_nginx
from demo.replayer.scenarios import SCENARIOS, discover
from demo.replayer.scheduler import load, measure_start, replay
from demo.replayer.shift import (
    csv_field_span,
    shift_csv_line,
    shift_log_line,
    shift_nginx_line,
    shift_ts,
)
from demo.replayer.writer import Writer

DATASET = Path("datasets/sn")
ANCHOR = datetime(2026, 7, 16, 16, 0, 0, tzinfo=UTC)


def _fast_clock() -> datetime:
    """먼 미래 → wait<=0 → 재우지 않는다. 페이싱을 건너뛰고 병합·산출만 검증한다."""
    return datetime(2099, 1, 1, tzinfo=UTC)


def _source_records(source):
    if source.kind == "nginx":
        return list(read_nginx(source.path))
    if source.kind == "csv":
        return list(read_csv(source.path, source.ts_column).rows)
    return list(read_log(source.path))


def _shift_line(source, line, new_ts):
    if source.kind == "csv":
        idx = 5 if source.ts_column == "start_time" else 0
        return shift_csv_line(line, idx, new_ts)
    if source.kind == "nginx":
        return shift_nginx_line(line, new_ts)
    return shift_log_line(line, new_ts)


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_replay_is_faithful_to_source(scenario, tmp_path):
    sources = discover(DATASET, scenario)
    if not sources:
        pytest.skip(f"{scenario} 데이터셋 없음 (MVP 3종만 커밋됨)")

    loaded = load(sources)
    t0 = measure_start(loaded)
    with Writer(tmp_path) as w:
        written = replay(loaded, w, ANCHOR, t0, clock=_fast_clock, sleep=lambda s: None)

    total_source = 0
    for s in sources:
        src_recs = _source_records(s)
        total_source += len(src_recs)

        out_path = tmp_path / s.modality / s.filename
        if not src_recs:
            # 0바이트 소스(cpu/kill_media 의 NginxThrift_.log)는 방출할 줄이 없어 출력 파일도 없다.
            # 원본 0줄 == 출력 0줄이라 충실하다.
            assert not out_path.exists()
            continue

        out_lines = out_path.read_text(
            encoding="utf-8", errors="surrogateescape"
        ).splitlines(keepends=True)

        header = None
        if s.kind == "csv":
            header = read_csv(s.path, s.ts_column).header
            assert out_lines[0] == header  # 헤더가 맨 앞에 정확히 한 줄
            out_lines = out_lines[1:]

        # 누락 없음 — 줄 수 일치
        assert len(out_lines) == len(src_recs), f"{s.filename}: {len(out_lines)} != {len(src_recs)}"

        # 기대 출력 = 원본을 시프트한 것. 멀티셋으로 대조 → 누락 없음 + 내용 보존.
        expected = Counter(
            _shift_line(s, r.line, shift_ts(r.ts, t0, ANCHOR)) for r in src_recs
        )
        assert Counter(out_lines) == expected, f"{s.filename}: 내용/누락 불일치"

        if s.kind == "csv":
            _assert_ascending(out_lines, s)  # CSV 는 정렬돼 나간다 (0-6')
        else:
            _assert_log_order_and_gaps(src_recs, out_lines, s, t0)  # 로그는 파일 순서·간격 보존

    assert written == total_source


def _assert_ascending(out_lines, source):
    """출력 타임스탬프가 비내림차순 — CSV 는 new_ts 로 정렬해 방출한다."""
    idx = 5 if source.ts_column == "start_time" else 0
    prev = None
    for line in out_lines:
        s, e = csv_field_span(line, idx)
        cur = line[s:e]
        if prev is not None:
            assert cur >= prev, f"정렬 위반: {prev!r} > {cur!r}"  # 고정폭 포맷 → 문자열 비교 OK
        prev = cur


def _assert_log_order_and_gaps(src_recs, out_lines, source, t0):
    """로그는 파일 순서 그대로. 위치별로 기대 출력과 같고, 인접 간격이 원본과 같다."""
    prev_new = prev_src = None
    for rec, out in zip(src_recs, out_lines, strict=True):
        new_ts = shift_ts(rec.ts, t0, ANCHOR)
        assert out == _shift_line(source, rec.line, new_ts)
        if prev_new is not None:
            assert (new_ts - prev_new) == (rec.ts - prev_src)  # 간격 보존
        prev_new, prev_src = new_ts, rec.ts
