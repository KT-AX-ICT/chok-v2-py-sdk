"""포함된 normal/장애 원본이 현재 detector 정책과 맞는지 fast replay로 검증한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from demo.replayer.scheduler import merged
from demo.replayer.writer import Writer
from demo.simulator.catalog import load_all
from demo.simulator.filters import keep_baseline_record
from demo.simulator.playback import CyclicPlayback, Playback
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

DATASET_ROOT = Path(__file__).resolve().parents[3] / "datasets" / "sn"
PREFIXES = {
    "normal": "Normal_Baseline",
    "cpu": "Perf_CPU_Contention",
    "kill_media": "Svc_Kill_Media",
    "code_media": "Code_Stop_MediaService",
}


class FastClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 24, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class Result:
    fires: list[TriggerEvidence] = field(default_factory=list)
    bundles: list[SnapshotBundle] = field(default_factory=list)


class CapturingTransport:
    def __init__(self, result: Result) -> None:
        self.result = result

    def send(self, bundle: SnapshotBundle) -> SubmissionResult:
        self.result.bundles.append(bundle)
        return SubmissionResult(accepted=True)


def scenario_dirs(prefix: str) -> dict[Modality, Path]:
    result = {}
    for modality in Modality:
        hits = sorted((DATASET_ROOT / f"{modality.value}_data").glob(f"{prefix}_*"))
        assert len(hits) == 1
        result[modality] = hits[0]
    return result


def replay(prefix: str, max_ticks: int | None = None) -> Result:
    settings = Settings()
    dirs = scenario_dirs(prefix)
    probes = {modality: DatasetReplayCollector(path, modality) for modality, path in dirs.items()}
    origin = min(probe.origin for probe in probes.values())
    collectors = {
        modality: DatasetReplayCollector(path, modality, origin=origin)
        for modality, path in dirs.items()
    }
    normalizers = {
        Modality.LOG: LogNormalizer(settings.expected_services),
        Modality.METRIC: MetricNormalizer(settings.expected_services),
        Modality.TRACE: TraceNormalizer(settings.expected_services),
    }
    result = Result()
    snapshot = SnapshotManager()
    register = snapshot.register_triggers

    def capture(evidences: list[TriggerEvidence], buffer: MemoryBuffer) -> None:
        result.fires.extend(evidences)
        register(evidences, buffer)

    snapshot.register_triggers = capture  # type: ignore[method-assign]
    runner = Runner(
        settings,
        sources=[
            (collectors[modality], normalizers[modality])
            for modality in (Modality.LOG, Modality.METRIC, Modality.TRACE)
        ],
        buffer=MemoryBuffer(settings.buffer_retention_sec),
        detectors=[
            DETECTOR_TYPES[name](dict(condition))
            for name, condition in settings.trigger_conditions.items()
        ],
        snapshot=snapshot,
        transport=CapturingTransport(result),
    )

    limit = max_ticks or 200
    for _ in range(limit):
        runner.tick()
        if max_ticks is None and all(collector.exhausted for collector in collectors.values()):
            break
    return result


def test_normal_baseline_is_silent_for_all_detectors():
    result = replay(PREFIXES["normal"])
    assert result.fires == []
    assert result.bundles == []


def test_baseline_filter_removes_only_its_eleven_cold_starts():
    baseline, incidents = load_all(DATASET_ROOT)
    baseline_starts = [
        (record, loaded)
        for record, loaded in merged(baseline.loaded)
        if not keep_baseline_record(record, loaded)
    ]
    cpu_starts = [
        (record, loaded)
        for record, loaded in merged(incidents["cpu"].loaded)
        if not keep_baseline_record(record, loaded)
    ]

    assert len(baseline_starts) == 11
    # 같은 predicate를 CPU에 적용하면 11개를 찾지만, engine은 baseline에만 적용한다.
    assert len(cpu_starts) == 11


def test_normal_to_cpu_output_has_only_cpu_cold_starts(tmp_path: Path):
    baseline, incidents = load_all(DATASET_ROOT)
    clock = FastClock()
    output = tmp_path / "out"

    with Writer(output) as writer:
        target = CyclicPlayback(
            baseline,
            clock=clock,
            sleep=clock.sleep,
            record_filter=keep_baseline_record,
        ).play(writer, clock(), 60)
        Playback(
            incidents["cpu"],
            clock=clock,
            sleep=clock.sleep,
        ).play_window(writer, target, 30)

    starts = 0
    for path in (output / "log").glob("*.log"):
        starts += sum(") Starting" in line for line in path.read_text().splitlines())
    assert starts == 11


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("cpu", {"cpu_spike"}),
        ("kill_media", {"restart_marker"}),
        ("code_media", {"nginx_error", "trace_5xx"}),
    ],
)
def test_first_330_seconds_trigger_and_finalize_one_report(scenario: str, expected: set[str]):
    # 11 × 30초 = 330초. 가장 늦은 code_media trace_5xx(270초)와 post 끝(330초) 포함.
    result = replay(PREFIXES[scenario], max_ticks=11)
    fired = {evidence.detector_type for evidence in result.fires}
    assert expected <= fired
    assert len(result.bundles) == 1
