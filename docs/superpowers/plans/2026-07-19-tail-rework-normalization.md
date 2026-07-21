# 원본 형식 tail 개편 · normalization 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 계획 03(docs/plans/03-tail-rework-normalization.md)에 따라 collectors 를 원본 형식(텍스트 라인/CSV) tail 로 개편하고 normalization 3종 + roster 를 구현한다.

**Architecture:** `LineTailCollector`(byte offset tail 공통) + `_frame` 훅으로 log(raw)/CSV(컬럼 dict) 분기. Normalizer 3종이 라인/컬럼을 스키마로 변환하고 expected_services 대조로 roster 산출.

**Tech Stack:** Python 3.11 · pydantic v2 · pytest(tmp_path) · uv · ruff==0.15.21

## Global Constraints

- docstring·주석·커밋 메시지는 한국어 (repo 관례)
- 모든 시각은 naive `datetime` — tz 는 변환 없이 버린다 (계획 02 C6)
- 테스트 fixture 파일 커밋 금지 — tmp_path 에 즉석 생성 (ADR-004)
- 레코드 단위 파싱 실패는 skip + `logging.warning` (계획 03 N3)
- `src/rca_sdk/collectors/tail.py` 의 사용자 학습 주석(`#poll에서 새롭게 읽은 데이터` 등)은 해당 줄이 살아남는 한 유지
- 커밋 trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 실행 명령은 항상 `uv run pytest …` / `uv run ruff check .`

---

### Task 1: 정규화 스키마 필드 개명 `canonical_service` → `service` (N4)

**Files:**
- Modify: `src/rca_sdk/schemas/events.py:33,46,62`
- Modify: `tests/test_smoke.py:42-61`
- Modify: `examples/basic_sdk/main.py:41,44`

**Interfaces:**
- Produces: `NormalizedLog.service`, `NormalizedTrace.service`, `NormalizedMetric.service` (`str | None`) — Task 5~8 이 이 이름을 사용

- [ ] **Step 1: 스키마 3곳 개명** — `src/rca_sdk/schemas/events.py` 에서 `canonical_service:` 필드 3개를 `service:` 로 바꾼다 (주석은 유지). `SourceStatus.source` 의 주석 `# artifact / canonical_service` 는 `# canonical 서비스명 (계획 03 N2)` 로 갱신.

- [ ] **Step 2: 참조 지점 갱신** — `tests/test_smoke.py` 의 `canonical_service=` 5곳·`.canonical_service` 1곳, `examples/basic_sdk/main.py` 의 2곳을 `service` 로 바꾼다.

- [ ] **Step 3: 전체 테스트 통과 확인**

Run: `uv run pytest`
Expected: 26 passed

- [ ] **Step 4: Commit**

```bash
git add src/rca_sdk/schemas/events.py tests/test_smoke.py examples/basic_sdk/main.py
git commit -m "refactor(schemas): 정규화 필드 canonical_service → service 통일 (계획 03 N4)"
```

---

### Task 2: LineTailCollector 개편 + LogCollector raw 프레이밍

**Files:**
- Modify: `src/rca_sdk/collectors/tail.py` (JsonlTailCollector → LineTailCollector)
- Modify: `src/rca_sdk/collectors/log.py`
- Modify: `src/rca_sdk/collectors/__init__.py`
- Rewrite: `tests/test_collectors.py` (log 계열 — CSV 는 Task 3)

**Interfaces:**
- Produces: `LineTailCollector(source_root: str)` — 클래스 속성 `pattern: str`(glob), 훅 `_frame(line: str, path: Path) -> dict[str, Any] | None`(None=레코드 아님), 훅 `_reset_file_state(name: str) -> None`(truncate 시). `LogCollector` 레코드 = `{"raw": 라인, "_source": 파일명}`.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_collectors.py` 를 아래로 전면 교체 (metric/trace import 는 Task 3 에서 추가):

```python
"""collectors 단위 테스트 — tmp_path 기반 (fixture 파일 커밋 금지, ADR-004).

계획 03: var/ 는 원본 형식 그대로다 — log 는 텍스트 라인, metric/trace 는 CSV.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rca_sdk.collectors.log import LogCollector
from rca_sdk.collectors.tail import SourceLayoutError, validate_source_layout
from rca_sdk.schemas.events import Modality

BOOST_LINE = (
    "[2025-Nov-04 00:01:57.490560] <info>: "
    "(MediaService.cpp:44:main) Starting the media-service server..."
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


def test_validate_source_layout_ok(tmp_path):
    validate_source_layout(str(make_layout(tmp_path)))  # 예외 없음


def test_validate_source_layout_missing_dir_raises_with_paths(tmp_path):
    (tmp_path / "log").mkdir()  # metric/trace 부재
    with pytest.raises(SourceLayoutError) as exc:
        validate_source_layout(str(tmp_path))
    msg = str(exc.value)
    assert str((tmp_path / "metric").resolve()) in msg
    assert "CWD" in msg
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_collectors.py -q`
Expected: FAIL — `LogCollector` 는 아직 `*.jsonl` glob + json.loads 라서 `test_log_line_wrapped_as_raw` 등이 실패

- [ ] **Step 3: tail.py 개편** — `src/rca_sdk/collectors/tail.py` 를 아래로 교체 (docstring·사용자 주석 유지, `json` import 제거):

```python
"""라인 tailer 공통 구현 — 파일별 byte offset 을 기억하고 신규 완성 라인만 읽는다.

