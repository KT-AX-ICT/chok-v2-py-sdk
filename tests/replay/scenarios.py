"""시나리오 재생 실행기 — 데이터셋 1개를 끝까지 돌리고 관측 결과를 모은다 (계획 05 §4).

Runner·normalizer·buffer·detector·SnapshotManager 는 전부 **실제 구현**이다.
대체하는 것은 파일 tail(`Collector.poll`)과 전송(`Transport.send`) 둘뿐.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.config import Settings
from rca_sdk.normalization.log import LogNormalizer
from rca_sdk.normalization.metric import MetricNormalizer
from rca_sdk.normalization.trace import TraceNormalizer
from rca_sdk.runtime.runner import DETECTOR_TYPES, Runner
from rca_sdk.schemas.events import Modality
from rca_sdk.schemas.snapshot import SnapshotBundle, SubmissionResult
from rca_sdk.snapshot.assembler import SnapshotManager
from rca_sdk.trigger.models import TriggerEvidence
from tests.replay.harness import DatasetReplayCollector

DATASET_ROOT = Path(__file__).resolve().parents[2] / "datasets/sn"

# 시나리오명 → 데이터셋 디렉토리 접두어. 3개 모달리티가 디렉토리를 따로 쓴다.
SCENARIOS = {
    "Svc_Kill_Media": "Svc_Kill_Media",
    "Code_Stop_MediaService": "Code_Stop_MediaService",
    "Perf_CPU_Contention": "Perf_CPU_Contention",
}
_MODALITY_DIRS = {
    Modality.LOG: "log_data",
    Modality.METRIC: "metric_data",
    Modality.TRACE: "trace_data",
}
MAX_TICKS = 200  # 폭주 방지 — 실제 시나리오는 41~52 틱


@dataclass
class Fire:
    """detector 발화 1건 + 그것이 관측된 틱."""

    tick: int
    evidence: TriggerEvidence


@dataclass
class ReplayResult:
    scenario: str
    origin: datetime
    ticks: int
    fires: list[Fire] = field(default_factory=list)
    bundles: list[SnapshotBundle] = field(default_factory=list)
    loaded: dict[Modality, int] = field(default_factory=dict)

    def fired_types(self) -> set[str]:
        return {f.evidence.detector_type for f in self.fires}

    def first_fire(self, detector_type: str) -> Fire | None:
        return next((f for f in self.fires if f.evidence.detector_type == detector_type), None)


class _CapturingTransport:
    """전송 대역 — 번들을 모아만 둔다. 네트워크는 이 테스트의 관심사가 아니다."""

    def __init__(self) -> None:
        self.sent: list[SnapshotBundle] = []

    def send(self, bundle: SnapshotBundle) -> SubmissionResult:
        self.sent.append(bundle)
        return SubmissionResult(accepted=True)


def dataset_available() -> bool:
    return DATASET_ROOT.exists()


def _scenario_dirs(prefix: str) -> dict[Modality, Path]:
    dirs = {}
    for modality, sub in _MODALITY_DIRS.items():
        matches = sorted((DATASET_ROOT / sub).glob(f"{prefix}_*"))
        if not matches:
            raise FileNotFoundError(f"{prefix} / {sub} 데이터 없음")
        dirs[modality] = matches[0]
    return dirs


def run_scenario(name: str, settings: Settings | None = None) -> ReplayResult:
    """시나리오를 30초 배치로 끝까지 재생하고 발화·번들을 모아 돌려준다."""
    settings = settings or Settings()
    dirs = _scenario_dirs(SCENARIOS[name])

    # 3개 모달리티가 같은 틱 경계를 공유해야 한다 — 러너가 한 틱에 셋을 함께 poll 하는
    # 실제 동작과 맞춘다(ADR-007 §4). 그래서 origin 은 전체 최솟값으로 통일한다.
    probes = {m: DatasetReplayCollector(d, m) for m, d in dirs.items()}
    origin = min(p.origin for p in probes.values())
    loaded = {m: len(p._records) for m, p in probes.items()}

    collectors = {m: DatasetReplayCollector(d, m, origin=origin) for m, d in dirs.items()}
    transport = _CapturingTransport()
    snapshot = SnapshotManager()
    result = ReplayResult(scenario=name, origin=origin, ticks=0, loaded=loaded)

    # register_triggers 를 감싸 발화를 관측한다 — Runner 는 근거를 반환하지 않는다.
    original_register = snapshot.register_triggers

    def observing_register(evidences: list[TriggerEvidence], buffer: MemoryBuffer) -> None:
        result.fires.extend(Fire(tick=result.ticks, evidence=e) for e in evidences)
        original_register(evidences, buffer)

    snapshot.register_triggers = observing_register  # type: ignore[method-assign]

    expected = settings.expected_services
    runner = Runner(
        settings,
        sources=[
            (collectors[Modality.LOG], LogNormalizer(expected)),
            (collectors[Modality.METRIC], MetricNormalizer(expected)),
            (collectors[Modality.TRACE], TraceNormalizer(expected)),
        ],
        buffer=MemoryBuffer(settings.buffer_retention_sec),
        detectors=[
            DETECTOR_TYPES[n](dict(cond)) for n, cond in settings.trigger_conditions.items()
        ],
        snapshot=snapshot,
        transport=transport,
    )

    for tick in range(MAX_TICKS):
        result.ticks = tick
        runner.tick()
        if all(c.exhausted for c in collectors.values()):
            break
    result.ticks += 1
    result.bundles = transport.sent
    return result
