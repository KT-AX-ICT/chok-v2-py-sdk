"""스케줄러 — 재생 대상을 재생 시각순으로 병합해, 현재 시각이 닿으면 방출한다 (계획 Phase 4).

파일 단위 순차 처리는 시각축을 깬다. 파일별 스트림의 **k-way merge** 로, 각 스트림 안의 순서는
그대로 두고 다음에 내보낼 스트림만 고른다.

- **CSV 는 `ts` 로 정렬**한 뒤 병합한다. 원본이 시계열 단위로 묶여 파일 순서≠시각순이다 (0-6').
- **로그는 파일 순서 그대로** 병합한다. `heapq.merge` 는 스트림이 정렬돼 있지 않아도 각 스트림을
  준 순서대로 전진시키며 head 가 가장 이른 것을 고른다 — 로그의 마이크로초 역전(멀티스레드 기록)이
  파일 순서 그대로 남는다.
"""

from __future__ import annotations

import csv
import heapq
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import NamedTuple

from .readers import Record, read_csv, read_log, read_nginx
from .scenarios import Source
from .shift import measure_t0, shift_csv_line, shift_log_line, shift_nginx_line, shift_ts
from .writer import Writer


class Loaded(NamedTuple):
    """재생 준비를 마친 소스. CSV 는 정렬돼 메모리에 있고, 로그는 다시 열 경로만 들고 있다."""

    source: Source
    header: str | None
    rows: list[Record] | None  # csv 만 — 정렬된 실체. 로그는 None (스트리밍)
    ts_index: int | None  # csv 시프트용 컬럼 인덱스


def _read(source: Source) -> Iterator[Record]:
    if source.kind == "nginx":
        return read_nginx(source.path)
    return read_log(source.path)  # boost + thrift


def load(sources: list[Source]) -> list[Loaded]:
    """CSV 는 정렬해 적재하고, 로그는 스트리밍으로 남긴다.

    CSV 정렬은 전량 적재가 불가피하지만 metric·trace 합쳐 5MB 라 무해하다. 로그(최대 27MB)는
    적재하지 않는다 (함정 5) — 아래 t0 측정과 재생에서 두 번 스트리밍한다.
    """
    out: list[Loaded] = []
    for s in sources:
        if s.kind == "csv":
            src = read_csv(s.path, s.ts_column)
            rows = sorted(src.rows, key=lambda r: r.ts)
            ts_index = None
            if src.header is not None:
                ts_index = next(csv.reader([src.header])).index(s.ts_column)
            out.append(Loaded(s, src.header, rows, ts_index))
        else:
            out.append(Loaded(s, None, None, None))
    return out


def measure_start(loaded: list[Loaded]) -> datetime:
    """t0 = 전 모달리티 통틀어 실측 min (함정 4). 폴더명 시각이 아니다.

    CSV 는 정렬돼 있어 첫 행이 min 이고, 로그는 한 번 스트리밍해 min 을 구한다.
    """
    mins: list[datetime] = []
    for lo in loaded:
        if lo.rows is not None:
            if lo.rows:
                mins.append(lo.rows[0].ts)
        else:
            m = min((r.ts for r in _read(lo.source)), default=None)
            if m is not None:
                mins.append(m)
    return measure_t0(mins)


def _shift_line(lo: Loaded, line: str, new_ts: datetime) -> str:
    if lo.source.kind == "csv":
        return shift_csv_line(line, lo.ts_index, new_ts)
    if lo.source.kind == "nginx":
        return shift_nginx_line(line, new_ts)
    return shift_log_line(line, new_ts)


def _stream(lo: Loaded) -> Iterator[tuple[Record, Loaded]]:
    rows: Iterator[Record] = iter(lo.rows) if lo.rows is not None else _read(lo.source)
    for r in rows:
        yield r, lo


def merged(loaded: list[Loaded]) -> Iterator[tuple[Record, Loaded]]:
    """전 소스를 `ts` 로 k-way 병합. 정렬 키는 `ts` 뿐 — 동시각 동률은 삽입 순서로 갈린다."""
    return heapq.merge(*(_stream(lo) for lo in loaded), key=lambda it: it[0].ts)


def replay(
    loaded: list[Loaded],
    writer: Writer,
    anchor: datetime,
    t0: datetime,
    duration_sec: float | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """병합 스트림을 현재 시각에 맞춰 방출한다. 방출한 줄 수를 돌려준다.

    `new_ts = anchor + (orig_ts - t0)`. 현재 시각이 `new_ts` 에 못 미치면 그 차이만큼 잔다.
    이미 지난 시각(마이크로초 역전 등)이면 즉시 쓴다. **데이터 끝에 도달하면 정지**한다 (반복 없음).

    `duration_sec` 는 재생 시간축 기준이다 — `new_ts` 가 `anchor + duration` 을 넘으면 멈춘다.
    페이싱이 `new_ts` 를 현재 시각에 맞추므로 이는 실측 경과 시간과 같다. `clock`/`sleep` 주입으로
    테스트는 재우지 않고 돌린다.
    """
    deadline = None if duration_sec is None else anchor.timestamp() + duration_sec
    written = 0
    for r, lo in merged(loaded):
        new_ts = shift_ts(r.ts, t0, anchor)
        if deadline is not None and new_ts.timestamp() > deadline:
            break
        wait = new_ts.timestamp() - clock().timestamp()
        if wait > 0:
            sleep(wait)
        # 헤더는 파일이 비었을 때만 (open 이 멱등, 내부에서 판단). 데이터 줄 전에 반드시 선행한다.
        writer.open(lo.source.modality, lo.source.filename, header=lo.header)
        writer.write(lo.source.modality, lo.source.filename, _shift_line(lo, r.line, new_ts))
        written += 1
    return written
