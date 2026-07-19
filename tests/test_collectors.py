"""collectors 단위 테스트 — tmp_path 기반 (fixture 파일 커밋 금지, ADR-004).

계획 03: var/ 는 원본 형식 그대로다 — log 는 텍스트 라인, metric/trace 는 CSV.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rca_sdk.collectors.log import LogCollector
from rca_sdk.collectors.metric import MetricCollector
from rca_sdk.collectors.tail import SourceLayoutError, validate_source_layout
from rca_sdk.collectors.trace import TraceCollector
from rca_sdk.schemas.events import Modality

BOOST_LINE = (
    "[2025-Nov-04 00:01:57.490560] <info>: "
    "(MediaService.cpp:44:main) Starting the media-service server..."
)
METRIC_HEADER = "timestamp,value,metric,container_label_com_docker_compose_service\n"
METRIC_ROW = (
    '2025-11-04 00:02:21,0.006794,'
    '"container_label_com_docker_compose_service=""cadvisor""",cadvisor\n'
)


def make_layout(tmp_path: Path) -> Path:
    """var/ 형 레이아웃(log/metric/trace 하위 디렉터리)을 만든다."""
    for modality in ("log", "metric", "trace"):
        (tmp_path / modality).mkdir()
    return tmp_path


def append_text(path: Path, text: str) -> None:
    """원본 줄 그대로 append (리플레이어 동작 재현). 개행 포함 여부는 호출자가 정한다."""
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(text)


def test_empty_dir_returns_empty_batch(tmp_path):
    root = make_layout(tmp_path)
    batch = LogCollector(str(root)).poll()
    assert batch.modality is Modality.LOG
    assert batch.records == []
    assert batch.sources == []


def test_log_line_wrapped_as_raw(tmp_path):
    root = make_layout(tmp_path)
    append_text(root / "log" / "MediaService_.log", BOOST_LINE + "\n")
    batch = LogCollector(str(root)).poll()
    assert batch.records == [{"raw": BOOST_LINE, "_source": "MediaService_.log"}]
    assert batch.sources == ["MediaService_.log"]


def test_offset_continues_between_polls(tmp_path):
    root = make_layout(tmp_path)
    f = root / "log" / "MediaService_.log"
    collector = LogCollector(str(root))
    append_text(f, "line-a\n")
    assert [r["raw"] for r in collector.poll().records] == ["line-a"]
    append_text(f, "line-b\nline-c\n")
    assert [r["raw"] for r in collector.poll().records] == ["line-b", "line-c"]


def test_incomplete_last_line_deferred(tmp_path):
    root = make_layout(tmp_path)
    f = root / "log" / "MediaService_.log"
    collector = LogCollector(str(root))
    append_text(f, "done\npartial")  # 마지막 줄 개행 없음 = 쓰는 도중
    assert [r["raw"] for r in collector.poll().records] == ["done"]
    append_text(f, "\n")  # 리플레이어가 줄을 완성
    assert [r["raw"] for r in collector.poll().records] == ["partial"]


def test_zero_byte_file_listed_in_sources(tmp_path):
    root = make_layout(tmp_path)
    (root / "log" / "NginxThrift_.log").touch()  # Perf_CPU 실측 — 0바이트 존재
    batch = LogCollector(str(root)).poll()
    assert batch.sources == ["NginxThrift_.log"]
    assert batch.records == []


def test_blank_line_skipped(tmp_path):
    root = make_layout(tmp_path)
    append_text(root / "log" / "MediaService_.log", "a\n\n \nb\n")
    batch = LogCollector(str(root)).poll()
    assert [r["raw"] for r in batch.records] == ["a", "b"]


def test_truncated_file_reread_from_start(tmp_path):
    root = make_layout(tmp_path)
    f = root / "log" / "MediaService_.log"
    collector = LogCollector(str(root))
    append_text(f, "old-1\nold-2\n")
    collector.poll()
    f.write_text("fresh\n", encoding="utf-8")  # rca-replay --reset 재실행
    assert [r["raw"] for r in collector.poll().records] == ["fresh"]


def test_non_log_extension_ignored(tmp_path):
    root = make_layout(tmp_path)
    append_text(root / "log" / "summary.txt", "meta\n")  # 재생 대상 아님
    batch = LogCollector(str(root)).poll()
    assert batch.sources == []
    assert batch.records == []


def test_observed_window_is_continuous(tmp_path):
    root = make_layout(tmp_path)
    collector = LogCollector(str(root))
    first = collector.poll()
    second = collector.poll()
    assert first.observed_until == second.observed_from
    assert first.observed_from <= first.observed_until


def test_new_file_appearing_mid_run(tmp_path):
    root = make_layout(tmp_path)
    collector = LogCollector(str(root))
    collector.poll()
    append_text(root / "log" / "UserService_.log", "late\n")
    batch = collector.poll()
    assert batch.sources == ["UserService_.log"]
    assert batch.records[0]["raw"] == "late"