계획 03 §1. var/ 는 원본 형식 그대로(log 텍스트 라인·CSV)이므로 라인 해석은
서브클래스 훅 `_frame` 이 담당한다. 소스 present/missing 판정은 normalizer 전담 —
여기서는 관측 사실(sources)만 전달한다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from rca_sdk.collectors.base import Collector
from rca_sdk.schemas.events import RawBatch

logger = logging.getLogger(__name__)

MODALITY_SUBDIRS = ("log", "metric", "trace")


class SourceLayoutError(RuntimeError):
    """source_root 레이아웃 오류 — 설정 오류를 '이상 없음(0건)'과 구분한다 (ADR-004)."""


def validate_source_layout(source_root: str) -> None:
    """source_root 와 모달리티 하위 디렉터리 존재를 검증한다 (기동 시 1회, 호출은 Runner 소관)."""
    root = Path(source_root).resolve()
    missing = [p for p in (root, *(root / m for m in MODALITY_SUBDIRS)) if not p.is_dir()]
    if missing:
        paths = ", ".join(str(p) for p in missing)
        raise SourceLayoutError(
            f"원천 디렉터리 부재: {paths} (CWD={Path.cwd()}) — 저장소 루트에서 실행했는지 확인"
        )


class LineTailCollector(Collector):
    """`<source_root>/<modality>/<pattern>` 을 tail 해 신규 완성 라인을 RawBatch 로 산출한다."""

    pattern = "*"  # 서브클래스가 모달리티별 glob 지정 (*.log / *.csv)

    def __init__(self, source_root: str) -> None:
        self.source_root = source_root
        self._dir = Path(source_root) / self.modality.value
        self._offsets: dict[str, int] = {}  # 파일명 → 소비한 byte 수 (인메모리, 계획 02 C1)
        self._last_poll_at = datetime.now()  # 첫 poll 의 관측 하한 = 생성 시각 (폭 0 구간 방지)

    def poll(self) -> RawBatch:
        now = datetime.now()  # naive (계획 02 C6)
        records: list[dict[str, Any]] = []  # poll에서 새롭게 읽은 데이터
        sources: list[str] = []  # 현재 디렉토리에 존재하는 파일 목록
        # 현재 디렉토리에서 pattern 에 맞는 파일을 순회하며 새롭게 추가된 라인을 읽어온다
        for path in sorted(self._dir.glob(self.pattern)):
            try:
                new_records = self._read_new_lines(path)
            except OSError:
                # 나열과 읽기 사이 파일 소실(--reset 레이스) 등 — 이 파일만 이번 poll 제외
                logger.warning("%s: 읽기 실패 — 이번 poll 관측에서 제외", path.name)
                continue
            sources.append(path.name)  # 신규 데이터가 0 건이어도 source에는 포함
            records.extend(new_records)
        batch = RawBatch(
            modality=self.modality,
            observed_from=self._last_poll_at,  # 직전 poll 시각 (첫 poll 은 생성 시각)
            observed_until=now,
            records=records,
            sources=sources,
        )
        self._last_poll_at = now
        return batch

    def _frame(self, line: str, path: Path) -> dict[str, Any] | None:
        """완성 라인 1개 → 레코드 dict. None 이면 레코드 아님(헤더·스킵). 서브클래스가 구현."""
        raise NotImplementedError

    def _reset_file_state(self, name: str) -> None:
        """truncate(--reset 재실행) 감지 시 파일별 부가 상태 초기화 훅 (기본 없음)."""

    def _read_new_lines(self, path: Path) -> list[dict[str, Any]]:
        offset = self._offsets.get(path.name, 0)
        # 현재 파일 크기 < 내가 기억하는 offset
        if path.stat().st_size < offset:
            offset = 0  # 파일이 줄어듦 = 리플레이어 --reset 재실행 → 처음부터
            self._reset_file_state(path.name)
        with path.open("rb") as f:  # read binary 모드로 열어 offset 위치부터 읽는다.
            f.seek(offset)
            chunk = f.read()
        incomplete = chunk.rpartition(b"\n")[2]
        if incomplete:  # 개행 없는 마지막 조각 = 쓰는 도중 → 다음 poll 로 미룸
            chunk = chunk[: -len(incomplete)]
        records: list[dict[str, Any]] = []
        for line_bytes in chunk.splitlines():
            if not line_bytes.strip():
                continue
            try:
                line = line_bytes.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning("%s: UTF-8 해석 실패 줄 스킵 (계획 03 N3)", path.name)
                continue
            rec = self._frame(line, path)
            if rec is None:
                continue
            rec["_source"] = path.name
            records.append(rec)
        self._offsets[path.name] = offset + len(chunk)
        return records
