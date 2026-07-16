"""실행 기록 — `var/.replay/runs.csv` (계획 Phase 3).

이어 돌리기가 정상 경로라, `var/` 만 봐서는 어디서 시나리오가 바뀌었는지 알 수 없다. 무엇을 언제
돌렸는지 여기 남는다.

`started_at` 은 곧 그 실행의 **`T0` 앵커**다. 원본 시각 → 재생 시각 매핑을 나중에 되짚을 수 있다.

`.replay/` 는 `--reset` 대상이 아니라 이력이 보존된다 (`ADR-004`).
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

HEADER = ("scenario", "started_at", "ended_at", "status")

RUNNING = "running"
COMPLETED = "completed"
INTERRUPTED = "interrupted"
RESET = "reset"


class RunLog:
    """`runs.csv` 한 개. 진행 중인 행 하나를 붙들고 있다가 종료 시 그 행을 갱신한다.

    append 만으로는 "완료되면 체크"가 안 된다 — 시작 시점엔 종료 시각을 모른다. 파일이 작으므로
    (실행 1건 = 1행) 종료 시 전체를 다시 쓴다.
    """

    def __init__(self, source_root: Path) -> None:
        self.path = source_root / ".replay" / "runs.csv"
        self._row: int | None = None

    def _read(self) -> list[list[str]]:
        if not self.path.is_file():
            return []
        with open(self.path, encoding="utf-8", newline="") as f:
            return [r for r in csv.reader(f) if r]

    def _write(self, rows: list[list[str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(rows)

    def _append(self, row: list[str]) -> int:
        rows = self._read()[1:]  # 헤더 제외
        rows.append(row)
        self._write(rows)
        return len(rows) - 1

    def start(self, scenario: str, at: datetime) -> None:
        """`status=running` 행을 남긴다. `at` 이 그 실행의 `T0` 앵커다."""
        self._row = self._append([scenario, at.isoformat(), "", RUNNING])

    def finish(self, status: str, at: datetime) -> None:
        """`start()` 가 남긴 행의 `ended_at` 과 `status` 를 채운다.

        `start()` 없이 부르면 아무것도 하지 않는다 — 기록할 실행이 없다.
        강제 종료되면 이 함수가 불리지 않아 행이 `running` 인 채로 남는다. 사실 그대로다.
        """
        if self._row is None:
            return
        rows = self._read()[1:]
        rows[self._row][2] = at.isoformat()
        rows[self._row][3] = status
        self._write(rows)

    def reset(self, at: datetime) -> None:
        """`--reset` 을 기록한다. 기록과 실제 데이터가 어긋나 보일 때 이유가 된다."""
        self._append(["", at.isoformat(), at.isoformat(), RESET])
