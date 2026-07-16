"""스캐폴드 스모크 테스트 — 패키지 import 와 인터페이스 계약 타입을 확인.

내부 로직은 아직 스캐폴드(TODO)라, 여기서는 계약(타입/ABC)이 성립하는지만 검증한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

import rca_sdk
from rca_sdk.collectors.base import Collector
from rca_sdk.normalization.base import Normalizer
from rca_sdk.schemas import (
    BundleRecord,
    Modality,
    MultimodalSnapshot,
    NormalizedBatch,
    NormalizedLog,
    NormalizedMetric,
    NormalizedTrace,
    RawBatch,
    SnapshotBundle,
    SubmissionResult,
    TriggerInfo,
    Window,
)
from rca_sdk.transport.client import Transport
from rca_sdk.trigger.detector import TriggerDetector
from rca_sdk.trigger.models import TriggerEvidence

TS = datetime(2026, 7, 15, 12, 0, 0)


def test_version():
    assert rca_sdk.__version__ == "0.1.0"


def test_record_schemas_instantiate():
    NormalizedLog(timestamp=TS, canonical_service="user", level="error")
    NormalizedTrace(timestamp=TS, canonical_service="nginx", http_status_code=500)
    NormalizedMetric(
        timestamp=TS, canonical_service="user", metric_name="container_cpu", value=0.97
    )


def test_batch_and_snapshot_contracts():
    log = NormalizedLog(timestamp=TS, canonical_service="user")
    raw = RawBatch(modality=Modality.LOG, observed_from=TS, observed_until=TS, records=[{"x": 1}])
    nb = NormalizedBatch(modality=Modality.LOG, observed_from=TS, observed_until=TS, records=[log])
    snap = MultimodalSnapshot(logs=[log])
    assert raw.modality is Modality.LOG
    assert nb.records[0].canonical_service == "user"
    assert snap.metrics == []


def test_trigger_evidence():
    ev = TriggerEvidence(
        trigger_time=TS,
        modality=Modality.METRIC,
        detector_type="cpu_spike",
        value=0.97,
        baseline=0.2,
        threshold=0.5,
    )
    assert ev.detector_type == "cpu_spike"


def test_snapshot_bundle_fixed_shape():
    bundle = SnapshotBundle(
        window=Window(start=TS, end=TS),
        trigger_info=TriggerInfo(trigger_time=TS, triggered_by=["metric", "log"]),
        logs=[BundleRecord(timestamp=TS, service="user", raw='{"level":"error"}')],
    )
    assert bundle.bundle_version == "1.0"
    assert bundle.trigger_info.triggered_by == ["metric", "log"]
    assert isinstance(bundle.logs[0].raw, str)  # raw = JSON 을 문자열로 감싼 형태


def test_submission_result():
    assert SubmissionResult(accepted=True, job_id="j1").accepted is True


@pytest.mark.parametrize("abc_cls", [Collector, Normalizer, Transport])
def test_boundary_abcs_cannot_instantiate(abc_cls):
    with pytest.raises(TypeError):
        abc_cls()


def test_trigger_detector_is_abstract():
    with pytest.raises(TypeError):
        TriggerDetector(condition={})
