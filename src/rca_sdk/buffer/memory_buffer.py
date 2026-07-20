"""시간 기반 롤링 메모리 버퍼 — 계획 04.

NormalizedBatch 를 적재하고 `watermark − retention_sec` 이전 레코드를 축출한다(B3).
`get_snapshot(start, end)` 은 반열림 구간 [start, end) 의 모달리티별 레코드를
독립 복사본(MultimodalSnapshot)으로 반환한다 (ADR-005 §2.3).

보존 기간은 pre 윈도가 아니라 **pre + post** 를 담을 만큼 주입받는다(B1). 버퍼는
pre/post 의미를 모르고 "얼마나 오래 들고 있을지"만 안다 — 정책은 SnapshotManager 소관.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from rca_sdk.schemas.events import (
    Modality,
    MultimodalSnapshot,
    NormalizedBatch,
    NormalizedLog,
    NormalizedMetric,
    NormalizedRecord,
    NormalizedTrace,
    SourceStatus,
)


@dataclass
class BatchCoverage:
    """배치 1건의 관측 구간과 roster (buffer 내부 타입 — 공용 계약을 늘리지 않는다)."""

    observed_from: datetime
    observed_until: datetime
    roster: list[SourceStatus] = field(default_factory=list)


class MemoryBuffer:
    def __init__(self, retention_sec: int = 390) -> None:
        # 기본값 = buffer_window_sec(210) + post_trigger_wait_sec(180). 주입은 Runner 소관 (B1).
        self.retention_sec = retention_sec
        self._records: dict[Modality, list[NormalizedRecord]] = defaultdict(list)
        self._history: dict[Modality, list[BatchCoverage]] = defaultdict(list)
        self._watermark: datetime | None = None

    def append(self, batch: NormalizedBatch) -> None:
        """정규화 배치를 버퍼에 적재하고 오래된 레코드를 축출한다."""
        self._records[batch.modality].extend(batch.records)
        # 레코드 0건 배치도 이력에 남긴다 — empty(파일은 있는데 0건) 판정 재료
        self._history[batch.modality].append(
            BatchCoverage(
                observed_from=batch.observed_from,
                observed_until=batch.observed_until,
                roster=list(batch.roster),
            )
        )
        if self._watermark is None or batch.observed_until > self._watermark:
            self._watermark = batch.observed_until
        self._evict()

    def get_snapshot(self, start_ts: datetime, end_ts: datetime) -> MultimodalSnapshot:
        """반열림 구간 [start_ts, end_ts) 의 모달리티별 레코드를 독립 복사본으로 반환한다."""
        selected: dict[Modality, list[NormalizedRecord]] = {}
        for modality, records in self._records.items():
            picked = [r for r in records if start_ts <= r.timestamp < end_ts]
            picked.sort(key=lambda r: r.timestamp)  # 배치 내 순서는 파일 순 — 시간순 아님 (B4)
            # 조립·전송 중에도 버퍼는 계속 도므로 독립 복사본을 넘긴다
            selected[modality] = [r.model_copy(deep=True) for r in picked]
        coverage = {
            modality.value: self._aggregate_roster(modality, start_ts, end_ts)
            for modality in self._history
        }
        return MultimodalSnapshot(
            logs=[r for r in selected.get(Modality.LOG, []) if isinstance(r, NormalizedLog)],
            metrics=[
                r for r in selected.get(Modality.METRIC, []) if isinstance(r, NormalizedMetric)
            ],
            traces=[r for r in selected.get(Modality.TRACE, []) if isinstance(r, NormalizedTrace)],
            coverage=coverage,
        )

    def _evict(self) -> None:
        """`watermark − retention_sec` 이전 레코드·이력을 버린다 (경계값은 유지)."""
        if self._watermark is None:
            return
        threshold = self._watermark - timedelta(seconds=self.retention_sec)
        for modality, records in self._records.items():
            self._records[modality] = [r for r in records if r.timestamp >= threshold]
        for modality, history in self._history.items():
            self._history[modality] = [b for b in history if b.observed_until >= threshold]

    def _aggregate_roster(
        self, modality: Modality, start_ts: datetime, end_ts: datetime
    ) -> list[SourceStatus]:
        """구간과 겹치는 배치들의 roster 를 source 별로 접는다 — present=OR, count=합계 (B2).

        배치가 연속(N.until == N+1.from)이므로 `until > start` 로 걸러 경계 배치의
        이중 계산을 막는다.
        """
        present: dict[str, bool] = {}
        counts: dict[str, int] = {}
        order: list[str] = []
        for batch in self._history[modality]:
            if not (batch.observed_from < end_ts and batch.observed_until > start_ts):
                continue
            for status in batch.roster:
                if status.source not in present:
                    present[status.source] = False
                    counts[status.source] = 0
                    order.append(status.source)
                present[status.source] |= status.present
                counts[status.source] += status.record_count
        return [
            SourceStatus(source=source, present=present[source], record_count=counts[source])
            for source in order
        ]
