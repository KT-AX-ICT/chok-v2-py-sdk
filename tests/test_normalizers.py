"""Normalizer 3종 테스트 — 실측 라인/행을 축약한 인라인 픽스처 (ADR-004)."""

from __future__ import annotations

from datetime import datetime

from rca_sdk.normalization.log import LogNormalizer
from rca_sdk.normalization.metric import MetricNormalizer
from rca_sdk.normalization.trace import TraceNormalizer
from rca_sdk.schemas.events import Modality, RawBatch

WINDOW = {
    "observed_from": datetime(2025, 11, 4, 0, 0, 0),
    "observed_until": datetime(2025, 11, 4, 0, 0, 30),
}

BOOST_STARTING = (
    "[2025-Nov-04 00:01:57.490560] <info>: "
    "(MediaService.cpp:44:main) Starting the media-service server..."
)
NGINX_RESOLVE = (
    "2025/11/04 02:58:25 [error] 9#9: *816 [lua] compose.lua:62: ComposePost(): "
    "compost_post failure: Could not resolve host for client socket., client: 192.168.64.1"
)
BOOST_CONNECT = (
    "[2025-Nov-04 02:58:00.000000] <error>: (TextHandler.h:10:main) "
    "TTransportException: Could not connect to media-service:9090"
)


def log_batch(records: list[dict], sources: list[str]) -> RawBatch:
    return RawBatch(modality=Modality.LOG, records=records, sources=sources, **WINDOW)


def test_boost_line_parsed():
    batch = log_batch(
        [{"raw": BOOST_STARTING, "_source": "MediaService_.log"}], ["MediaService_.log"]
    )
    [rec] = LogNormalizer().normalize(batch).records
    assert rec.service == "media"
    assert rec.log_type == "service_log"
    assert rec.level == "info"
    assert rec.code_loc == "MediaService.cpp:44"
    assert rec.timestamp == datetime(2025, 11, 4, 0, 1, 57, 490560)
    assert rec.event_type == "service_start"      # restart_marker 원천
    assert rec.target_service is None
    assert rec.message.startswith("Starting the media-service")


def test_nginx_line_parsed_anonymous_resolve_host():
    batch = log_batch(
        [{"raw": NGINX_RESOLVE, "_source": "NginxThrift_.log"}], ["NginxThrift_.log"]
    )
    [rec] = LogNormalizer().normalize(batch).records
    assert rec.service == "nginx"
    assert rec.log_type == "nginx_log"
    assert rec.level == "error"
    assert rec.code_loc == "compose.lua:62"
    assert rec.timestamp == datetime(2025, 11, 4, 2, 58, 25)
    assert rec.event_type == "connection_error"
    assert rec.target_service is None             # 익명 — Code_Stop 신호 그대로 보존


def test_connect_target_extracted():
    batch = log_batch(
        [{"raw": BOOST_CONNECT, "_source": "TextService_.log"}], ["TextService_.log"]
    )
    [rec] = LogNormalizer().normalize(batch).records
    assert rec.event_type == "connection_error"
    assert rec.target_service == "media"


def test_unparseable_line_skipped():
    batch = log_batch(
        [
            {"raw": "no timestamp here", "_source": "UserService_.log"},
            {"raw": BOOST_STARTING, "_source": "MediaService_.log"},
        ],
        ["UserService_.log", "MediaService_.log"],
    )
    out = LogNormalizer().normalize(batch)
    assert len(out.records) == 1  # 해석 불가 줄만 스킵 (N3)


def metric_batch(records: list[dict], sources: list[str]) -> RawBatch:
    return RawBatch(modality=Modality.METRIC, records=records, sources=sources, **WINDOW)


