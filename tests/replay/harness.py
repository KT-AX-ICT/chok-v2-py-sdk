"""데이터셋을 30초 배치로 재생하는 테스트 하네스 (계획 05 §3).

리플레이어가 하는 일과 같다 — **타임스탬프만 파싱**해 30초 구간에 나누고, 원본 줄/행은
바이트 그대로 넘긴다(ADR-004). `Collector.poll() -> RawBatch` 만 대체하므로 정규화·roster
판정·버퍼·detector·스냅샷은 전부 **실제 구현**이 탄다.

파일 tail(오프셋·미완성 줄·truncate 복구)만 빠진다 — 그건 `tests/test_collectors.py` 소관.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from rca_sdk.normalization.common import parse_timestamp
from rca_sdk.schemas.events import Modality, RawBatch

TICK_SEC = 30

# 모달리티별 (하위 디렉토리 glob, 시각 컬럼). log 는 CSV 가 아니라 raw 라인.
_CSV_TIME_COLUMN = {Modality.METRIC: "timestamp", Modality.TRACE: "start_time"}
_PATTERN = {Modality.LOG: "*.log", Modality.METRIC: "*.csv", Modality.TRACE: "*.csv"}

# 원본 줄 앞머리의 타임스탬프만 집는다 — 본문 해석은 normalizer 소관.
_BOOST_PREFIX = re.compile(r"^\[([^\]]+)\]")
_NGINX_PREFIX = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})")


def line_timestamp(line: str) -> datetime | None:
    """로그 한 줄의 시각. 앞머리에 타임스탬프가 없으면(스택트레이스 등) None."""
    match = _BOOST_PREFIX.match(line) or _NGINX_PREFIX.match(line)
    if match is None:
        return None
    try:
        return parse_timestamp(match.group(1))
    except (ValueError, TypeError):
        return None


class DatasetReplayCollector:
    """시나리오 디렉토리를 30초씩 잘라 RawBatch 로 낸다.

    `Collector` 를 상속하지 않는다 — 계약(`modality` 속성 + `poll()`)만 맞추면 Runner 가
    받는다. 상속하면 `source_root` 기반 __init__ 을 억지로 맞춰야 한다.
    """

    def __init__(
        self,
        data_dir: Path,
        modality: Modality,
        origin: datetime | None = None,
        tick_sec: int = TICK_SEC,
    ) -> None:
        # data_dir 은 **파일이 직접 든 디렉토리**다. 데이터셋 레이아웃이
        # `<root>/log_data/<시나리오>_logs_.../` 라 SDK 의 `<root>/<modality>/` 와 다르다 —
        # 억지로 맞추면 심볼릭 링크가 필요해진다(Windows 에서 권한 문제).
        self.modality = modality
        self.tick_sec = tick_sec
        self._dir = Path(data_dir)
        self.sources: list[str] = []
        self._records: list[tuple[datetime, dict[str, Any]]] = self._load()
        # 시간순 정렬 — 파일 단위로 읽히므로 원본은 시간순이 아니다
        self._records.sort(key=lambda pair: pair[0])
        self.origin = origin or (self._records[0][0] if self._records else datetime.min)
        self._cursor = 0   # 아직 안 낸 첫 레코드
        self._tick = 0

    @property
    def exhausted(self) -> bool:
        """남은 레코드가 없는가. 재생 루프의 종료 조건."""
        return self._cursor >= len(self._records)

    def poll(self) -> RawBatch:
        start = self.origin + timedelta(seconds=self.tick_sec * self._tick)
        end = start + timedelta(seconds=self.tick_sec)
        self._tick += 1

        records: list[dict[str, Any]] = []
        while self._cursor < len(self._records) and self._records[self._cursor][0] < end:
            records.append(self._records[self._cursor][1])
            self._cursor += 1

        # sources 는 레코드 유무와 무관하게 "파일이 있었다" 는 사실 — empty/missing 판정 재료
        return RawBatch(
            modality=self.modality,
            observed_from=start,
            observed_until=end,
            records=records,
            sources=list(self.sources),
        )

    # ── 적재 ────────────────────────────────────────────────────────────────

    def _load(self) -> list[tuple[datetime, dict[str, Any]]]:
        loaded: list[tuple[datetime, dict[str, Any]]] = []
        for path in sorted(self._dir.glob(_PATTERN[self.modality])):
            self.sources.append(path.name)
            if self.modality is Modality.LOG:
                loaded.extend(self._load_log(path))
            else:
                loaded.extend(self._load_csv(path))
        return loaded

    def _load_log(self, path: Path) -> list[tuple[datetime, dict[str, Any]]]:
        out = []
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.rstrip("\n")
                if not line:
                    continue
                timestamp = line_timestamp(line)
                if timestamp is None:
                    continue  # 시각 없는 줄은 배치에 못 넣는다 — 리플레이어도 같다
                out.append((timestamp, {"raw": line, "_source": path.name}))
        return out

    def _load_csv(self, path: Path) -> list[tuple[datetime, dict[str, Any]]]:
        column = _CSV_TIME_COLUMN[self.modality]
        out = []
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    timestamp = parse_timestamp(row[column])
                except (KeyError, ValueError, TypeError):
                    continue  # 해석 실패 행은 스킵 (계획 03 N3 와 같은 취급)
                row["_source"] = path.name
                out.append((timestamp, dict(row)))
        return out
