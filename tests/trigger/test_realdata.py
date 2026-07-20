"""실데이터로 detector 발화 확인. 정규화기 대역(로컬 추출). 데이터 없으면 skip."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.normalization.metric import MetricNormalizer
from rca_sdk.schemas.events import (
    Modality,
    MultimodalSnapshot,
    NormalizedBatch,
    NormalizedLog,
    NormalizedMetric,
    NormalizedTrace,
    RawBatch,
)
from rca_sdk.trigger.code_stop.log import NginxErrorDetector
from rca_sdk.trigger.code_stop.trace import TraceFivexxDetector
from rca_sdk.trigger.perf.metric import CPU_METRIC, CpuSpikeDetector
from rca_sdk.trigger.svc_kill.log import RestartMarkerDetector

ROOT = Path(__file__).resolve().parents[2] / "datasets/sn"
SVCKILL_LOGS = ROOT / "log_data/Svc_Kill_Media_20251104_000111_logs_2025-11-04_00-21-42"
CODESTOP_LOGS = ROOT / "log_data/Code_Stop_MediaService_20251104_024819_logs_2025-11-04_03-21-39"
CODESTOP_TRACES = (
    ROOT / "trace_data/Code_Stop_MediaService_20251104_024819_traces_2025-11-04_03-21-39"
)
PERF_METRICS = ROOT / "metric_data/Perf_CPU_Contention_20251103_222601_metrics_2025-11-03_22-46-44"

pytestmark = pytest.mark.skipif(not ROOT.exists(), reason="datasets/sn 미커밋 클론")

BOOT_RE = re.compile(
    r"^\[(\d{4}-[A-Za-z]{3}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*Starting the (\S+) server"
)
NGINX_ERR_RE = re.compile(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} \[error\]")


class FakeBuffer:
    """계약(get_snapshot)만 흉내내는 대역 — window_sec 같은 내부 속성은 없다."""

    def __init__(
        self,
        logs: list[NormalizedLog] | None = None,
        metrics: list[NormalizedMetric] | None = None,
    ) -> None:
        self._logs = logs or []
        self._metrics = metrics or []

    def get_snapshot(self, start_ts: datetime, end_ts: datetime) -> MultimodalSnapshot:
        return MultimodalSnapshot(
            logs=[r for r in self._logs if start_ts <= r.timestamp < end_ts],
            metrics=[r for r in self._metrics if start_ts <= r.timestamp < end_ts],
        )


def _batch(modality: Modality, records: list, until: datetime) -> NormalizedBatch:
    return NormalizedBatch(
        modality=modality,
        observed_from=until - timedelta(days=1),
        observed_until=until,
        records=records,
    )


def test_restart_marker_fires_on_real_svckill_logs():
    logs: list[NormalizedLog] = []
    for log_file in sorted(SVCKILL_LOGS.glob("*Service_.log")):
        for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
            match = BOOT_RE.search(line)
            if match:
                ts = datetime.strptime(match.group(1), "%Y-%b-%d %H:%M:%S.%f")
                svc = match.group(2).replace("-service", "").replace("-server", "")
                logs.append(
                    NormalizedLog(timestamp=ts, service=svc, event_type="service_start")
                )
    assert logs, "부팅 마커 추출 실패 — 경로/포맷 확인"
    until = max(rec.timestamp for rec in logs) + timedelta(seconds=1)
    ev = RestartMarkerDetector({"threshold": 2}).evaluate(
        _batch(Modality.LOG, [], until), FakeBuffer(logs)
    )
    assert [e.service for e in ev] == ["media"]
    assert ev[0].value == 2.0
    assert ev[0].trigger_time == datetime(2025, 11, 4, 0, 3, 41, 500315)


def test_trace_5xx_fires_on_real_codestop_traces():
    until = datetime(2025, 11, 4, 3, 21, 39)
    records: list[NormalizedTrace] = []
    with (CODESTOP_TRACES / "all_traces.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw = row.get("http_status_code", "").strip()
            code = int(raw) if raw.isdigit() else None
            records.append(NormalizedTrace(timestamp=until, http_status_code=code))
    ev = TraceFivexxDetector({"baseline": 0.0, "floor": 3.0}).evaluate(
        _batch(Modality.TRACE, records, until), None
    )
    assert len(ev) == 1
    # 실측 기대치: Code_Stop 구간의 500 span 은 ~70 건(baseline 은 0). floor=3 을 넉넉히 넘는다.
    assert ev[0].value >= 4.0


def test_nginx_error_fires_on_real_codestop_log():
    until = datetime(2025, 11, 4, 3, 21, 39)
    text = (CODESTOP_LOGS / "NginxThrift_.log").read_text(encoding="utf-8", errors="replace")
    records = [
        NormalizedLog(timestamp=until, service="nginx", event_type="connection_error")
        for line in text.splitlines()
        if NGINX_ERR_RE.search(line)
    ]
    ev = NginxErrorDetector({"baseline": 0.0, "floor": 3.0}).evaluate(
        _batch(Modality.LOG, records, until), None
    )
    assert len(ev) == 1
    assert ev[0].value >= 4.0


def _normalized_cpu_batch(until: datetime) -> NormalizedBatch:
    """실 CSV → **실제 MetricNormalizer** 통과. 손으로 NormalizedMetric 을 만들지 않는다.

    직접 만들면 detector 가 기대하는 `metric_name` 을 테스트가 그대로 복사해 넣게 되어,
    Normalizer 실출력과 어긋나도 초록불이 된다(실제로 `system_cpu` vs `system_cpu_usage` 로
    어긋나 cpu_spike 가 무발화였다). 이 이음매를 밟는 것이 이 테스트의 존재 이유다.
    """
    name = "system_cpu_usage.csv"
    with (PERF_METRICS / name).open(encoding="utf-8") as fh:
        rows = [{**row, "_source": name} for row in csv.DictReader(fh)]
    assert rows, "cpu 샘플 추출 실패"
    return MetricNormalizer().normalize(
        RawBatch(
            modality=Modality.METRIC,
            observed_from=until - timedelta(days=1),
            observed_until=until,
            records=rows,
            sources=[name],
        )
    )


def test_cpu_metric_name_matches_normalizer_output():
    """계약 고정: detector 의 CPU_METRIC == Normalizer 가 실제로 내는 metric_name.

    알고리즘 테스트(test_cpu_spike.py)는 CPU_METRIC 을 그대로 쓰므로 이름이 어긋나도 통과한다.
    이름 정합은 오직 여기서만 깨진다.
    """
    batch = _normalized_cpu_batch(datetime(2025, 11, 3, 22, 33, 29))
    assert {r.metric_name for r in batch.records} == {CPU_METRIC}


def test_cpu_spike_plateau_on_real_perf_metrics():
    # 실 파이프라인 그대로: Normalizer → MemoryBuffer → Detector (대역 없음)
    plateau_anchor = datetime(2025, 11, 3, 22, 33, 29)
    buffer = MemoryBuffer(retention_sec=3600)  # 전 구간 보존 — 축출은 buffer 테스트 소관
    buffer.append(_normalized_cpu_batch(plateau_anchor))

    det = CpuSpikeDetector({"bar": 50.0, "min_over": 5, "window_sec": 210})
    # plateau 구간(22:27:59~22:33:29, ~100%) 끝 근처 anchor → 지속 발화
    fired = det.evaluate(_batch(Modality.METRIC, [], plateau_anchor), buffer)
    assert len(fired) == 1 and fired[0].value >= 5.0
    assert fired[0].extra["max_cpu"] == 100.0
    # 주입 전 정상 구간(~2%) anchor → 무발화
    silent = det.evaluate(_batch(Modality.METRIC, [], datetime(2025, 11, 3, 22, 27, 55)), buffer)
    assert silent == []