```

- [ ] **Step 4: log.py 교체** — `src/rca_sdk/collectors/log.py`:

```python
"""로그 tailer — `<source_root>/log/*.log` 원본 라인을 {"raw": 라인} 으로 산출한다 (계획 03 N1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rca_sdk.collectors.tail import LineTailCollector
from rca_sdk.schemas.events import Modality


class LogCollector(LineTailCollector):
    modality = Modality.LOG
    pattern = "*.log"

    def _frame(self, line: str, path: Path) -> dict[str, Any] | None:
        return {"raw": line}  # boost/nginx 해석은 normalizer 소관
```

- [ ] **Step 5: `__init__.py` 갱신** — `JsonlTailCollector` 를 `LineTailCollector` 로 교체 (import·`__all__` 양쪽). metric/trace 는 아직 Task 3 전이므로 임시로 기존 import 유지가 깨지면 metric.py/trace.py 의 부모를 `LineTailCollector` + `pattern = "*.csv"` + `_frame` 미구현(추상) 상태로 두지 말고, **Task 3 까지는 metric.py/trace.py 를 `LineTailCollector` 상속 + `_frame` 이 `{"raw": line}` 인 임시 구현으로 유지**한다 (Task 3 에서 교체).

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest tests/test_collectors.py -q`
Expected: 14 passed

- [ ] **Step 7: 전체 스위트·린트**

Run: `uv run pytest -q; uv run ruff check .`
Expected: all passed, no lint errors

- [ ] **Step 8: Commit**

```bash
git add src/rca_sdk/collectors tests/test_collectors.py
git commit -m "refactor(collectors): 원본 라인 tail 로 개편 — LineTailCollector + LogCollector raw 프레이밍 (계획 03 §1)"
```

---

### Task 3: CsvTailCollector — 헤더 기억 + 컬럼 dict 프레이밍

**Files:**
- Modify: `src/rca_sdk/collectors/tail.py` (CsvTailCollector 추가)
- Modify: `src/rca_sdk/collectors/metric.py`, `src/rca_sdk/collectors/trace.py`
- Modify: `src/rca_sdk/collectors/__init__.py`
- Modify: `tests/test_collectors.py` (CSV 테스트 추가)

**Interfaces:**
- Consumes: `LineTailCollector`(`_frame`/`_reset_file_state` 훅, Task 2)
- Produces: `CsvTailCollector` — 레코드 = `{컬럼명: 값(str), "_source": 파일명}`, 헤더 라인은 레코드 아님. `MetricCollector`/`TraceCollector` 는 `pattern = "*.csv"`.

- [ ] **Step 1: 실패 테스트 추가** — `tests/test_collectors.py` 에 append (import 에 `MetricCollector`, `TraceCollector` 추가):

```python
from rca_sdk.collectors.metric import MetricCollector
from rca_sdk.collectors.trace import TraceCollector

METRIC_HEADER = "timestamp,value,metric,container_label_com_docker_compose_service\n"
METRIC_ROW = '2025-11-04 00:02:21,0.006794,"container_label_com_docker_compose_service=""cadvisor""",cadvisor\n'


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
        "timestamp,value,metric,instance\n1,2\n" + "2025-11-04 00:02:28,2.27,m,node-exporter:9100\n",
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_collectors.py -q`
Expected: 새 CSV 테스트들 FAIL (metric/trace 가 아직 raw 프레이밍)

- [ ] **Step 3: CsvTailCollector 구현** — `src/rca_sdk/collectors/tail.py` 에 추가 (파일 상단에 `import csv` 추가):

```python
class CsvTailCollector(LineTailCollector):
    """CSV tail — 파일 맨 앞 헤더를 기억해 각 행을 {컬럼명: 값} dict 로 프레이밍한다 (계획 03 N1).

    헤더는 offset 이어읽기 특성상 첫 배치에만 나타나므로, 상태를 가진 collector 가
    기억해야 한다 (무상태 normalizer 는 볼 수 없다).
    """

    pattern = "*.csv"

    def __init__(self, source_root: str) -> None:
        super().__init__(source_root)
        self._headers: dict[str, list[str]] = {}  # 파일명 → 컬럼 목록

    def _reset_file_state(self, name: str) -> None:
        self._headers.pop(name, None)  # truncate 후 새 헤더를 다시 학습

    def _frame(self, line: str, path: Path) -> dict[str, Any] | None:
        row = next(csv.reader([line]))  # 인용 콤마 안전 (1레코드=1줄 전제, 계획 03 §1)
        header = self._headers.get(path.name)
        if header is None:
            self._headers[path.name] = row  # 파일 맨 앞 1회 — 레코드 아님
            return None
        if len(row) != len(header):
            logger.warning("%s: 컬럼 수 불일치 줄 스킵 (계획 03 N3)", path.name)
            return None
        return dict(zip(header, row, strict=True))
```

- [ ] **Step 4: metric.py / trace.py 교체**:

```python
# src/rca_sdk/collectors/metric.py
"""메트릭 tailer — `<source_root>/metric/*.csv` 행을 컬럼 dict 로 산출한다 (계획 03 N1)."""

from __future__ import annotations

from rca_sdk.collectors.tail import CsvTailCollector
from rca_sdk.schemas.events import Modality


class MetricCollector(CsvTailCollector):
    modality = Modality.METRIC
```

```python
# src/rca_sdk/collectors/trace.py
"""트레이스 tailer — `<source_root>/trace/all_traces.csv` 행을 컬럼 dict 로 산출한다 (계획 03 N1)."""

from __future__ import annotations

from rca_sdk.collectors.tail import CsvTailCollector
from rca_sdk.schemas.events import Modality


class TraceCollector(CsvTailCollector):
    modality = Modality.TRACE
```

`src/rca_sdk/collectors/__init__.py` 의 export 에 `CsvTailCollector` 추가.

- [ ] **Step 5: 통과·전체 확인**

Run: `uv run pytest -q; uv run ruff check .`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add src/rca_sdk/collectors tests/test_collectors.py
git commit -m "feat(collectors): CSV tail — 파일별 헤더 기억 + 컬럼 dict 프레이밍 (계획 03 §1)"
```

---

### Task 4: normalization common — canonical_service · parse_timestamp

**Files:**
- Modify: `src/rca_sdk/normalization/common.py`
- Create: `tests/test_normalization_common.py`

