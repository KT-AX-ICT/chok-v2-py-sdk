"""Normalizer 3종 테스트 — 실측 라인/행을 축약한 인라인 픽스처 (ADR-004)."""

from __future__ import annotations

from datetime import datetime

from rca_sdk.normalization.log import LogNormalizer
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


def test_window_preserved():
    out = LogNormalizer().normalize(log_batch([], []))
    assert out.modality is Modality.LOG
    assert out.observed_from == WINDOW["observed_from"]
    assert out.observed_until == WINDOW["observed_until"]