def test_container_metric_normalized():
    rec = {
        "timestamp": "2025-11-04 00:02:21",
        "value": "0.006794",
        "metric": 'container_label_com_docker_compose_service="user-service"',
        "container_label_com_docker_compose_service": "user-service",
        "_source": "socialnet_container_cpu.csv",
    }
    [out] = (
        MetricNormalizer().normalize(metric_batch([rec], ["socialnet_container_cpu.csv"])).records
    )
    assert out.service == "user"
    assert out.metric_name == "container_cpu"     # socialnet_ 접두 제거
    assert out.value == 0.006794
    assert out.dimension == "user-service"
    assert out.unit == "fraction"
    assert out.timestamp == datetime(2025, 11, 4, 0, 2, 21)


def test_system_metric_is_node():
    rec = {
        "timestamp": "2025-11-04 00:03:13",
        "value": "53.95",
        "metric": 'instance="node-exporter:9100"',
        "instance": "node-exporter:9100",
        "_source": "system_cpu_usage.csv",
    }
    [out] = MetricNormalizer().normalize(metric_batch([rec], ["system_cpu_usage.csv"])).records
    assert out.service == "__node__"              # cpu_spike 신호 원천
    assert out.metric_name == "system_cpu_usage"
    assert out.unit == "percent"
    assert out.dimension == "node-exporter:9100"


def test_unknown_dimension_service_none():
    rec = {"timestamp": "2025-11-04 00:03:13", "value": "1.5", "_source": "jaeger_spans_rate.csv"}
    [out] = MetricNormalizer().normalize(metric_batch([rec], ["jaeger_spans_rate.csv"])).records
    assert out.service is None
    assert out.unit is None


def test_bad_metric_value_skipped():
    rec = {"timestamp": "2025-11-04 00:03:13", "value": "?", "_source": "system_load1.csv"}
    out = MetricNormalizer().normalize(metric_batch([rec], ["system_load1.csv"]))
    assert out.records == []                      # N3


TRACE_ROW = {
    "trace_id": "00375a1ade701ffa",
    "span_id": "b04a35bc78367bd0",
    "parent_span_id": "",
    "service": "nginx-web-server",
    "operation": "read_home_timeline_client",
    "start_time": "2025-11-04 00:20:00.521783",
    "duration_us": "490",
    "http_status_code": "",
    "http_method": "",
    "http_url": "",
    "component": "",
    "tags": '{"internal.span.format": "proto"}',
    "logs": "",
    "_source": "all_traces.csv",
}


def trace_batch(records: list[dict]) -> RawBatch:
    return RawBatch(
        modality=Modality.TRACE, records=records, sources=["all_traces.csv"], **WINDOW
    )


def test_trace_row_normalized():
    [out] = TraceNormalizer().normalize(trace_batch([TRACE_ROW])).records
    assert out.service == "nginx"
    assert out.trace_id == "00375a1ade701ffa"
    assert out.parent_span_id is None             # 공백 → None
    assert out.http_status_code is None           # 공백 → None
    assert out.duration_us == 490
    assert out.duration_ms == 0.49
    assert out.timestamp == datetime(2025, 11, 4, 0, 20, 0, 521783)
    assert out.tags == {"internal.span.format": "proto"}
    assert out.logs is None                       # 공백 → None


def test_trace_status_code_parsed():
    row = dict(TRACE_ROW, http_status_code="500", parent_span_id="c4c6197d4cc6a67e")
    [out] = TraceNormalizer().normalize(trace_batch([row])).records
    assert out.http_status_code == 500            # trace_5xx 신호 원천
    assert out.parent_span_id == "c4c6197d4cc6a67e"


def test_trace_bad_tags_kept_as_empty_dict():
    row = dict(TRACE_ROW, tags="{broken")
    [out] = TraceNormalizer().normalize(trace_batch([row])).records
    assert out.tags == {}                         # 파싱 실패 → 빈 dict + warning


def test_trace_missing_start_time_skipped():
    row = dict(TRACE_ROW, start_time="")
    out = TraceNormalizer().normalize(trace_batch([row]))
    assert out.records == []                      # N3


def test_window_preserved():
    out = LogNormalizer().normalize(log_batch([], []))
    assert out.modality is Modality.LOG
    assert out.observed_from == WINDOW["observed_from"]
    assert out.observed_until == WINDOW["observed_until"]
