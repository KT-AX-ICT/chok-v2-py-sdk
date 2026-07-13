"""30초 관측 루프 오케스트레이터 (스캐폴드).

한 tick 흐름:
  collectors.poll → normalization → buffer.add
  → trigger.detect_all + correlation.correlate
  → dispatch 판정: incident 있으면 snapshot.assemble → transport.send, 없으면 관찰 지속
"""

from __future__ import annotations

import time

from rca_sdk.config import Settings, load_settings


class Runner:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        # TODO: collectors / buffer / detector / assembler / transport 인스턴스 구성.

    def tick(self) -> None:
        """1회 관측 사이클 (스캐폴드)."""
        # TODO: 파이프라인 한 바퀴.
        raise NotImplementedError("Runner.tick 스캐폴드")

    def run(self, once: bool = False) -> None:
        while True:
            self.tick()
            if once:
                return
            time.sleep(self.settings.loop_interval_sec)
