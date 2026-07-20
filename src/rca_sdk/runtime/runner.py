"""30초 관측 루프 오케스트레이터 (스캐폴드).

한 tick 흐름:
  collectors.poll → normalization.normalize → buffer.append
  → snapshot_manager.finalize_ready → detector.evaluate → register_triggers
  → 완성 번들 있으면 transport.send, 없으면 관찰 지속

`finalize_ready` 를 `evaluate` **앞에** 두는 이유: 이 틱에 번들이 완성되면 그 창 끝이 곧
이번 평가의 하한(`_detect_since`)이 된다. 순서가 뒤집히면 방금 전송한 구간으로 즉시
재발화한다 (계획 04 §7-3).
"""

from __future__ import annotations

import time
from datetime import datetime

from rca_sdk.config import Settings, load_settings


class Runner:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        # 마지막으로 완성된 번들의 창 끝 = detector 평가 하한 (계획 04 §7-3).
        # 번들 이력을 아는 것은 조립자인 Runner 뿐 — detector 는 시각 하나만 받아 무상태를
        # 유지하고(ADR-006), SnapshotManager 는 세션 1건의 생애만 안다.
        # post 대기 중(세션 열림)에는 register_triggers 가 재트리거를 기존 세션에 흡수하므로
        # 이 값이 필요 없다. 세션이 닫히는 순간 갱신되고, 그때부터 의미가 생긴다.
        self._detect_since: datetime | None = None
        # TODO: collectors / buffer / detector / assembler / transport 인스턴스 구성.
        # tick() 배선 시:
        #   bundles = self._snapshot.finalize_ready(observed_until, self._buffer)
        #   if bundles:
        #       self._detect_since = bundles[-1].window.end
        #   ev = detector.evaluate(batch, self._buffer, since=self._detect_since)
        #   self._snapshot.register_triggers(ev, self._buffer)

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
