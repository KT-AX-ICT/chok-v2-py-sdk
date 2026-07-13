"""스캐폴드 스모크 테스트 — 패키지 import 와 실동작 코어(buffer/correlation/baseline)를 확인."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import rca_sdk
from rca_sdk.buffer import MemoryBuffer
from rca_sdk.trigger.baseline import load_baseline
from rca_sdk.trigger.correlation import canonical_service, correlate
from rca_sdk.trigger.models import Candidate, ModalitySignal


def test_version():
    assert rca_sdk.__version__ == "0.1.0"


def test_canonical_service():
    assert canonical_service("MediaService") == "media"
    assert canonical_service("user-service") == "user"
    assert canonical_service(None) is None


def test_buffer_evicts_old_events(make_event):
    buf = MemoryBuffer(window_sec=210)
    t0 = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)
    buf.add(make_event(ts=t0))
    buf.add(make_event(ts=t0 + timedelta(seconds=400)))  # 윈도 밖 → 옛 이벤트 축출
    assert len(buf) == 1


def test_correlate_converges_by_service():
    def sig(modality, service):
        c = Candidate(service=service, signal="err", value=1, baseline=0, severity=1.0)
        return ModalitySignal(modality=modality, triggered=True, candidates=[c])

    sigs = [sig("log", "MediaService"), sig("trace", "media-service")]
    incidents = correlate(sigs)
    assert len(incidents) == 1
    assert incidents[0].corroboration == 2  # log + trace 가 media 로 수렴


def test_load_baseline_placeholder():
    b = load_baseline("sn_normal")
    assert b["dataset"] == "SN"
