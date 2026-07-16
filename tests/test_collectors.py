"""JsonlTailCollector 단위 테스트 — tmp_path 기반 (fixture 파일 새로 만들지 않음, ADR-004).

계획 02 §① collectors. 리플레이어 실출력 대신 실측 포맷을 축약한 JSONL 로 검증한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rca_sdk.collectors.log import LogCollector
from rca_sdk.collectors.metric import MetricCollector
from rca_sdk.collectors.tail import SourceLayoutError, validate_source_layout
from rca_sdk.collectors.trace import TraceCollector
from rca_sdk.schemas.events import Modality


def make_layout(tmp_path: Path) -> Path:
    """var/ 형 레이아웃(log/metric/trace 하위 디렉터리)을 만든다."""
    for modality in ("log", "metric", "trace"):
        (tmp_path / modality).mkdir()
    return tmp_path


def append_lines(path: Path, objs: list[dict], *, newline_at_end: bool = True) -> None:
    """JSONL append. newline_at_end=False 면 마지막 줄을 개행 없이 남긴다(쓰는 도중 상태)."""
    text = "\n".join(json.dumps(o) for o in objs)
    if newline_at_end:
        text += "\n"
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(text)


def test_empty_dir_returns_empty_batch(tmp_path):
    root = make_layout(tmp_path)
    batch = LogCollector(str(root)).poll()
    assert batch.modality is Modality.LOG
    assert batch.records == []
    assert batch.sources == []


def test_reads_lines_and_tags_source(tmp_path):
    root = make_layout(tmp_path)
    append_lines(root / "log" / "media-service.jsonl", [{"msg": "a"}, {"msg": "b"}])
    batch = LogCollector(str(root)).poll()
    assert len(batch.records) == 2
    assert batch.records[0]["_source"] == "media-service.jsonl"
    assert batch.sources == ["media-service.jsonl"]


def test_offset_continues_between_polls(tmp_path):
    root = make_layout(tmp_path)
    f = root / "log" / "media-service.jsonl"
    collector = LogCollector(str(root))
    append_lines(f, [{"msg": "a"}])
    assert len(collector.poll().records) == 1
    append_lines(f, [{"msg": "b"}, {"msg": "c"}])
    second = collector.poll()
    assert [r["msg"] for r in second.records] == ["b", "c"]  # 신규 줄만


def test_incomplete_last_line_deferred(tmp_path):
    root = make_layout(tmp_path)
    f = root / "log" / "media-service.jsonl"
    collector = LogCollector(str(root))
    append_lines(f, [{"msg": "a"}])
    append_lines(f, [{"msg": "partial"}], newline_at_end=False)  # 쓰는 도중
    first = collector.poll()
    assert [r["msg"] for r in first.records] == ["a"]  # 미완성 줄은 미소비
    with f.open("a", encoding="utf-8", newline="") as fh:
        fh.write("\n")  # 리플레이어가 줄을 완성
    second = collector.poll()
    assert [r["msg"] for r in second.records] == ["partial"]


def test_zero_byte_file_listed_in_sources(tmp_path):
    root = make_layout(tmp_path)
    (root / "log" / "nginx-thrift.jsonl").touch()  # Perf_CPU 실측 — 0바이트 존재
    batch = LogCollector(str(root)).poll()
    assert batch.sources == ["nginx-thrift.jsonl"]
    assert batch.records == []


def test_bad_json_line_skipped(tmp_path):
    root = make_layout(tmp_path)
    f = root / "log" / "media-service.jsonl"
    with f.open("a", encoding="utf-8", newline="") as fh:
        fh.write('{"msg": "ok"}\n{broken\n{"msg": "ok2"}\n')
    batch = LogCollector(str(root)).poll()
    assert [r["msg"] for r in batch.records] == ["ok", "ok2"]  # 깨진 줄만 스킵


def test_truncated_file_reread_from_start(tmp_path):
    root = make_layout(tmp_path)
    f = root / "log" / "media-service.jsonl"
    collector = LogCollector(str(root))
    append_lines(f, [{"msg": "old1"}, {"msg": "old2"}])
    collector.poll()
    f.write_text('{"msg": "fresh"}\n', encoding="utf-8")  # rca-replay --reset 재실행
    batch = collector.poll()
    assert [r["msg"] for r in batch.records] == ["fresh"]


def test_observed_window_is_continuous(tmp_path):
    root = make_layout(tmp_path)
    collector = LogCollector(str(root))
    first = collector.poll()
    second = collector.poll()
    assert first.observed_until == second.observed_from
    assert first.observed_from <= first.observed_until
    assert second.observed_from <= second.observed_until


def test_new_file_appearing_mid_run(tmp_path):
    root = make_layout(tmp_path)
    collector = LogCollector(str(root))
    collector.poll()
    append_lines(root / "log" / "user-service.jsonl", [{"msg": "late"}])
    batch = collector.poll()
    assert batch.sources == ["user-service.jsonl"]
    assert batch.records[0]["msg"] == "late"


@pytest.mark.parametrize(
    ("collector_cls", "modality", "subdir"),
    [
        (LogCollector, Modality.LOG, "log"),
        (MetricCollector, Modality.METRIC, "metric"),
        (TraceCollector, Modality.TRACE, "trace"),
    ],
)
def test_each_collector_owns_its_subdir(tmp_path, collector_cls, modality, subdir):
    root = make_layout(tmp_path)
    append_lines(root / subdir / "media-service.jsonl", [{"v": 1}])
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
    assert str((tmp_path / "metric").resolve()) in msg  # 해석된 절대경로
    assert "CWD" in msg  # 실행 위치 안내 (ADR-004)
