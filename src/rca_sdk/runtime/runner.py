"""30초 관측 루프 오케스트레이터 (계획 05 §2).

한 tick 흐름:
  collectors.poll → normalization.normalize → buffer.append
  → snapshot.finalize_ready → detector.evaluate → snapshot.register_triggers
  → 완성 번들 있으면 transport.send, 없으면 관찰 지속

**순서 자체가 계약이다.**

- `append` 가 먼저 — 창 기반 detector(`cpu_spike`·`restart_marker`)가 버퍼를 되돌아본다.
- `finalize_ready` 가 `evaluate` 앞 — 이 틱에 완성된 번들의 창 끝이 곧 이번 평가의
  하한(`since`)이다. 뒤집으면 방금 전송한 구간으로 즉시 재발화한다 (계획 04 §7-3).
- `send` 가 마지막 — 전송이 실패해도 `_detect_since` 는 이미 전진해 있다. 같은 번들을
  무한 재시도하지 않는다.

Runner 는 조립자다. 번들 이력을 아는 유일한 계층이며(`_detect_since`), detector 는
시각 하나만 받아 무상태를 유지하고(ADR-006) SnapshotManager 는 세션 1건의 생애만 안다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from datetime import datetime

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.collectors.base import Collector
from rca_sdk.collectors.log import LogCollector
from rca_sdk.collectors.metric import MetricCollector
from rca_sdk.collectors.tail import validate_source_layout
from rca_sdk.collectors.trace import TraceCollector
from rca_sdk.config import Settings, load_settings
from rca_sdk.normalization.base import Normalizer
from rca_sdk.normalization.log import LogNormalizer
from rca_sdk.normalization.metric import MetricNormalizer
from rca_sdk.normalization.trace import TraceNormalizer
from rca_sdk.schemas.snapshot import SnapshotBundle
from rca_sdk.snapshot.assembler import SnapshotManager
from rca_sdk.transport.client import Transport, TransportClient
from rca_sdk.trigger.code_stop.log import NginxErrorDetector
from rca_sdk.trigger.code_stop.trace import TraceFivexxDetector
from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence
from rca_sdk.trigger.perf.log import ErrorRateDetector
from rca_sdk.trigger.perf.metric import CpuSpikeDetector
from rca_sdk.trigger.perf.trace import LatencySpikeDetector
from rca_sdk.trigger.svc_kill.log import RestartMarkerDetector

logger = logging.getLogger(__name__)


class Runner:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        sources: Sequence[tuple[Collector, Normalizer]],
        buffer: MemoryBuffer,
        detectors: Sequence[TriggerDetector],
        snapshot: SnapshotManager,
        transport: Transport,
    ) -> None:
        self.settings = settings or load_settings()
        self.sources = list(sources)
        self.buffer = buffer
        self.detectors = list(detectors)
        self.snapshot = snapshot
        self.transport = transport
        # 마지막으로 완성된 번들의 창 끝 = detector 평가 하한 (계획 04 §7-3).
        # post 대기 중(세션 열림)에는 register_triggers 가 재트리거를 기존 세션에 흡수하므로
        # 이 값이 필요 없다. 세션이 닫히는 순간 갱신되고, 그때부터 의미가 생긴다.
        self._detect_since: datetime | None = None

    def tick(self) -> list[SnapshotBundle]:
        """1회 관측 사이클. 이 틱에 완성된 번들을 반환한다(없으면 [])."""
        batches = [normalizer.normalize(collector.poll()) for collector, normalizer in self.sources]
        if not batches:
            return []
        for batch in batches:
            self.buffer.append(batch)
        observed_until = max(batch.observed_until for batch in batches)

        # finalize 가 먼저 — 이 틱에 완성된 번들의 창 끝이 아래 evaluate 의 하한이 된다.
        bundles = self.snapshot.finalize_ready(observed_until, self.buffer)
        if bundles:
            self._detect_since = bundles[-1].window.end

        evidences: list[TriggerEvidence] = [
            evidence
            for batch in batches
            for detector in self.detectors
            for evidence in detector.evaluate(batch, self.buffer, since=self._detect_since)
        ]
        self.snapshot.register_triggers(evidences, self.buffer)

        # 전송은 마지막. 실패해도 위 상태 전이는 이미 끝나 있다.
        for bundle in bundles:
            result = self.transport.send(bundle)
            if not result.accepted:
                logger.warning("번들 전송 실패 (창 %s): %s", bundle.window.end, result.error)
        return bundles

    def run(self, once: bool = False) -> None:
        while True:
            self.tick()
            if once:
                return
            time.sleep(self.settings.loop_interval_sec)


# detector_type → 클래스. Settings.trigger_conditions 의 키와 짝이 맞아야 한다 —
# 조건만 적어두고 detector 를 안 다는 실수는 test_runner_wiring 이 잡는다.
DETECTOR_TYPES: dict[str, type[TriggerDetector]] = {
    CpuSpikeDetector.DETECTOR_TYPE: CpuSpikeDetector,
    RestartMarkerDetector.DETECTOR_TYPE: RestartMarkerDetector,
    TraceFivexxDetector.DETECTOR_TYPE: TraceFivexxDetector,
    NginxErrorDetector.DETECTOR_TYPE: NginxErrorDetector,
    ErrorRateDetector.DETECTOR_TYPE: ErrorRateDetector,
    LatencySpikeDetector.DETECTOR_TYPE: LatencySpikeDetector,
}


def build_runner(settings: Settings | None = None) -> Runner:
    """Settings 만으로 실운용 Runner 를 조립한다 — 배선의 정답을 여기 한 곳에 둔다."""
    settings = settings or load_settings()
    validate_source_layout(settings.source_root)  # 경로 오류 = 기동 시 즉시 실패 (계획 06 §3)
    expected = settings.expected_services
    return Runner(
        settings,
        sources=[
            (LogCollector(settings.source_root), LogNormalizer(expected)),
            (MetricCollector(settings.source_root), MetricNormalizer(expected)),
            (TraceCollector(settings.source_root), TraceNormalizer(expected)),
        ],
        buffer=MemoryBuffer(settings.buffer_retention_sec),
        detectors=[
            DETECTOR_TYPES[name](dict(condition))
            for name, condition in settings.trigger_conditions.items()
        ],
        snapshot=SnapshotManager(),
        transport=TransportClient(settings.collect_endpoint),
    )
