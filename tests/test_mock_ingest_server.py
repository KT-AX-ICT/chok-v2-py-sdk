"""scripts/mock_ingest_server.py 의 요약 로직 테스트 (계획 06 §1).

scripts/ 는 demo/ 와 같은 이유로 배포 wheel 대상이 아니라 패키지로 등록돼 있지 않다
(pyproject.toml). 그래서 파일 경로로 직접 모듈을 로드해 sys.path 관례에 기대지 않는다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "mock_ingest_server.py"
_SPEC = importlib.util.spec_from_file_location("mock_ingest_server", _PATH)
mock_ingest_server = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mock_ingest_server)


def test_summarize_includes_window_trigger_and_counts():
    bundle = {
        "window": {"start": "2026-07-22T00:00:41", "end": "2026-07-22T00:06:41"},
        "trigger_info": {"trigger_time": "2026-07-22T00:03:41", "triggered_by": ["log"]},
        "logs": [{}, {}, {}],
        "metrics": [{}],
        "traces": [],
    }
    line = mock_ingest_server.summarize(bundle)
    assert "2026-07-22T00:00:41" in line
    assert "2026-07-22T00:06:41" in line
    assert "2026-07-22T00:03:41" in line
    assert "log" in line
    assert "logs=3" in line
    assert "metrics=1" in line
    assert "traces=0" in line


def test_summarize_handles_multiple_triggered_modalities():
    bundle = {
        "window": {"start": "a", "end": "b"},
        "trigger_info": {"trigger_time": "c", "triggered_by": ["log", "trace"]},
        "logs": [],
        "metrics": [],
        "traces": [{}],
    }
    line = mock_ingest_server.summarize(bundle)
    assert "log,trace" in line
