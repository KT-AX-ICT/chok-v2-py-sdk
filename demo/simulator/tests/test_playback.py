from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from demo.replayer.scenarios import Source
from demo.replayer.scheduler import load
from demo.replayer.writer import Writer
from demo.simulator.catalog import Dataset
from demo.simulator.filters import keep_baseline_record
from demo.simulator.playback import CyclicPlayback, Playback

T0 = datetime(2025, 1, 1, tzinfo=UTC)
NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def metric_dataset(tmp_path: Path) -> Dataset:
    path = tmp_path / "system_cpu_usage.csv"
    path.write_text(
        "timestamp,value,metric,instance\n"
        "2025-01-01 00:00:00,10,cpu,node:9100\n"
        "2025-01-01 00:00:05,11,cpu,node:9100\n",
        encoding="utf-8",
    )
    loaded = load([Source("metric", path.name, path, "csv", ts_column="timestamp")])
    return Dataset("tiny", "Tiny", loaded, T0, T0 + timedelta(seconds=10))


def output_lines(root: Path) -> list[str]:
    return (root / "metric" / "system_cpu_usage.csv").read_text(encoding="utf-8").splitlines()


def test_playback_keeps_header_once_across_windows(tmp_path: Path):
    output = tmp_path / "out"
    clock = FakeClock()
    player = Playback(metric_dataset(tmp_path), clock=clock, sleep=clock.sleep)

    with Writer(output) as writer:
        end = player.play_window(writer, NOW, 5)
        player.play_window(writer, end, 5)

    lines = output_lines(output)
    assert lines.count("timestamp,value,metric,instance") == 1
    assert lines[1].startswith("2026-07-24 12:00:00")
    assert lines[2].startswith("2026-07-24 12:00:05")
    assert clock.now == NOW + timedelta(seconds=10)


def test_cyclic_playback_wraps_only_after_dataset_end(tmp_path: Path):
    output = tmp_path / "out"
    clock = FakeClock()
    player = CyclicPlayback(metric_dataset(tmp_path), clock=clock, sleep=clock.sleep)

    with Writer(output) as writer:
        player.play(writer, NOW, 15)

    lines = output_lines(output)
    assert len(lines) == 4
    assert lines[1].startswith("2026-07-24 12:00:00")
    assert lines[2].startswith("2026-07-24 12:00:05")
    assert lines[3].startswith("2026-07-24 12:00:10")
    assert clock.now == NOW + timedelta(seconds=15)


def test_baseline_filter_skips_cold_start_without_changing_other_lines(tmp_path: Path):
    path = tmp_path / "MediaService_.log"
    path.write_text(
        "[2025-Jan-01 00:00:00.000001] <info>: "
        "(MediaService.cpp:44:main) Starting the media-service server...\n"
        "[2025-Jan-01 00:00:01.000001] <info>: "
        "(MediaService.cpp:50:main) Serving requests\n",
        encoding="utf-8",
    )
    loaded = load([Source("log", path.name, path, "boost")])
    dataset = Dataset("normal", "Normal", loaded, T0, T0 + timedelta(seconds=2))
    output = tmp_path / "out"
    clock = FakeClock()

    with Writer(output) as writer:
        Playback(
            dataset,
            clock=clock,
            sleep=clock.sleep,
            record_filter=keep_baseline_record,
        ).play_window(writer, NOW, 2)

    lines = (output / "log" / path.name).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "Serving requests" in lines[0]
    assert "Starting" not in lines[0]
