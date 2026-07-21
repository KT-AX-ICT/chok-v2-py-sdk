"""Normalizer 3종 테스트 — 실측 라인/행을 축약한 인라인 픽스처 (ADR-004)."""

from __future__ import annotations

from datetime import datetime

from rca_sdk.config import Settings
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


def roster_of(batch_out):
    return {s.source: (s.present, s.record_count) for s in batch_out.roster}


def test_log_roster_missing_empty_data():
    """Code_Stop 실측: media 파일 자체 없음(missing) · nginx 0바이트(empty) · text 데이터."""
    normalizer = LogNormalizer(expected_services=["media", "nginx", "text"])
    batch = log_batch(
        [{"raw": BOOST_CONNECT, "_source": "TextService_.log"}],
        sources=["TextService_.log", "NginxThrift_.log"],  # media 파일은 관측 안 됨
    )
    roster = roster_of(normalizer.normalize(batch))
    assert roster["media"] == (False, 0)   # missing
    assert roster["nginx"] == (True, 0)    # empty
    assert roster["text"] == (True, 1)     # data


def test_metric_roster_includes_node():
    normalizer = MetricNormalizer(expected_services=["user"])
    rec = {
        "timestamp": "2025-11-04 00:02:21",
        "value": "0.5",
        "container_label_com_docker_compose_service": "user-service",
        "_source": "socialnet_container_cpu.csv",
    }
    batch = metric_batch([rec], ["socialnet_container_cpu.csv", "system_cpu_usage.csv"])
    roster = roster_of(normalizer.normalize(batch))
    assert roster["user"] == (True, 1)
    assert roster["__node__"] == (True, 0)  # expected 에 자동 포함


def test_trace_roster_single_artifact():
    normalizer = TraceNormalizer(expected_services=["nginx", "media"])
    roster = roster_of(normalizer.normalize(trace_batch([TRACE_ROW])))
    assert roster["nginx"] == (True, 1)
    assert roster["media"] == (True, 0)     # 파일은 있으니 empty


def test_trace_roster_missing_when_no_file():
    normalizer = TraceNormalizer(expected_services=["nginx"])
    batch = RawBatch(modality=Modality.TRACE, records=[], sources=[], **WINDOW)
    roster = roster_of(normalizer.normalize(batch))
    assert roster["nginx"] == (False, 0)


def test_settings_default_expected_services():
    settings = Settings()
    assert "media" in settings.expected_services
    assert "nginx" in settings.expected_services
    assert len(settings.expected_services) == 12


def test_boost_line_with_cpp_operator_in_function_name():
    """`operator()` 처럼 함수명에 괄호가 든 줄도 읽어야 한다.

    C++ 람다·펑터는 함수명이 `operator()` 로 찍힌다. func 패턴이 첫 `)` 에서 멈추면
    그 줄이 통째로 버려진다 — 실데이터에서 TextService 400줄이 조용히 사라졌다
    (시나리오 재생 실측, 계획 05 §6).
    """
    line = (
        "[2025-Nov-04 00:03:50.448151] <info>: (TextHandler.h:105:operator()) "
        "ComposeUrls to url-shorten-service succeeded [req_id=32999497]"
    )
    batch = log_batch([{"raw": line, "_source": "TextService_.log"}], ["TextService_.log"])
    [rec] = LogNormalizer().normalize(batch).records
    assert rec.service == "text"
    assert rec.code_loc == "TextHandler.h:105"
    assert rec.level == "info"
    assert rec.message.startswith("ComposeUrls to url-shorten-service")