def test_file_deleted_between_glob_and_read(tmp_path, monkeypatch):
    """나열과 읽기 사이 파일 삭제(--reset 레이스)가 poll 전체를 죽이면 안 된다."""
    root = make_layout(tmp_path)
    f = root / "log" / "MediaService_.log"
    append_text(f, "a\n")
    collector = LogCollector(str(root))
    real_stat = type(f).stat

    def racy_stat(self, *args, **kwargs):
        if self.name == "MediaService_.log":
            raise FileNotFoundError(self)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(type(f), "stat", racy_stat)
    batch = collector.poll()  # 예외 없이 완료
    assert batch.records == []
    assert batch.sources == []


def test_first_poll_window_starts_at_creation(tmp_path):
    import time

    root = make_layout(tmp_path)
    collector = LogCollector(str(root))
    time.sleep(0.02)
    batch = collector.poll()
    assert batch.observed_from < batch.observed_until


def test_csv_header_consumed_and_rows_dicted(tmp_path):
    root = make_layout(tmp_path)
    append_text(root / "metric" / "socialnet_container_cpu.csv", METRIC_HEADER + METRIC_ROW)
    batch = MetricCollector(str(root)).poll()
    assert len(batch.records) == 1  # 헤더는 레코드가 아님
    rec = batch.records[0]
    assert rec["timestamp"] == "2025-11-04 00:02:21"
    assert rec["value"] == "0.006794"
    assert rec["container_label_com_docker_compose_service"] == "cadvisor"
    assert rec["_source"] == "socialnet_container_cpu.csv"


def test_csv_header_remembered_across_polls(tmp_path):
    root = make_layout(tmp_path)
    f = root / "metric" / "socialnet_container_cpu.csv"
    collector = MetricCollector(str(root))
    append_text(f, METRIC_HEADER + METRIC_ROW)
    assert len(collector.poll().records) == 1
    append_text(f, METRIC_ROW)  # 두 번째 배치에는 헤더가 없다
    second = collector.poll()
    assert len(second.records) == 1
    assert second.records[0]["timestamp"] == "2025-11-04 00:02:21"


def test_csv_header_only_file_is_empty_source(tmp_path):
    root = make_layout(tmp_path)
    append_text(root / "metric" / "system_cpu_usage.csv", "timestamp,value,metric,instance\n")
    batch = MetricCollector(str(root)).poll()
    assert batch.sources == ["system_cpu_usage.csv"]
    assert batch.records == []  # empty 판정 재료


def test_csv_quoted_comma_field(tmp_path):
    root = make_layout(tmp_path)
    header = "trace_id,service,tags\n"
    row = 'abc,nginx-web-server,"{""a"": 1, ""b"": 2}"\n'  # 인용 필드 안 콤마
    append_text(root / "trace" / "all_traces.csv", header + row)
    batch = TraceCollector(str(root)).poll()
    assert batch.records[0]["tags"] == '{"a": 1, "b": 2}'


def test_csv_column_mismatch_skipped(tmp_path):
    root = make_layout(tmp_path)
    append_text(
        root / "metric" / "system_cpu_usage.csv",
        "timestamp,value,metric,instance\n1,2\n"
        + "2025-11-04 00:02:28,2.27,m,node-exporter:9100\n",
    )
    batch = MetricCollector(str(root)).poll()
    assert len(batch.records) == 1  # 컬럼 수 불일치 줄만 스킵
    assert batch.records[0]["value"] == "2.27"


def test_csv_truncate_relearns_header(tmp_path):
    root = make_layout(tmp_path)
    f = root / "metric" / "system_cpu_usage.csv"
    collector = MetricCollector(str(root))
    append_text(f, "timestamp,value,metric,instance\n2025-11-04 00:02:28,2.27,m,n\n")
    collector.poll()
    f.write_text("ts,v\n1,2\n", encoding="utf-8")  # --reset 후 다른 헤더
    batch = collector.poll()
    assert batch.records == [{"ts": "1", "v": "2", "_source": "system_cpu_usage.csv"}]


@pytest.mark.parametrize(
    ("collector_cls", "modality", "subdir", "content"),
    [
        (LogCollector, Modality.LOG, "log", BOOST_LINE + "\n"),
        (MetricCollector, Modality.METRIC, "metric", METRIC_HEADER + METRIC_ROW),
        (TraceCollector, Modality.TRACE, "trace", METRIC_HEADER + METRIC_ROW),
    ],
)
def test_each_collector_owns_its_subdir(tmp_path, collector_cls, modality, subdir, content):
    root = make_layout(tmp_path)
    name = "sample.log" if subdir == "log" else "sample.csv"
    append_text(root / subdir / name, content)
    batch = collector_cls(str(root)).poll()
    assert batch.modality is modality
    assert len(batch.records) == 1


def test_validate_source_layout_ok(tmp_path):
    validate_source_layout(str(make_layout(tmp_path)))  # 예외 없음


def test_validate_source_layout_missing_dir_raises_with_paths(tmp_path):
    (tmp_path / "log").mkdir()  # metric/trace 부재
    with pytest.raises(SourceLayoutError) as exc:
        validate_source_layout(str(tmp_path))
    msg = str(exc.value)
    assert str((tmp_path / "metric").resolve()) in msg
    assert "CWD" in msg
