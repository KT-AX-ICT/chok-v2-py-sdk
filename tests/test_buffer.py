"""MemoryBuffer 단위 테스트 — 계획 04 (watermark 축출 · 반열림 조회 · coverage 집계).

시각은 전부 고정 기준시(T0)에서 만든 naive datetime 이다. 실제 벽시계를 쓰지 않는 것 자체가
"축출 기준은 watermark 이지 벽시계가 아니다"(B3)를 보장한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.buffer.memory_buffer import MemoryBuffer
from rca_sdk.schemas.events import (
    Modality,
    NormalizedBatch,
    NormalizedLog,
    NormalizedMetric,
    NormalizedTrace,
    SourceStatus,
)

T0 = datetime(2025, 11, 4, 0, 0, 0)


def at(sec: float) -> datetime:
    return T0 + timedelta(seconds=sec)


def log_batch(
    from_sec: float,
    until_sec: float,
    record_secs: list[float] | None = None,
    roster: list[SourceStatus] | None = None,
) -> NormalizedBatch:
    return NormalizedBatch(
        modality=Modality.LOG,
        observed_from=at(from_sec),
        observed_until=at(until_sec),
        records=[NormalizedLog(timestamp=at(s), service="media") for s in (record_secs or [])],
        roster=roster or [],
    )


# --- 적재·조회 ---


def test_records_within_window_returned():
    buf = MemoryBuffer(retention_sec=600)
    buf.append(log_batch(0, 30, [10, 20]))
    snap = buf.get_snapshot(at(0), at(30))
    assert [r.timestamp for r in snap.logs] == [at(10), at(20)]


def test_window_is_half_open():
    """[start, end) — start 는 포함, end 는 제외."""
    buf = MemoryBuffer(retention_sec=600)
    buf.append(log_batch(0, 60, [10, 20, 30]))
    snap = buf.get_snapshot(at(10), at(30))
    assert [r.timestamp for r in snap.logs] == [at(10), at(20)]


def test_empty_window_returns_empty_snapshot():
    buf = MemoryBuffer(retention_sec=600)
    buf.append(log_batch(0, 30, [10]))
    snap = buf.get_snapshot(at(100), at(200))
    assert snap.logs == []


def test_records_sorted_by_timestamp():
    """배치 내 레코드는 파일 단위로 읽혀 시간순이 아니다 — 조회 시 정렬해 돌려준다 (B4)."""
    buf = MemoryBuffer(retention_sec=600)
    buf.append(log_batch(0, 60, [50, 10, 30]))  # 파일 A→B→C 순서로 들어온 상황
    snap = buf.get_snapshot(at(0), at(60))
    assert [r.timestamp for r in snap.logs] == [at(10), at(30), at(50)]


def test_modalities_are_separated():
    buf = MemoryBuffer(retention_sec=600)
    buf.append(log_batch(0, 30, [10]))
    buf.append(
        NormalizedBatch(
            modality=Modality.METRIC,
            observed_from=at(0),
            observed_until=at(30),
            records=[NormalizedMetric(timestamp=at(11), service="__node__", value=1.0)],
        )
    )
    buf.append(
        NormalizedBatch(
            modality=Modality.TRACE,
            observed_from=at(0),
            observed_until=at(30),
            records=[NormalizedTrace(timestamp=at(12), service="nginx")],
        )
    )
    snap = buf.get_snapshot(at(0), at(30))
    assert len(snap.logs) == 1
    assert len(snap.metrics) == 1
    assert len(snap.traces) == 1


# --- 축출 (watermark 기준, B3) ---


def test_evicts_records_older_than_retention():
    buf = MemoryBuffer(retention_sec=60)
    buf.append(log_batch(0, 30, [10]))
    buf.append(log_batch(60, 90, [70]))  # watermark=90 → 임계 30, 10 은 축출
    snap = buf.get_snapshot(at(0), at(200))
    assert [r.timestamp for r in snap.logs] == [at(70)]


def test_keeps_record_exactly_at_eviction_threshold():
    buf = MemoryBuffer(retention_sec=60)
    buf.append(log_batch(0, 30, [30]))
    buf.append(log_batch(60, 90, [70]))  # 임계 30 — 경계값은 유지
    snap = buf.get_snapshot(at(0), at(200))
    assert [r.timestamp for r in snap.logs] == [at(30), at(70)]


def test_eviction_uses_watermark_not_wall_clock():
    """레코드 시각은 실제 현재보다 한참 과거지만, watermark 가 낮으면 축출되지 않는다."""
    buf = MemoryBuffer(retention_sec=60)
    buf.append(log_batch(0, 30, [10]))
    buf.append(log_batch(30, 60, [40]))  # watermark=60 → 임계 0
    snap = buf.get_snapshot(at(0), at(200))
    assert [r.timestamp for r in snap.logs] == [at(10), at(40)]


def test_history_evicted_with_records():
    buf = MemoryBuffer(retention_sec=60)
    buf.append(log_batch(0, 30, roster=[SourceStatus(source="media", present=True)]))
    buf.append(log_batch(300, 330, roster=[SourceStatus(source="media", present=True)]))
    snap = buf.get_snapshot(at(0), at(30))  # 옛 구간 이력은 사라졌다
    assert snap.coverage.get("log", []) == []


# --- coverage 집계 (B2) ---


def test_zero_record_batch_kept_in_coverage():
    """0건 배치도 이력에 남아야 empty 판정 재료가 된다."""
    buf = MemoryBuffer(retention_sec=600)
    buf.append(log_batch(0, 30, roster=[SourceStatus(source="nginx", present=True)]))
    snap = buf.get_snapshot(at(0), at(30))
    assert snap.coverage["log"] == [SourceStatus(source="nginx", present=True, record_count=0)]


def test_coverage_present_is_or_across_batches():
    buf = MemoryBuffer(retention_sec=600)
    buf.append(log_batch(0, 30, roster=[SourceStatus(source="media", present=False)]))
    buf.append(
        log_batch(30, 60, roster=[SourceStatus(source="media", present=True, record_count=5)])
    )
    snap = buf.get_snapshot(at(0), at(60))
    [status] = snap.coverage["log"]
    assert status.present is True


def test_coverage_record_count_is_summed():
    buf = MemoryBuffer(retention_sec=600)
    buf.append(
        log_batch(0, 30, roster=[SourceStatus(source="media", present=True, record_count=3)])
    )
    buf.append(
        log_batch(30, 60, roster=[SourceStatus(source="media", present=True, record_count=5)])
    )
    snap = buf.get_snapshot(at(0), at(60))
    [status] = snap.coverage["log"]
    assert status.record_count == 8


def test_coverage_excludes_batch_ending_at_window_start():
    """배치가 연속(N.until == N+1.from)이라 경계 배치가 이중 계산되면 안 된다."""
    buf = MemoryBuffer(retention_sec=600)
    buf.append(
        log_batch(0, 30, roster=[SourceStatus(source="media", present=True, record_count=10)])
    )
    buf.append(log_batch(30, 60, roster=[SourceStatus(source="media", present=False)]))
    snap = buf.get_snapshot(at(30), at(60))  # 앞 배치는 until==start 라 제외
    [status] = snap.coverage["log"]
    assert status.present is False
    assert status.record_count == 0


def test_coverage_three_states():
    """missing(파일 없음) · empty(있는데 0건) · data 를 한 배치에서 구분한다."""
    buf = MemoryBuffer(retention_sec=600)
    buf.append(
        log_batch(
            0,
            30,
            roster=[
                SourceStatus(source="media", present=False, record_count=0),
                SourceStatus(source="nginx", present=True, record_count=0),
                SourceStatus(source="text", present=True, record_count=7),
            ],
        )
    )
    snap = buf.get_snapshot(at(0), at(30))
    states = {s.source: (s.present, s.record_count) for s in snap.coverage["log"]}
    assert states["media"] == (False, 0)
    assert states["nginx"] == (True, 0)
    assert states["text"] == (True, 7)


# --- 독립성 (deep copy) ---


def test_snapshot_records_are_deep_copies():
    buf = MemoryBuffer(retention_sec=600)
    buf.append(log_batch(0, 30, [10]))
    first = buf.get_snapshot(at(0), at(30))
    first.logs[0].service = "mutated"
    second = buf.get_snapshot(at(0), at(30))
    assert second.logs[0].service == "media"  # 버퍼 원본은 그대로


def test_snapshot_unaffected_by_later_eviction():
    """스냅샷 조립·전송 중에도 버퍼는 계속 돈다 — 이미 꺼낸 스냅샷은 변하지 않아야 한다."""
    buf = MemoryBuffer(retention_sec=60)
    buf.append(log_batch(0, 30, [10]))
    snap = buf.get_snapshot(at(0), at(30))
    buf.append(log_batch(300, 330, [310]))  # 앞 레코드는 버퍼에서 축출됨
    assert [r.timestamp for r in snap.logs] == [at(10)]


# ── scan (복사 없는 구간 조회) — 계획 05 §7, 실측으로 드러난 필요 ────────────
#
# detector 는 매 틱 구간을 되돌아보며 **읽고 버린다.** get_snapshot 은 번들 조립용이라
# 독립 복사본을 만드는데, 그 복사가 Svc_Kill 재생 시간의 88% 였다(deep copy 244만 회).
# scan 은 같은 구간을 **참조로** 준다 — 호출자가 수정하지 않는다는 전제.


def metric_batch(from_sec: float, until_sec: float, record_secs: list[float]) -> NormalizedBatch:
    return NormalizedBatch(
        modality=Modality.METRIC,
        observed_from=at(from_sec),
        observed_until=at(until_sec),
        records=[
            NormalizedMetric(timestamp=at(s), service="__node__", metric_name="cpu", value=1.0)
            for s in record_secs
        ],
    )


def trace_batch(from_sec: float, until_sec: float, record_secs: list[float]) -> NormalizedBatch:
    return NormalizedBatch(
        modality=Modality.TRACE,
        observed_from=at(from_sec),
        observed_until=at(until_sec),
        records=[NormalizedTrace(timestamp=at(s), service="media") for s in record_secs],
    )


def mixed_buffer() -> MemoryBuffer:
    buf = MemoryBuffer()
    buf.append(log_batch(0, 30, [10]))
    buf.append(metric_batch(0, 30, [12]))
    buf.append(trace_batch(0, 30, [14]))
    return buf


def test_scan_returns_only_requested_modality():
    assert [r.timestamp for r in mixed_buffer().scan(at(0), at(30), Modality.METRIC)] == [at(12)]


def test_scan_uses_half_open_interval():
    buf = MemoryBuffer()
    buf.append(log_batch(0, 60, [0, 30, 60]))
    assert [r.timestamp for r in buf.scan(at(0), at(60), Modality.LOG)] == [at(0), at(30)]


def test_scan_returns_time_sorted():
    buf = MemoryBuffer()
    buf.append(log_batch(0, 60, [40, 10, 25]))  # 파일 순 = 시간순 아님 (B4)
    assert [r.timestamp for r in buf.scan(at(0), at(60), Modality.LOG)] == [at(10), at(25), at(40)]


def test_scan_on_empty_modality_is_empty():
    assert mixed_buffer().scan(at(0), at(30), Modality.METRIC) != []
    assert MemoryBuffer().scan(at(0), at(30), Modality.LOG) == []


def test_scan_returns_references_not_copies():
    """scan 의 존재 이유. 호출자가 수정하면 버퍼에 비친다 — 읽고 버릴 때만 쓴다."""
    buf = mixed_buffer()
    scanned = buf.scan(at(0), at(30), Modality.LOG)
    assert scanned[0] is buf._records[Modality.LOG][0]


def test_get_snapshot_still_copies():
    """번들 조립 경로는 그대로 독립 복사본이어야 한다."""
    buf = mixed_buffer()
    snap = buf.get_snapshot(at(0), at(30))
    snap.logs[0].service = "mutated"
    assert buf.scan(at(0), at(30), Modality.LOG)[0].service == "media"