**Interfaces:**
- Produces: `canonical_service(name: str | None) -> str | None`, `parse_timestamp(value: Any) -> datetime`(naive). Task 5~7 이 사용.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_normalization_common.py`:

```python
"""정규화 공용 헬퍼 테스트 — 스펙 §1-1(서비스명)·§1-2(시간) + 계획 02 C6(naive)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rca_sdk.normalization.common import canonical_service, parse_timestamp


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("UserService", "user"),
        ("user-service", "user"),
        ("SocialGraphService", "socialgraph"),
        ("social-graph-service", "socialgraph"),
        ("NginxThrift", "nginx"),
        ("nginx-thrift", "nginx"),
        ("nginx-web-server", "nginx"),
        ("media-service", "media"),
        ("MediaService_", "media"),          # 로그 파일명 stem
        ("text-service", "text"),
        ("unique-id-service", "uniqueid"),
        ("url-shorten-service", "urlshorten"),
        ("user-mention-service", "usermention"),
        ("user-timeline-service", "usertimeline"),
        ("home-timeline-service", "hometimeline"),
        ("post-storage-service", "poststorage"),
        ("compose-post-service", "composepost"),
        # 인프라는 특수문자만 제거하고 유지 (§1-1)
        ("user-mongodb", "usermongodb"),
        ("social-graph-mongodb", "socialgraphmongodb"),
        ("url-shorten-memcached", "urlshortenmemcached"),
    ],
)
def test_canonical_service_table(raw, expected):
    assert canonical_service(raw) == expected


def test_canonical_service_none():
    assert canonical_service(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2025-Nov-04 00:01:57.490560", datetime(2025, 11, 4, 0, 1, 57, 490560)),  # boost 마이크로초
        ("2025-Nov-04 00:01:57", datetime(2025, 11, 4, 0, 1, 57)),                 # boost 초 단위
        ("2025/11/04 02:58:25", datetime(2025, 11, 4, 2, 58, 25)),                 # nginx
        ("2025-11-04 00:02:21", datetime(2025, 11, 4, 0, 2, 21)),                  # metric CSV
        ("2025-11-04 00:20:00.521000", datetime(2025, 11, 4, 0, 20, 0, 521000)),   # trace CSV
    ],
)
def test_parse_timestamp_formats(raw, expected):
    parsed = parse_timestamp(raw)
    assert parsed == expected
    assert parsed.tzinfo is None  # naive 보장 (C6)


def test_parse_timestamp_drops_tz_without_conversion():
    parsed = parse_timestamp("2025-11-04T00:02:21+09:00")
    assert parsed == datetime(2025, 11, 4, 0, 2, 21)  # 변환 없이 버림
    assert parsed.tzinfo is None


def test_parse_timestamp_aware_datetime_becomes_naive():
    aware = datetime(2025, 11, 4, 1, 2, 3, tzinfo=UTC)
    assert parse_timestamp(aware) == datetime(2025, 11, 4, 1, 2, 3)


def test_parse_timestamp_garbage_raises():
    with pytest.raises(ValueError):
        parse_timestamp("not-a-time")
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_normalization_common.py -q`
Expected: FAIL — `canonical_service` 는 NotImplementedError, boost/nginx 포맷은 fromisoformat 불가

- [ ] **Step 3: common.py 구현** — `src/rca_sdk/normalization/common.py` 를 교체:

```python
"""정규화 공용 헬퍼 (타임스탬프 파싱, 서비스명 정규화).

canonical_service 규칙은 정규화 스펙 §1-1, 시간 통일은 §1-2 + 계획 02 C6 (naive).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# nginx alias (정규화 스펙 §1-1)
ALIASES = {"nginxwebserver": "nginx", "nginxthrift": "nginx"}

# 인프라(DB/캐시)는 본체 서비스 장애와 구분하기 위해 접미사 제거 없이 유지한다 (§1-1)
INFRA_KEYWORDS = ("mongodb", "redis", "memcached", "rabbitmq")

# boost 영문 월 → 숫자 (strptime %b 는 로케일 의존이라 쓰지 않는다)
_MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}
_BOOST_DATE_RE = re.compile(r"^(\d{4})-([A-Z][a-z]{2})-(\d{2}) (.+)$")
_NGINX_DATE_RE = re.compile(r"^(\d{4})/(\d{2})/(\d{2}) (.+)$")


def canonical_service(name: str | None) -> str | None:
    """서비스명을 canonical 형으로 정규화한다 (§1-1).

    소문자화 → 특수문자 제거 → 인프라 키워드 포함 시 정지 → `service` 접미사 제거 → ALIASES.
    """
    if not name:
        return None
    cleaned = re.sub(r"[^a-z0-9]", "", name.lower())
    if any(keyword in cleaned for keyword in INFRA_KEYWORDS):
        return cleaned
    cleaned = cleaned.removesuffix("service")
    return ALIASES.get(cleaned, cleaned)


