"""DatasetReplayCollector — 데이터셋을 30초 배치로 재생하는 하네스 (계획 05 §3).

리플레이어가 하는 일과 같다: **타임스탬프만 파싱**해 30초 구간에 나누고, 원본 줄/행은
그대로 넘긴다. 정규화·roster 판정은 실제 Normalizer 가 한다.

여기 테스트는 하네스 자체의 계약만 본다 — 실데이터 시나리오는 test_scenarios.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from rca_sdk.schemas.events import Modality
from tests.replay.harness import DatasetReplayCollector, line_timestamp

T0 = datetime(2025, 11, 4, 0, 0, 0)


@pytest.fixture
def scenario(tmp_path):
    """모달리티별 디렉토리 3종. 실데이터도 모달리티마다 디렉토리가 따로다."""
    (tmp_path / "log").mkdir()
    (tmp_path / "metric").mkdir()
    (tmp_path / "trace").mkdir()
    (tmp_path / "log" / "MediaService_.log").write_text(
        "[2025-Nov-04 00:00:05.000000] <info>: (MediaService.cpp:44:main) "
        "Starting the media-service server...\n"
        "[2025-Nov-04 00:00:35.000000] <error>: (Media.h:12:x) Could not connect to user:9090\n",
        encoding="utf-8",
    )
    (tmp_path / "metric" / "system_cpu_usage.csv").write_text(
        "timestamp,value,metric,instance\n"
        "2025-11-04 00:00:10,12.5,m,node-exporter:9100\n"
        "2025-11-04 00:00:40,88.0,m,node-exporter:9100\n",
        encoding="utf-8",
    )
    (tmp_path / "trace" / "all_traces.csv").write_text(
        "trace_id,span_id,parent_span_id,service,operation,start_time,duration_us,"
        "http_status_code,http_method,http_url,component,tags,logs\n"
        "a,a,,media-service,/x,2025-11-04 00:00:15.000000,1200,200,GET,u,c,,\n",
        encoding="utf-8",
    )
    return tmp_path


# ── 타임스탬프 추출 ─────────────────────────────────────────────────────────


def test_line_timestamp_parses_boost_format():
    line = "[2025-Nov-04 00:01:57.490560] <info>: (MediaService.cpp:44:main) Starting..."
    assert line_timestamp(line) == datetime(2025, 11, 4, 0, 1, 57, 490560)


def test_line_timestamp_parses_nginx_format():
    line = "2025/11/04 00:03:41 [error] 12#12: connect() failed"
    assert line_timestamp(line) == datetime(2025, 11, 4, 0, 3, 41)


def test_line_timestamp_returns_none_for_continuation_line():
    assert line_timestamp("    at Foo.bar(Foo.java:12)") is None


# ── 30초 버킷팅 ─────────────────────────────────────────────────────────────


def test_poll_yields_only_first_window(scenario):
    collector = DatasetReplayCollector(scenario / "log", Modality.LOG, origin=T0)
    batch = collector.poll()
    assert batch.observed_from == T0
    assert batch.observed_until == T0 + timedelta(seconds=30)
    assert len(batch.records) == 1  # 00:00:05 만, 00:00:35 는 다음 틱


def test_consecutive_polls_advance_window(scenario):
    collector = DatasetReplayCollector(scenario / "log", Modality.LOG, origin=T0)
    collector.poll()
    second = collector.poll()
    assert second.observed_from == T0 + timedelta(seconds=30)
    assert len(second.records) == 1  # 00:00:35


def test_batches_are_contiguous(scenario):
    """배치가 연속(N.until == N+1.from)이라야 coverage 겹침 판정이 성립한다 (계획 04 §4)."""
    collector = DatasetReplayCollector(scenario / "log", Modality.LOG, origin=T0)
    first, second = collector.poll(), collector.poll()
    assert first.observed_until == second.observed_from


def test_empty_window_still_yields_batch(scenario):
    """레코드 0건 배치도 나와야 한다 — empty 판정 재료 (계획 04 §3)."""
    collector = DatasetReplayCollector(scenario / "log", Modality.LOG, origin=T0)
    for _ in range(3):
        batch = collector.poll()
    assert batch.records == []
    assert batch.sources == ["MediaService_.log"]  # 파일은 여전히 존재


# ── 원본 보존 · sources ─────────────────────────────────────────────────────


def test_log_records_keep_raw_line(scenario):
    batch = DatasetReplayCollector(scenario / "log", Modality.LOG, origin=T0).poll()
    assert batch.records[0]["raw"].startswith("[2025-Nov-04 00:00:05.000000]")
    assert batch.records[0]["_source"] == "MediaService_.log"


def test_csv_records_become_column_dicts(scenario):
    batch = DatasetReplayCollector(scenario / "metric", Modality.METRIC, origin=T0).poll()
    assert batch.records[0]["timestamp"] == "2025-11-04 00:00:10"
    assert batch.records[0]["value"] == "12.5"
    assert batch.records[0]["_source"] == "system_cpu_usage.csv"


def test_csv_header_is_not_a_record(scenario):
    collector = DatasetReplayCollector(scenario / "metric", Modality.METRIC, origin=T0)
    rows = [r for _ in range(3) for r in collector.poll().records]
    assert all("timestamp" in r for r in rows)
    assert len(rows) == 2  # 헤더 제외


def test_sources_lists_files_regardless_of_records(scenario):
    batch = DatasetReplayCollector(scenario / "trace", Modality.TRACE, origin=T0).poll()
    assert batch.sources == ["all_traces.csv"]


def test_trace_uses_start_time_column(scenario):
    batch = DatasetReplayCollector(scenario / "trace", Modality.TRACE, origin=T0).poll()
    assert len(batch.records) == 1
    assert batch.records[0]["start_time"] == "2025-11-04 00:00:15.000000"


# ── 재생 종료 ───────────────────────────────────────────────────────────────


def test_exhausted_reports_done(scenario):
    collector = DatasetReplayCollector(scenario / "log", Modality.LOG, origin=T0)
    assert not collector.exhausted
    collector.poll()
    collector.poll()
    assert collector.exhausted  # 마지막 레코드를 낸 뒤


def test_origin_defaults_to_earliest_timestamp(scenario):
    collector = DatasetReplayCollector(scenario / "log", Modality.LOG)
    assert collector.origin == datetime(2025, 11, 4, 0, 0, 5)
