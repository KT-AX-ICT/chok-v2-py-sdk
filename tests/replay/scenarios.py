"""시나리오 재생 실행기 — 데이터셋 1개를 끝까지 돌리고 관측 결과를 모은다 (계획 05 §4).

Runner·normalizer·buffer·detector·SnapshotManager 는 전부 **실제 구현**이다.
대체하는 것은 파일 tail(`Collector.poll`)과 전송(`Transport.send`) 둘뿐.
"""

from __future__ import annotations

import time
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
    # 연속성·성능 관측 (계획 05 §6)
    normalized: dict[Modality, int] = field(default_factory=dict)  # 정규화를 통과한 레코드
    raw_polled: dict[Modality, int] = field(default_factory=dict)  # poll 이 낸 원시 레코드
    gaps: list[str] = field(default_factory=list)  # 배치 불연속 (N.until != N+1.from)
    elapsed_sec: float = 0.0

    def fired_types(self) -> set[str]:
        return {f.evidence.detector_type for f in self.fires}

    def first_fire(self, detector_type: str) -> Fire | None:
        return next((f for f in self.fires if f.evidence.detector_type == detector_type), None)

    def dropped(self, modality: Modality) -> int:
        """정규화에서 해석 실패로 버려진 레코드 수 (계획 03 N3)."""
        return self.raw_polled.get(modality, 0) - self.normalized.get(modality, 0)


class _ObservingNormalizer:
    """정규화 전후 건수와 배치 연속성을 세는 얇은 래퍼. 정규화 자체는 실제 구현이 한다."""

    def __init__(self, inner, modality: Modality, result: ReplayResult) -> None:
        self._inner = inner
        self._modality = modality
        self._result = result
        self._previous_until: datetime | None = None

    @property
    def expected_services(self):  # noqa: ANN201 — 배선 검증용 통과 속성
        return self._inner.expected_services

    def normalize(self, batch):  # noqa: ANN001, ANN201
        if self._previous_until is not None and batch.observed_from != self._previous_until:
            self._result.gaps.append(
                f"{self._modality.value}: {self._previous_until} → {batch.observed_from}"
            )
        self._previous_until = batch.observed_until
        self._result.raw_polled[self._modality] = self._result.raw_polled.get(
            self._modality, 0
        ) + len(batch.records)
        normalized = self._inner.normalize(batch)
        self._result.normalized[self._modality] = self._result.normalized.get(
            self._modality, 0
        ) + len(normalized.records)
        return normalized


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
    normalizers = {
        Modality.LOG: LogNormalizer(expected),
        Modality.METRIC: MetricNormalizer(expected),
        Modality.TRACE: TraceNormalizer(expected),
    }
    runner = Runner(
        settings,
        sources=[
            (collectors[m], _ObservingNormalizer(normalizers[m], m, result))
            for m in (Modality.LOG, Modality.METRIC, Modality.TRACE)
        ],
        buffer=MemoryBuffer(settings.buffer_retention_sec),
        detectors=[
            DETECTOR_TYPES[n](dict(cond)) for n, cond in settings.trigger_conditions.items()
        ],
        snapshot=snapshot,
        transport=transport,
    )

    started = time.perf_counter()
    for tick in range(MAX_TICKS):
        result.ticks = tick
        runner.tick()  # 예외가 나면 여기서 터진다 — 끊김 없이 도는지가 이 재생의 1차 검증
        if all(c.exhausted for c in collectors.values()):
            break
    result.elapsed_sec = time.perf_counter() - started
    result.ticks += 1
    result.bundles = transport.sent
    return result