def parse_timestamp(value: Any) -> datetime:
    """원본 타임스탬프 표현 3계열(boost 영문월·nginx·ISO 공백형)을 naive datetime 으로 변환한다.

    tz 정보가 들어오면 변환 없이 버린다 (계획 02 C6). 실패 시 ValueError/TypeError.
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value))
    if isinstance(value, str):
        text = value.strip()
        boost = _BOOST_DATE_RE.match(text)
        if boost:
            year, month_name, day, rest = boost.groups()
            month = _MONTHS.get(month_name)
            if month is None:
                raise ValueError(f"알 수 없는 월 표기: {value!r}")
            text = f"{year}-{month}-{day} {rest}"
        else:
            nginx = _NGINX_DATE_RE.match(text)
            if nginx:
                year, month, day, rest = nginx.groups()
                text = f"{year}-{month}-{day} {rest}"
        return datetime.fromisoformat(text).replace(tzinfo=None)
    raise TypeError(f"지원하지 않는 timestamp 타입: {type(value)!r}")
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_normalization_common.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/rca_sdk/normalization/common.py tests/test_normalization_common.py
git commit -m "feat(normalization): canonical_service·parse_timestamp 구현 (스펙 §1-1·§1-2, C6)"
```

---

### Task 5: LogNormalizer — boost/nginx 라인 파싱 + 파생 필드

**Files:**
- Modify: `src/rca_sdk/normalization/log.py`
- Create: `tests/test_normalizers.py`

**Interfaces:**
- Consumes: `canonical_service`/`parse_timestamp`(Task 4), `NormalizedLog.service`(Task 1), collector 레코드 `{"raw": 라인, "_source": 파일명}`(Task 2)
- Produces: `LogNormalizer().normalize(batch: RawBatch) -> NormalizedBatch` — roster 는 Task 8 에서 채움(그 전까지 빈 리스트)

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_normalizers.py` 생성:

```python
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
    batch = log_batch([{"raw": BOOST_STARTING, "_source": "MediaService_.log"}], ["MediaService_.log"])
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
    batch = log_batch([{"raw": NGINX_RESOLVE, "_source": "NginxThrift_.log"}], ["NginxThrift_.log"])
    [rec] = LogNormalizer().normalize(batch).records
    assert rec.service == "nginx"
    assert rec.log_type == "nginx_log"
    assert rec.level == "error"
    assert rec.code_loc == "compose.lua:62"
    assert rec.timestamp == datetime(2025, 11, 4, 2, 58, 25)
    assert rec.event_type == "connection_error"
    assert rec.target_service is None             # 익명 — Code_Stop 신호 그대로 보존


def test_connect_target_extracted():
    batch = log_batch([{"raw": BOOST_CONNECT, "_source": "TextService_.log"}], ["TextService_.log"])
    [rec] = LogNormalizer().normalize(batch).records
    assert rec.event_type == "connection_error"
    assert rec.target_service == "media"


def test_unparseable_line_skipped():
    batch = log_batch(
        [{"raw": "no timestamp here", "_source": "UserService_.log"},
         {"raw": BOOST_STARTING, "_source": "MediaService_.log"}],
        ["UserService_.log", "MediaService_.log"],
    )
    out = LogNormalizer().normalize(batch)
    assert len(out.records) == 1  # 해석 불가 줄만 스킵 (N3)


def test_window_preserved():
    out = LogNormalizer().normalize(log_batch([], []))
    assert out.modality is Modality.LOG
    assert out.observed_from == WINDOW["observed_from"]
    assert out.observed_until == WINDOW["observed_until"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_normalizers.py -q`
Expected: FAIL — LogNormalizer.normalize 는 NotImplementedError

- [ ] **Step 3: log.py 구현** — `src/rca_sdk/normalization/log.py` 교체:

```python
"""로그 정규화 — {"raw": 원본 라인} → NormalizedLog (정규화 스펙 §3, 계획 03 §2)."""

from __future__ import annotations

import logging
import re
from typing import Any

from rca_sdk.normalization.base import Normalizer
from rca_sdk.normalization.common import canonical_service, parse_timestamp
from rca_sdk.schemas.events import NormalizedBatch, NormalizedLog, RawBatch

logger = logging.getLogger(__name__)

# boost: [ts] <level>: (file:line:func) message
_BOOST_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\] <(?P<level>\w+)>: "
    r"\((?P<file>[^:()]+):(?P<line>\d+):(?P<func>[^)]*)\) (?P<msg>.*)$"
)
# nginx: YYYY/MM/DD HH:MM:SS [level] message
_NGINX_RE = re.compile(
    r"^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) \[(?P<level>\w+)\] (?P<msg>.*)$"
)
_LUA_LOC_RE = re.compile(r"([\w.]+\.lua:\d+)")
_CONNECT_TARGET_RE = re.compile(r"Could not connect to ([A-Za-z0-9-]+):\d+")
# 익명 resolve-host 는 target 없음 그대로 둔다 — Code_Stop 신호 (ADR-003)
_CONNECTION_ERROR_MARKERS = ("Could not resolve host", "Could not connect", "TTransportException")


class LogNormalizer(Normalizer):
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        records = []
        for rec in batch.records:
            normalized = self._normalize_record(rec)
            if normalized is not None:
                records.append(normalized)
        return NormalizedBatch(
            modality=batch.modality,
            observed_from=batch.observed_from,
            observed_until=batch.observed_until,
            records=records,
        )

    def _normalize_record(self, rec: dict[str, Any]) -> NormalizedLog | None:
        raw = rec.get("raw", "")
        source = rec.get("_source", "")
        service = canonical_service(source.removesuffix(".log"))
        match = _BOOST_RE.match(raw)
        if match:
            code_loc = f"{match['file']}:{match['line']}"
        else:
            match = _NGINX_RE.match(raw)
            if match is None:
                logger.warning("%s: 해석 불가 로그 줄 스킵 (계획 03 N3)", source)
                return None
            lua = _LUA_LOC_RE.search(match["msg"])
            code_loc = lua.group(1) if lua else None
        message = match["msg"]
        try:
            timestamp = parse_timestamp(match["ts"])
        except (ValueError, TypeError):
            logger.warning("%s: timestamp 해석 실패 줄 스킵 (계획 03 N3)", source)
            return None
        if message.startswith("Starting"):
            event_type = "service_start"  # restart_marker 원천 (trigger-policy)
        elif any(marker in message for marker in _CONNECTION_ERROR_MARKERS):
            event_type = "connection_error"
        else:
            event_type = "normal_log"
        target = _CONNECT_TARGET_RE.search(message)
        return NormalizedLog(
            timestamp=timestamp,
            service=service,
            log_type="nginx_log" if service == "nginx" else "service_log",
            level=match["level"],
            code_loc=code_loc,
            message=message,
            target_service=canonical_service(target.group(1)) if target else None,
            event_type=event_type,
        )
```

- [ ] **Step 4: 통과·전체 확인**

Run: `uv run pytest -q; uv run ruff check .`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/rca_sdk/normalization/log.py tests/test_normalizers.py
git commit -m "feat(normalization): LogNormalizer — boost/nginx 파싱 + event_type·target 파생 (스펙 §3)"
```

---

### Task 6: MetricNormalizer

**Files:**
- Modify: `src/rca_sdk/normalization/metric.py`
- Modify: `tests/test_normalizers.py` (추가)

**Interfaces:**
- Consumes: collector 레코드 `{컬럼명: 값(str), "_source": 파일명}`(Task 3), Task 4 헬퍼
- Produces: `MetricNormalizer().normalize(batch) -> NormalizedBatch` — `service="__node__"`(system_*), unit 테이블

- [ ] **Step 1: 실패 테스트 추가** — `tests/test_normalizers.py` 에 append:

```python
from rca_sdk.normalization.metric import MetricNormalizer


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
    [out] = MetricNormalizer().normalize(
        metric_batch([rec], ["socialnet_container_cpu.csv"])
    ).records
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_normalizers.py -q`
Expected: 새 metric 테스트 FAIL (NotImplementedError)

- [ ] **Step 3: metric.py 구현**:

```python
"""메트릭 정규화 — CSV 컬럼 dict → NormalizedMetric (정규화 스펙 §5, 계획 03 §2)."""

from __future__ import annotations

import logging
from typing import Any

from rca_sdk.normalization.base import Normalizer
from rca_sdk.normalization.common import canonical_service, parse_timestamp
from rca_sdk.schemas.events import NormalizedBatch, NormalizedMetric, RawBatch

logger = logging.getLogger(__name__)

NODE_SERVICE = "__node__"
_CONTAINER_DIM = "container_label_com_docker_compose_service"
# metric_name → 단위 (미정의는 None)
_UNITS = {"container_cpu": "fraction", "system_cpu_usage": "percent"}


class MetricNormalizer(Normalizer):
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        records = []
        for rec in batch.records:
            normalized = self._normalize_record(rec)
            if normalized is not None:
                records.append(normalized)
        return NormalizedBatch(
            modality=batch.modality,
            observed_from=batch.observed_from,
            observed_until=batch.observed_until,
            records=records,
        )

    def _normalize_record(self, rec: dict[str, Any]) -> NormalizedMetric | None:
        source = rec.get("_source", "")
        metric_name = source.rsplit(".", 1)[0].removeprefix("socialnet_")
        if _CONTAINER_DIM in rec:
            dimension = rec[_CONTAINER_DIM]
            service = canonical_service(dimension)
        elif "instance" in rec:
            dimension = rec["instance"]
            service = NODE_SERVICE  # 노드 지표 (§5) — cpu_spike 신호 원천
        else:
            dimension = None
            service = None
        try:
            return NormalizedMetric(
                timestamp=parse_timestamp(rec["timestamp"]),
                service=service,
                metric_name=metric_name,
                value=float(rec["value"]),
                dimension=dimension,
                unit=_UNITS.get(metric_name),
            )
        except (KeyError, ValueError, TypeError):
            logger.warning("%s: metric 행 해석 실패 스킵 (계획 03 N3)", source)
            return None
```

- [ ] **Step 4: 통과·전체 확인**

Run: `uv run pytest -q; uv run ruff check .`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/rca_sdk/normalization/metric.py tests/test_normalizers.py
git commit -m "feat(normalization): MetricNormalizer — container/__node__ 구분 + unit 테이블 (스펙 §5)"
```

---

### Task 7: TraceNormalizer

**Files:**
- Modify: `src/rca_sdk/normalization/trace.py`
- Modify: `tests/test_normalizers.py` (추가)

**Interfaces:**
- Consumes: collector 레코드(all_traces.csv 13컬럼 dict), Task 4 헬퍼
- Produces: `TraceNormalizer().normalize(batch) -> NormalizedBatch`

- [ ] **Step 1: 실패 테스트 추가** — `tests/test_normalizers.py` 에 append:

```python
from rca_sdk.normalization.trace import TraceNormalizer

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


def test_trace_bad_tags_kept_as_none_tags():
    row = dict(TRACE_ROW, tags="{broken")
    [out] = TraceNormalizer().normalize(trace_batch([row])).records
    assert out.tags == {}                         # 파싱 실패 → 빈 dict + warning


def test_trace_missing_start_time_skipped():
    row = dict(TRACE_ROW, start_time="")
    out = TraceNormalizer().normalize(trace_batch([row]))
    assert out.records == []                      # N3
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_normalizers.py -q`
Expected: 새 trace 테스트 FAIL

- [ ] **Step 3: trace.py 구현**:

```python
"""트레이스 정규화 — all_traces.csv 컬럼 dict → NormalizedTrace (정규화 스펙 §4, 계획 03 §2)."""

from __future__ import annotations

import json
import logging
from typing import Any

from rca_sdk.normalization.base import Normalizer
from rca_sdk.normalization.common import canonical_service, parse_timestamp
from rca_sdk.schemas.events import NormalizedBatch, NormalizedTrace, RawBatch

logger = logging.getLogger(__name__)


class TraceNormalizer(Normalizer):
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        records = []
        for rec in batch.records:
            normalized = self._normalize_record(rec)
            if normalized is not None:
                records.append(normalized)
        return NormalizedBatch(
            modality=batch.modality,
            observed_from=batch.observed_from,
            observed_until=batch.observed_until,
            records=records,
        )

    def _normalize_record(self, rec: dict[str, Any]) -> NormalizedTrace | None:
        source = rec.get("_source", "")
        try:
            timestamp = parse_timestamp(rec["start_time"])
            duration_us = int(rec["duration_us"]) if rec.get("duration_us") else None
            status = int(rec["http_status_code"]) if rec.get("http_status_code") else None
        except (KeyError, ValueError, TypeError):
            logger.warning("%s: trace 행 해석 실패 스킵 (계획 03 N3)", source)
            return None
        tags: dict[str, Any] = {}
        if rec.get("tags"):
            try:
                tags = json.loads(rec["tags"])
            except (json.JSONDecodeError, TypeError):
                logger.warning("%s: tags JSON 해석 실패 — 빈 dict 유지", source)
        logs: Any | None = None
        if rec.get("logs"):
            try:
                logs = json.loads(rec["logs"])
            except (json.JSONDecodeError, TypeError):
                logs = rec["logs"]  # JSON 아니면 원본 유지 (§4)
        return NormalizedTrace(
            timestamp=timestamp,
            service=canonical_service(rec.get("service")),
            trace_id=rec.get("trace_id") or None,
            span_id=rec.get("span_id") or None,
            parent_span_id=rec.get("parent_span_id") or None,
            operation=rec.get("operation") or None,
            duration_us=duration_us,
            duration_ms=duration_us / 1000 if duration_us is not None else None,
            http_status_code=status,
            tags=tags,
            logs=logs,
        )
```

- [ ] **Step 4: 통과·전체 확인**

Run: `uv run pytest -q; uv run ruff check .`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/rca_sdk/normalization/trace.py tests/test_normalizers.py
git commit -m "feat(normalization): TraceNormalizer — 컬럼 매핑 + 공백 None·tags 파싱 (스펙 §4)"
```

---

### Task 8: roster 산출 + Settings expected_services

**Files:**
- Modify: `src/rca_sdk/normalization/base.py` (expected_services 보관)
- Modify: `src/rca_sdk/normalization/log.py`, `metric.py`, `trace.py` (roster 채움)
- Modify: `src/rca_sdk/config.py`
- Modify: `tests/test_normalizers.py` (추가)

**Interfaces:**
- Consumes: `SourceStatus(source, present, record_count)`(schemas), Task 5~7 normalizer
- Produces: `Normalizer(expected_services: Sequence[str] = ())` 생성자; `NormalizedBatch.roster` 채워짐; `Settings.expected_services: list[str]`(기본 12종)

- [ ] **Step 1: 실패 테스트 추가** — `tests/test_normalizers.py` 에 append:

```python
from rca_sdk.config import Settings


def roster_of(batch_out):
    return {s.source: (s.present, s.record_count) for s in batch_out.roster}


def test_log_roster_missing_empty_data():
    """Code_Stop 실측: media 파일 자체 없음(missing) · nginx 0바이트(empty) · text 데이터."""
    normalizer = LogNormalizer(expected_services=["media", "nginx", "text"])
    batch = log_batch(
        [{"raw": BOOST_CONNECT, "_source": "TextService_.log"}],
        sources=["TextService_.log", "NginxThrift_.log"],   # media 파일은 관측 안 됨
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_normalizers.py -q`
Expected: FAIL — `expected_services` 인자 없음, roster 비어 있음

- [ ] **Step 3: base.py 에 생성자 추가**:

```python
"""Normalizer 추상 인터페이스. 모달리티별 정규화기가 이를 구현한다.

