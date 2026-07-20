"""SnapshotManager — 트리거 발화 시 anchor±3분 스냅샷 번들 조립 (계약 §2.5).

트리거는 "언제·어느 모달리티가 이상"만 알려주므로, 그 앞뒤 3분 원본 데이터를 버퍼에서 떠서
SnapshotBundle 로 묶는다. 번들은 트리거 즉시 못 만든다(뒤 3분이 아직 안 쌓임) → 2단계:
  register_triggers: 트리거 발화 시. 앞 3분(Pre)을 즉시 캡처하고 세션을 연다.
  finalize_ready:    매 틱. 뒤 3분(Post)이 다 차면 번들 완성 후 세션을 닫는다.
동시 세션은 1개. 창이 열린 동안의 재트리거는 같은 세션에 누적한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.events import (
    Modality,
    MultimodalSnapshot,
    NormalizedLog,
    NormalizedMetric,
    NormalizedTrace,
)
from rca_sdk.schemas.snapshot import (
    BundleRecord,
    ModalityInfo,
    SnapshotBundle,
    SourceInterval,
    TriggerInfo,
    Window,
)
from rca_sdk.trigger.models import TriggerEvidence

PRE_SEC = 180   # anchor 앞 3분 (Pre)
POST_SEC = 180  # anchor 뒤 3분 (Post)


@dataclass
class _CaptureSession:
    """진행 중인 캡처 1건. anchor 를 경계로 Pre[window_start, anchor) / Post[anchor, window_end)."""

    anchor: datetime           # 최초 트리거 시각 = 창 중심
    window_start: datetime     # anchor - 3분
    window_end: datetime       # anchor + 3분
    pre: MultimodalSnapshot    # register 시점에 캡처한 앞 3분
    triggered_by: set[Modality] = field(default_factory=set)  # 발화한 모달리티
    evidences: list[TriggerEvidence] = field(default_factory=list)  # 누적 근거(향후 소비용)


class SnapshotManager:
    def __init__(self) -> None:
        self._session: _CaptureSession | None = None  # None = 진행 중 캡처 없음

    def register_triggers(self, evidences: list[TriggerEvidence], buffer: MemoryBuffer) -> None:
        if not evidences:
            return

        if self._session is None:
            # 최초 트리거 → 새 세션. 가장 이른 발화가 anchor.
            anchor = min(e.trigger_time for e in evidences)
            window_start = anchor - timedelta(seconds=PRE_SEC)
            window_end = anchor + timedelta(seconds=POST_SEC)
            # Pre 를 지금 캡처한다 — 버퍼는 롤링이라 나중엔 앞 3분이 사라진다.
            pre = buffer.get_snapshot(window_start, anchor)
            self._session = _CaptureSession(
                anchor=anchor,
                window_start=window_start,
                window_end=window_end,
                pre=pre,
                triggered_by={e.modality for e in evidences},
                evidences=list(evidences),
            )
        else:
            # 재트리거 → 같은 세션에 발화 모달리티만 누적. window·anchor·pre 는 고정.
            self._session.triggered_by |= {e.modality for e in evidences}
            self._session.evidences.extend(evidences)

    def finalize_ready(
        self, observed_until: datetime, buffer: MemoryBuffer
    ) -> list[SnapshotBundle]:
        session = self._session
        # observed_until(관측 진행도)이 window_end 를 넘어야 Post 3분이 다 쌓인 것.
        if session is None or observed_until < session.window_end:
            return []
        # Post 캡처. [anchor, window_end) 라 Pre[window_start, anchor) 와 anchor 에서 안 겹침.
        post = buffer.get_snapshot(session.anchor, session.window_end)
        bundle = self._assemble(session, post)
        self._session = None  # 세션 종료 → 다음 트리거는 새 세션
        return [bundle]

    def _assemble(self, session: _CaptureSession, post: MultimodalSnapshot) -> SnapshotBundle:
        pre = session.pre
        return SnapshotBundle(
            window=Window(start=session.window_start, end=session.window_end),
            trigger_info=TriggerInfo(
                trigger_time=session.anchor,
                triggered_by=sorted(m.value for m in session.triggered_by),  # 중복 제거·정렬
            ),
            # Pre 뒤에 Post 를 이어 붙이면 시간순 (Pre 구간이 Post 보다 앞섬).
            logs=[_rec(r) for r in [*pre.logs, *post.logs]],
            metrics=[_rec(r) for r in [*pre.metrics, *post.metrics]],
            traces=[_rec(r) for r in [*pre.traces, *post.traces]],
            modality_info=_modality_info(pre, post, session.window_start, session.window_end),
        )


def _rec(record: NormalizedLog | NormalizedTrace | NormalizedMetric) -> BundleRecord:
    # 정규화 레코드 → 전송용 얇은 레코드. raw 는 원본이 없어 정규화 레코드를 JSON 직렬화한 것.
    return BundleRecord(
        timestamp=record.timestamp,
        service=record.service,
        raw=record.model_dump_json(),
    )


def _modality_info(
    pre: MultimodalSnapshot,
    post: MultimodalSnapshot,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, ModalityInfo]:
    # coverage(roster)의 레코드 수를 Pre+Post 합산 → >0 이면 data, 아니면 empty.
    # missing(파일 부재)은 Normalizer roster 완성 후. coverage 비면 빈 dict.
    merged: dict[tuple[str, str], int] = {}
    for snap in (pre, post):
        for modality, statuses in snap.coverage.items():
            for status in statuses:
                key = (modality, status.source)
                merged[key] = merged.get(key, 0) + status.record_count

    info: dict[str, ModalityInfo] = {}
    for (modality, source), count in merged.items():
        interval = SourceInterval(
            fileName=source,
            status="data" if count > 0 else "empty",
            start=window_start,
            end=window_end,
        )
        info.setdefault(modality, ModalityInfo()).intervals.append(interval)
    return info
