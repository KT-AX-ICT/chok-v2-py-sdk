"""Runner.tick() 순서 계약 (계획 05 §2).

tick 순서 자체가 계약이다:
    append -> finalize_ready -> evaluate -> register_triggers -> send

- append 가 먼저인 이유: 창 기반 detector 가 버퍼를 되돌아본다
- finalize_ready 가 evaluate 앞인 이유: 이 틱에 완성된 번들의 창 끝이 곧 이번 평가의
  하한(since)이다. 뒤집으면 방금 전송한 구간으로 즉시 재발화한다 (계획 04 §7-3)
- send 가 마지막인 이유: 전송이 실패해도 _detect_since 는 이미 전진해 있어야 한다

여기서는 대역(fake)으로 **순서와 배선**만 본다. 각 계층의 알고리즘은 자기 테스트가 있다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.config import Settings
from rca_sdk.runtime.runner import Runner
from rca_sdk.schemas.events import (
    Modality,
    NormalizedBatch,
    NormalizedMetric,
    RawBatch,
)
from rca_sdk.schemas.snapshot import SnapshotBundle, SubmissionResult, TriggerInfo, Window
from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence

T0 = datetime(2025, 11, 4, 0, 0, 0)


# ── 대역 ────────────────────────────────────────────────────────────────────


class FakeCollector:
    """호출할 때마다 다음 30초 배치를 낸다."""

    def __init__(self, modality: Modality, log: list[str]) -> None:
        self.modality = modality
        self._tick = 0
        self._log = log

    def poll(self) -> RawBatch:
        start = T0 + timedelta(seconds=30 * self._tick)
        self._tick += 1
        self._log.append("poll")
        return RawBatch(
            modality=self.modality,
            observed_from=start,
            observed_until=start + timedelta(seconds=30),
            records=[],
            sources=["system_cpu_usage.csv"],
        )


class FakeNormalizer:
    def __init__(self, log: list[str], records: list[NormalizedMetric] | None = None) -> None:
        self._log = log
        self._records = records or []

    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        self._log.append("normalize")
        return NormalizedBatch(
            modality=batch.modality,
            observed_from=batch.observed_from,
            observed_until=batch.observed_until,
            records=[r for r in self._records if batch.observed_from <= r.timestamp],
        )


class RecordingDetector(TriggerDetector):
    """evaluate 호출 시각의 since 를 기록하고, fire_on_tick 에서만 발화한다."""

    def __init__(self, log: list[str], fire_on_tick: set[int] | None = None) -> None:
        super().__init__({})
        self._log = log
        self._fire_on = fire_on_tick or set()
        self._tick = 0
        self.seen_since: list[datetime | None] = []

    def evaluate(self, new_batch, buffer, since=None) -> list[TriggerEvidence]:  # noqa: ANN001
        self._log.append("evaluate")
        self.seen_since.append(since)
        tick = self._tick
        self._tick += 1
        if tick not in self._fire_on:
            return []
        return [
            TriggerEvidence(
                trigger_time=new_batch.observed_until,
                modality=new_batch.modality,
                service="__node__",
                detector_type="fake",
                value=1.0,
                baseline=0.0,
                threshold=0.0,
            )
        ]


class RecordingSnapshot:
    """SnapshotManager 대역 — 호출 순서 기록 + 지정한 틱에 번들 반환."""

    def __init__(self, log: list[str], finalize_on_tick: set[int] | None = None) -> None:
        self._log = log
        self._finalize_on = finalize_on_tick or set()
        self._tick = 0
        self.registered: list[TriggerEvidence] = []

    def finalize_ready(self, observed_until, buffer) -> list[SnapshotBundle]:  # noqa: ANN001
        self._log.append("finalize_ready")
        tick = self._tick
        self._tick += 1
        if tick not in self._finalize_on:
            return []
        return [
            SnapshotBundle(
                window=Window(start=observed_until - timedelta(seconds=360), end=observed_until),
                trigger_info=TriggerInfo(trigger_time=observed_until, triggered_by=["metric"]),
            )
        ]

    def register_triggers(self, evidences, buffer) -> None:  # noqa: ANN001
        self._log.append("register_triggers")
        self.registered.extend(evidences)


class RecordingTransport:
    def __init__(self, log: list[str], fail: bool = False) -> None:
        self._log = log
        self._fail = fail
        self.sent: list[SnapshotBundle] = []

    def send(self, bundle: SnapshotBundle) -> SubmissionResult:
        self._log.append("send")
        if self._fail:
            return SubmissionResult(accepted=False, error="boom")
        self.sent.append(bundle)
        return SubmissionResult(accepted=True)


def build(
    log: list[str],
    *,
    fire_on_tick: set[int] | None = None,
    finalize_on_tick: set[int] | None = None,
    transport: RecordingTransport | None = None,
) -> tuple[Runner, RecordingDetector, RecordingSnapshot]:
    detector = RecordingDetector(log, fire_on_tick)
    snapshot = RecordingSnapshot(log, finalize_on_tick)
    runner = Runner(
        Settings(),
        sources=[(FakeCollector(Modality.METRIC, log), FakeNormalizer(log))],
        buffer=MemoryBuffer(),
        detectors=[detector],
        snapshot=snapshot,
        transport=transport or RecordingTransport(log),
    )
    return runner, detector, snapshot


# ── 순서 계약 ───────────────────────────────────────────────────────────────


def test_tick_order_without_bundle():
    log: list[str] = []
    runner, _, _ = build(log)
    runner.tick()
    assert log == ["poll", "normalize", "finalize_ready", "evaluate", "register_triggers"]


def test_finalize_runs_before_evaluate():
    """이 틱에 완성된 번들의 창 끝이 곧 이번 평가의 하한이어야 한다."""
    log: list[str] = []
    runner, _, _ = build(log, finalize_on_tick={0})
    runner.tick()
    assert log.index("finalize_ready") < log.index("evaluate")


def test_send_runs_last():
    """전송이 마지막이라, 실패해도 _detect_since 는 이미 전진해 있다."""
    log: list[str] = []
    runner, _, _ = build(log, finalize_on_tick={0})
    runner.tick()
    assert log[-1] == "send"
    assert log.index("register_triggers") < log.index("send")


# ── _detect_since 배선 (계획 04 §7-3) ──────────────────────────────────────


def test_detect_since_starts_none():
    log: list[str] = []
    runner, detector, _ = build(log)
    runner.tick()
    assert detector.seen_since == [None]


def test_detect_since_advances_to_bundle_window_end():
    log: list[str] = []
    runner, detector, snapshot = build(log, finalize_on_tick={1})
    runner.tick()  # 번들 없음
    runner.tick()  # 번들 완성 → 이 틱의 evaluate 부터 since 적용
    bundle_end = T0 + timedelta(seconds=60)  # 2번째 틱의 observed_until
    assert detector.seen_since == [None, bundle_end]


def test_detect_since_persists_after_bundle():
    log: list[str] = []
    runner, detector, _ = build(log, finalize_on_tick={0})
    runner.tick()
    runner.tick()
    bundle_end = T0 + timedelta(seconds=30)
    assert detector.seen_since == [bundle_end, bundle_end]


def test_detect_since_advances_even_when_send_fails():
    log: list[str] = []
    transport = RecordingTransport(log, fail=True)
    runner, detector, _ = build(log, finalize_on_tick={0}, transport=transport)
    runner.tick()
    runner.tick()
    # 전송 실패해도 하한은 전진 — 같은 번들을 무한 재시도하지 않는다
    assert detector.seen_since[1] == T0 + timedelta(seconds=30)
    assert transport.sent == []


# ── 배선 ────────────────────────────────────────────────────────────────────


def test_evidences_reach_register_triggers():
    log: list[str] = []
    runner, _, snapshot = build(log, fire_on_tick={0})
    runner.tick()
    assert len(snapshot.registered) == 1
    assert snapshot.registered[0].detector_type == "fake"


def test_tick_returns_finalized_bundles():
    log: list[str] = []
    runner, _, _ = build(log, finalize_on_tick={0})
    bundles = runner.tick()
    assert len(bundles) == 1
    assert bundles[0].window.end == T0 + timedelta(seconds=30)


def test_batch_lands_in_buffer_before_evaluate():
    """append 가 evaluate 앞이라 detector 가 이번 배치를 버퍼에서 볼 수 있다."""
    log: list[str] = []
    rec = NormalizedMetric(
        timestamp=T0 + timedelta(seconds=10), service="__node__", metric_name="x", value=1.0
    )
    buffer = MemoryBuffer()
    runner = Runner(
        Settings(),
        sources=[(FakeCollector(Modality.METRIC, log), FakeNormalizer(log, [rec]))],
        buffer=buffer,
        detectors=[],
        snapshot=RecordingSnapshot(log),
        transport=RecordingTransport(log),
    )
    runner.tick()
    snap = buffer.get_snapshot(T0, T0 + timedelta(seconds=30))
    assert len(snap.metrics) == 1
