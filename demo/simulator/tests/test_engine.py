from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from demo.replayer.scenarios import Source
from demo.replayer.scheduler import load
from demo.simulator.catalog import Dataset
from demo.simulator.engine import INCIDENT_DURATION_SEC, InfiniteSimulator

T0 = datetime(2025, 1, 1, tzinfo=UTC)
NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def dataset(tmp_path: Path, name: str, *, cyclic: bool = False) -> Dataset:
    path = tmp_path / name / "system_cpu_usage.csv"
    path.parent.mkdir()
    path.write_text(
        "timestamp,value,metric,instance\n"
        "2025-01-01 00:00:00,10,cpu,node:9100\n",
        encoding="utf-8",
    )
    loaded = load([Source("metric", path.name, path, "csv", ts_column="timestamp")])
    end = T0 + timedelta(seconds=600) if cyclic else None
    return Dataset(name, name, loaded, T0, end)


def test_one_cycle_runs_normal_before_each_incident_in_fixed_order(tmp_path: Path):
    clock = FakeClock()
    messages: list[str] = []
    simulator = InfiniteSimulator(
        source_root=tmp_path / "out",
        baseline=dataset(tmp_path, "normal", cyclic=True),
        incidents={
            name: dataset(tmp_path, name)
            for name in ("cpu", "kill_media", "code_media")
        },
        baseline_sec=2,
        cycles=1,
        clock=clock,
        sleep=clock.sleep,
        announce=messages.append,
    )

    simulator.run()

    assert messages == [
        "[simulator] baseline 2초 (다음 장애: cpu)",
        f"[simulator] incident cpu {INCIDENT_DURATION_SEC:g}초",
        "[simulator] baseline 2초 (다음 장애: kill_media)",
        f"[simulator] incident kill_media {INCIDENT_DURATION_SEC:g}초",
        "[simulator] baseline 2초 (다음 장애: code_media)",
        f"[simulator] incident code_media {INCIDENT_DURATION_SEC:g}초",
    ]
    assert clock.now == NOW + timedelta(seconds=3 * (2 + INCIDENT_DURATION_SEC))
