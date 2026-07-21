"""라인 tailer 공통 구현 — 파일별 byte offset 을 기억하고 신규 완성 라인만 읽는다.

계획 03 §1. var/ 는 원본 형식 그대로(log 텍스트 라인·CSV)이므로 라인 해석은
서브클래스 훅 `_frame` 이 담당한다. 소스 present/missing 판정은 normalizer 전담 —
여기서는 관측 사실(sources)만 전달한다.
"""

from __future__ import annotations

import csv
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
