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
        self._last_poll_at = datetime.now()  # 첫 poll 의 관측 하한 = 생성 시각 (폭 0 구간 방지)

    def poll(self) -> RawBatch:
        now = datetime.now()  # naive (계획 02 C6)
        records: list[dict[str, Any]] = [] #poll에서 새롭게 읽은 데이터
        sources: list[str] = [] # 현재 디렉토리에 존재하는 파일 목록
        # 현재 디렉토리에서 모든 .jsonl 파일을 순회하며 새롭게 추가된 라인을 읽어온다
        for path in sorted(self._dir.glob("*.jsonl")):
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

    def _read_new_lines(self, path: Path) -> list[dict[str, Any]]:
        offset = self._offsets.get(path.name, 0)
        # 현재 파일 크기 < 내가 기억하는 offset
        if path.stat().st_size < offset:
            offset = 0  # 파일이 줄어듦 = 리플레이어 --reset 재실행 → 처음부터
        with path.open("rb") as f: # read binary 모드로 열어 offset 위치부터 읽는다. 
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
            # 원하는 jsonl 형식이 아니면 스킵 
            if not isinstance(rec, dict):
                logger.warning("%s: 객체가 아닌 JSON 줄 스킵", path.name)
                continue
            rec["_source"] = path.name
            records.append(rec)
        self._offsets[path.name] = offset + len(chunk)
        return records
