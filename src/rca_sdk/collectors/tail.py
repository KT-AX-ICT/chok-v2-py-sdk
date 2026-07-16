"""JSONL tailer 공통 구현 — 파일별 byte offset 을 기억하고 신규 완성 라인만 읽는다.

계획 02 §① collectors. 세 모달리티가 같은 로직을 쓰며, 서브클래스는 modality 만 지정한다.
소스 present/missing 판정은 normalizer 전담 — 여기서는 관측 사실(sources)만 전달한다.
"""

from __future__ import annotations

import json
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


class JsonlTailCollector(Collector):
    """`<source_root>/<modality>/*.jsonl` 을 tail 해 신규 라인을 RawBatch 로 산출한다."""

    def __init__(self, source_root: str) -> None:
        self.source_root = source_root
        self._dir = Path(source_root) / self.modality.value
        self._offsets: dict[str, int] = {}  # 파일명 → 소비한 byte 수 (인메모리, 계획 02 C1)
        self._last_poll_at: datetime | None = None

    def poll(self) -> RawBatch:
        now = datetime.now()  # naive (계획 02 C6)
        records: list[dict[str, Any]] = []
        sources: list[str] = []
        for path in sorted(self._dir.glob("*.jsonl")):
            sources.append(path.name)
            records.extend(self._read_new_lines(path))
        batch = RawBatch(
            modality=self.modality,
            observed_from=self._last_poll_at or now,
            observed_until=now,
            records=records,
            sources=sources,
        )
        self._last_poll_at = now
        return batch

    def _read_new_lines(self, path: Path) -> list[dict[str, Any]]:
        offset = self._offsets.get(path.name, 0)
        if path.stat().st_size < offset:
            offset = 0  # 파일이 줄어듦 = 리플레이어 --reset 재실행 → 처음부터
        with path.open("rb") as f:
            f.seek(offset)
            chunk = f.read()
        incomplete = chunk.rpartition(b"\n")[2]
        if incomplete:  # 개행 없는 마지막 조각 = 쓰는 도중 → 다음 poll 로 미룸
            chunk = chunk[: -len(incomplete)]
        records: list[dict[str, Any]] = []
        for line in chunk.splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("%s: JSON 파싱 실패 줄 스킵 (계획 02 C7)", path.name)
                continue
            if not isinstance(rec, dict):
                logger.warning("%s: 객체가 아닌 JSON 줄 스킵", path.name)
                continue
            rec["_source"] = path.name
            records.append(rec)
        self._offsets[path.name] = offset + len(chunk)
        return records
