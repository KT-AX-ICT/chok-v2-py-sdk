"""normal → 장애 3종을 무한 순환하는 simulator 오케스트레이터."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from demo.replayer.writer import Writer

from .catalog import Dataset
from .filters import keep_baseline_record
from .playback import CyclicPlayback, Playback

INCIDENT_ORDER = ("cpu", "kill_media", "code_media")
# 실측 첫 발화(cpu 126/139s, kill 111s, code nginx 150s·trace 270s)와
# 가장 늦은 첫 report post 끝(code 330s)을 모두 포함한다.
INCIDENT_DURATION_SEC = 330.0


class InfiniteSimulator:
    def __init__(
        self,
        *,
        source_root: Path,
        baseline: Dataset,
        incidents: dict[str, Dataset],
        baseline_sec: float = 60.0,
        cycles: int | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
        announce: Callable[[str], None] = print,
    ) -> None:
        if baseline_sec <= 0:
            raise ValueError("baseline_sec은 0보다 커야 한다")
        if cycles is not None and cycles <= 0:
            raise ValueError("cycles는 0보다 커야 한다")
        missing = [name for name in INCIDENT_ORDER if name not in incidents]
        if missing:
            raise ValueError(f"incident 데이터 누락: {missing}")

        self.source_root = source_root
        self.baseline = baseline
        self.incidents = incidents
        self.baseline_sec = baseline_sec
        self.cycles = cycles
        self.clock = clock
        self.sleep = sleep
        self.announce = announce

    def run(self) -> None:
        baseline_player = CyclicPlayback(
            self.baseline,
            clock=self.clock,
            sleep=self.sleep,
            record_filter=keep_baseline_record,
        )
        target = self.clock()
        completed_cycles = 0

        with Writer(self.source_root) as writer:
            while self.cycles is None or completed_cycles < self.cycles:
                for name in INCIDENT_ORDER:
                    target = max(target, self.clock())
                    self.announce(
                        f"[simulator] baseline {self.baseline_sec:g}초 "
                        f"(다음 장애: {name})"
                    )
                    target = baseline_player.play(
                        writer,
                        target,
                        self.baseline_sec,
                    )

                    target = max(target, self.clock())
                    self.announce(
                        f"[simulator] incident {name} {INCIDENT_DURATION_SEC:g}초"
                    )
                    incident_player = Playback(
                        self.incidents[name],
                        clock=self.clock,
                        sleep=self.sleep,
                    )
                    target = incident_player.play_window(
                        writer,
                        target,
                        INCIDENT_DURATION_SEC,
                    )
                completed_cycles += 1
