"""원본 시간축의 일부를 현재 시각으로 옮겨 append하는 재생 cursor."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

from demo.replayer.readers import Record
from demo.replayer.scheduler import Loaded, merged, shift_line
from demo.replayer.shift import shift_ts
from demo.replayer.writer import Writer

from .catalog import Dataset

MergedItem = tuple[Record, Loaded]
RecordFilter = Callable[[Record, Loaded], bool]


def _include_all(record: Record, loaded: Loaded) -> bool:
    return True


class Playback:
    """Dataset의 병합 stream을 pause/resume할 수 있는 단방향 cursor."""

    def __init__(
        self,
        dataset: Dataset,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
        record_filter: RecordFilter = _include_all,
    ) -> None:
        self.dataset = dataset
        self.clock = clock
        self.sleep = sleep
        self.record_filter = record_filter
        self._cursor = dataset.t0
        self._stream: Iterator[MergedItem] = iter(merged(dataset.loaded))
        self._pending: MergedItem | None = None

    @property
    def cursor(self):
        return self._cursor

    def reset(self) -> None:
        self._cursor = self.dataset.t0
        self._stream = iter(merged(self.dataset.loaded))
        self._pending = None

    def _next(self) -> MergedItem | None:
        if self._pending is not None:
            item, self._pending = self._pending, None
            return item
        return next(self._stream, None)

    def play_window(self, writer: Writer, target_start: datetime, duration_sec: float) -> datetime:
        """현재 source cursor부터 duration만큼 재생하고 source/target cursor를 전진한다."""
        if duration_sec <= 0:
            raise ValueError("duration_sec은 0보다 커야 한다")

        source_start = self._cursor
        source_end = source_start + timedelta(seconds=duration_sec)
        target_end = target_start + timedelta(seconds=duration_sec)

        while (entry := self._next()) is not None:
            record, loaded = entry
            if record.ts < source_start:
                continue
            if record.ts >= source_end:
                self._pending = entry
                break
            if not self.record_filter(record, loaded):
                continue

            new_ts = shift_ts(record.ts, source_start, target_start)
            wait = new_ts.timestamp() - self.clock().timestamp()
            if wait > 0:
                self.sleep(wait)
            filename = self.dataset.output_filename(loaded)
            writer.open(loaded.source.modality, filename, header=loaded.header)
            writer.write(
                loaded.source.modality,
                filename,
                shift_line(loaded, record.line, new_ts),
            )

        # 레코드가 드문 구간도 source 시간축만큼 실제로 흘러야 collector watermark가 진행한다.
        wait = target_end.timestamp() - self.clock().timestamp()
        if wait > 0:
            self.sleep(wait)
        self._cursor = source_end
        return target_end


class CyclicPlayback:
    """baseline 전체 시간축을 연속 소비하고 끝에서만 처음으로 돌아간다."""

    def __init__(
        self,
        dataset: Dataset,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
        record_filter: RecordFilter = _include_all,
    ) -> None:
        if dataset.end is None:
            raise ValueError("CyclicPlayback에는 dataset.end가 필요하다")
        self.dataset = dataset
        self.clock = clock
        self.sleep = sleep
        self._playback = Playback(
            dataset,
            clock=clock,
            sleep=sleep,
            record_filter=record_filter,
        )

    def play(self, writer: Writer, target_start: datetime, duration_sec: float) -> datetime:
        if duration_sec <= 0:
            raise ValueError("duration_sec은 0보다 커야 한다")

        remaining = duration_sec
        target = target_start
        while remaining > 0:
            available = (self.dataset.end - self._playback.cursor).total_seconds()
            if available <= 0:
                self._playback.reset()
                continue
            chunk = min(remaining, available)
            target = self._playback.play_window(writer, target, chunk)
            remaining -= chunk
            if self._playback.cursor >= self.dataset.end:
                self._playback.reset()
        return target