RawBatch 를 받아 모달리티별 정규화 레코드로 변환하고, 배치 메타(observed_from/until)는 유지한다.
소스 present/missing 판정도 이 계층이 전담한다 (정규화 스펙 §2, roster 원천, 계획 03 N2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Sequence

from rca_sdk.schemas.events import NormalizedBatch, RawBatch, SourceStatus


class Normalizer(ABC):
    def __init__(self, expected_services: Sequence[str] = ()) -> None:
        self.expected_services = list(expected_services)  # canonical 목록 (Settings 주입)

    @abstractmethod
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        """RawBatch → NormalizedBatch (모달리티별 정규화 스키마 + roster)."""
        raise NotImplementedError

    def _build_roster(
        self, expected: Sequence[str], present: set[str], counts: Counter[str]
    ) -> list[SourceStatus]:
        """expected × 관측(present)·건수 → SourceStatus 목록 (missing/empty/data 재료)."""
        return [
            SourceStatus(source=svc, present=svc in present, record_count=counts.get(svc, 0))
            for svc in expected
        ]
```

- [ ] **Step 4: 각 normalizer 에 roster 결합** — 세 normalize() 모두 `records` 완성 직후 아래 패턴으로 roster 를 만들고 `NormalizedBatch(..., roster=roster)` 로 전달한다:

```python
# log.py — normalize() 안, records 완성 후
from collections import Counter  # 파일 상단 import

counts = Counter(r.service for r in records if r.service)
present = {
    svc
    for src in batch.sources
    if (svc := canonical_service(src.removesuffix(".log"))) is not None
}
roster = self._build_roster(self.expected_services, present, counts)
```

```python
# metric.py — normalize() 안 (NODE_SERVICE 는 이미 정의됨)
counts = Counter(r.service for r in records if r.service)
expected = [*self.expected_services, NODE_SERVICE]
has_container = any(s.startswith("socialnet_container_") for s in batch.sources)
has_system = any(s.startswith("system_") for s in batch.sources)
present = {
    svc for svc in expected
    if (has_system if svc == NODE_SERVICE else has_container)
}
roster = self._build_roster(expected, present, counts)
```

```python
# trace.py — normalize() 안
counts = Counter(r.service for r in records if r.service)
present = set(self.expected_services) if "all_traces.csv" in batch.sources else set()
roster = self._build_roster(self.expected_services, present, counts)
```

- [ ] **Step 5: Settings 필드 추가** — `src/rca_sdk/config.py` 의 `dataset_root` 아래에:

```python
    # 기대 서비스 로스터 (canonical, 계획 03 §3) — missing 판정의 관측 밖 기준
    expected_services: list[str] = [
        "media", "nginx", "user", "text", "uniqueid", "urlshorten",
        "usermention", "usertimeline", "hometimeline", "poststorage",
        "composepost", "socialgraph",
    ]
```

- [ ] **Step 6: 통과·전체 확인**

Run: `uv run pytest -q; uv run ruff check .`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add src/rca_sdk/normalization src/rca_sdk/config.py tests/test_normalizers.py
git commit -m "feat(normalization): roster 산출(N2) + Settings expected_services 기본 12종 (계획 03 §2·§3)"
```

---

### Task 9: README 현행화 + 최종 검증

**Files:**
- Modify: `src/rca_sdk/collectors/README.md`
- Modify: `src/rca_sdk/normalization/README.md`

**Interfaces:** 없음 (문서)

- [ ] **Step 1: collectors README 갱신** — JSONL 서술을 원본 형식으로 교체:

```markdown
# collectors — ① 수집

원천 소스(log·metric·trace)를 tail 해 **정규화 이전의 원시 레코드**(`RawBatch`)를 산출한다.
설계 근거는 [계획 03](../../../docs/plans/03-tail-rework-normalization.md) §1 참조.

- `base.Collector` — 추상 인터페이스. `poll() -> RawBatch` 를 30초 루프마다 호출한다.
- `tail.LineTailCollector` — 공통 구현. `<source_root>/<modality>/<pattern>` 을 파일별
  **byte offset** 으로 이어 읽는다 (미완성 줄 유예, truncate 복구, 삭제 레이스 방어).
  라인 해석은 서브클래스 훅 `_frame` 이 담당하고, `_source`(파일명) 주입과
  `RawBatch.sources`(존재 파일 목록) 전달은 공통층이 한다.
- `tail.CsvTailCollector` — 파일 맨 앞 헤더를 기억해 각 행을 `{컬럼명: 값}` dict 로
  프레이밍한다 (헤더는 offset 이어읽기 특성상 첫 배치에만 나타나므로 상태를 가진
  collector 가 기억한다, 계획 03 N1).
- `log.LogCollector`(`*.log`, `{"raw": 라인}`) / `metric.MetricCollector`·
  `trace.TraceCollector`(`*.csv`, 컬럼 dict) — 프로덕션 전환은 `poll()` 교체로 흡수 (ADR-004).
- `tail.validate_source_layout()` — 기동 시 경로 검증 헬퍼 (호출은 Runner 소관).

소스 present/missing **판정**은 여기서 하지 않는다 — 관측 사실만 전달하고 판정은
`normalization/` 이 전담한다 (ADR-005).
```

- [ ] **Step 2: normalization README 갱신**:

```markdown
# normalization — ② 정규화

collector 의 원시 레코드를 표준 스키마(`NormalizedLog/Metric/Trace`)로 변환하고,
기대 로스터 대조로 소스 상태(roster)를 판정한다.
설계 근거는 [계획 03](../../../docs/plans/03-tail-rework-normalization.md) §2 참조.

- `common.canonical_service()` — 서비스명 정규화 (스펙 §1-1, 인프라 예외·nginx ALIASES).
- `common.parse_timestamp()` — boost 영문월·nginx·ISO 공백형 → **naive** datetime (C6).
- `log.LogNormalizer` — `{"raw": 라인}` 을 boost/nginx 정규식으로 분해.
  `event_type`(service_start = restart_marker 원천 / connection_error / normal_log),
  `code_loc`, `target_service`(Could not connect to 패턴만, 익명 resolve-host 는 None) 파생.
- `metric.MetricNormalizer` — CSV 컬럼 dict. container_label → canonical,
  `instance`(system_*) → `__node__`(cpu_spike 원천), unit 상수 테이블.
- `trace.TraceNormalizer` — all_traces.csv 컬럼 직행 매핑, 공백 → None, tags/logs JSON 파싱.
- roster — `Normalizer(expected_services)` × `batch.sources` × 서비스별 건수 →
  `SourceStatus(source=canonical, present, record_count)`.
  missing(파일 없음) / empty(있는데 0건) / data 구분 재료 (Code_Stop 국소화, 계획 03 N2).

레코드 단위 파싱 실패는 skip + warning (N3) — 한 줄 오염이 30초 루프를 멈추지 않는다.
```

- [ ] **Step 3: 최종 전체 검증**

Run: `uv run pytest -q; uv run ruff check .`
Expected: all passed (collector 21 + normalization ~25 + 기존 스위트)

- [ ] **Step 4: Commit**

```bash
git add src/rca_sdk/collectors/README.md src/rca_sdk/normalization/README.md
git commit -m "docs: collectors·normalization README 를 계획 03 구현 기준으로 현행화"
```
