"""Phase 2 검증 — 시프트가 간격과 내용을 보존하는가 (계획 0-5).

핵심은 **항등 테스트**다. `anchor == t0` 로 두면 `new_ts == orig_ts` 이므로, 출력 줄은 입력 줄과
바이트 동일해야 한다. 렌더러가 원본 포맷을 한 글자라도 다르게 재현하면 여기서 걸린다.
"""

from __future__ import annotations

import glob
from datetime import UTC, datetime, timedelta

import pytest

from demo.replayer.readers import read_csv, read_log, read_nginx
from demo.replayer.shift import (
    csv_field_span,
    measure_t0,
    shift_csv_line,
    shift_log_line,
    shift_nginx_line,
    shift_ts,
)

SCENARIOS = ["Perf_CPU_Contention", "Svc_Kill_Media", "Code_Stop_MediaService"]

# 실측한 모달리티 최소 시각의 t0 대비 편차 (계획 0-3). 시프트는 이 관계를 바꾸면 안 된다.
TRACE_LAG = {"Perf_CPU_Contention": 126.3, "Svc_Kill_Media": 178.7, "Code_Stop_MediaService": 162.4}


def scen_dir(modality: str, prefix: str) -> str:
    hits = glob.glob(f"datasets/sn/{modality}_data/{prefix}_*/")
    if not hits:
        pytest.skip(f"데이터셋 없음: {modality}/{prefix} (MVP 3종만 커밋됨)")
    return hits[0]


# --- 오프셋 산술 ---------------------------------------------------------------


def test_shift_ts_preserves_gap():
    t0 = datetime(2025, 11, 3, 22, 26, 39, 643105, tzinfo=UTC)
    anchor = datetime(2026, 7, 16, 16, 0, 0, tzinfo=UTC)
    a = shift_ts(t0, t0, anchor)
    b = shift_ts(t0 + timedelta(seconds=104, microseconds=17), t0, anchor)
    assert a == anchor
    assert b - a == timedelta(seconds=104, microseconds=17)


def test_shift_ts_anchor_is_fixed_not_now():
    """같은 t0 을 두 번 시프트하면 같은 값이 나온다 — 레코드마다 now() 를 부르면 깨진다."""
    t0 = datetime(2025, 11, 3, 22, 26, 39, tzinfo=UTC)
    anchor = datetime(2026, 7, 16, 16, 0, 0, tzinfo=UTC)
    assert shift_ts(t0, t0, anchor) == shift_ts(t0, t0, anchor)


def test_measure_t0_is_min_not_first():
    """CSV 는 시계열 단위로 묶여 있어 첫 행이 최소가 아니다 (계획 0-6')."""
    xs = [
        datetime(2025, 11, 3, 22, 30, tzinfo=UTC),
        datetime(2025, 11, 3, 22, 26, tzinfo=UTC),
        datetime(2025, 11, 3, 22, 28, tzinfo=UTC),
    ]
    assert measure_t0(xs) == xs[1]


def test_measure_t0_rejects_empty():
    with pytest.raises(ValueError):
        measure_t0([])


# --- 렌더링: 항등 (anchor == t0 이면 원본 그대로) ---------------------------------


def test_boost_identity_on_real_log():
    path = scen_dir("log", "Perf_CPU_Contention") + "MediaService_.log"
    n = 0
    for rec in read_log(path):
        assert shift_log_line(rec.line, rec.ts) == rec.line
        n += 1
    assert n == 601  # 커밋된 불변 데이터 — 0줄을 통과시키지 않기 위한 하한이자 실측값


def test_thrift_identity_on_real_log():
    """THRIFT 줄은 Code_Stop 의 ComposePostService_.log 에만 있다 (200줄)."""
    path = scen_dir("log", "Code_Stop_MediaService") + "ComposePostService_.log"
    hits = [r for r in read_log(path) if r.line.startswith("Thrift: ")]
    assert len(hits) == 200
    for rec in hits:
        assert shift_log_line(rec.line, rec.ts) == rec.line


def test_nginx_identity_on_real_log():
    path = scen_dir("log", "Code_Stop_MediaService") + "NginxThrift_.log"
    n = 0
    for rec in read_nginx(path):
        assert shift_nginx_line(rec.line, rec.ts) == rec.line
        n += 1
    assert n == 200


def test_metric_csv_identity_on_real_data():
    path = scen_dir("metric", "Perf_CPU_Contention") + "socialnet_container_cpu.csv"
    src = read_csv(path, "timestamp")
    n = 0
    for rec in src.rows:
        assert shift_csv_line(rec.line, 0, rec.ts) == rec.line
        n += 1
    assert n > 100


def test_trace_csv_identity_on_real_data():
    """start_time 은 5번 컬럼이고, 뒤따르는 tags 필드에 쉼표와 이스케이프 따옴표가 들어 있다."""
    path = scen_dir("trace", "Perf_CPU_Contention") + "all_traces.csv"
    src = read_csv(path, "start_time")
    n = 0
    for rec in src.rows:
        assert shift_csv_line(rec.line, 5, rec.ts) == rec.line
        n += 1
    assert n > 1000


# --- 렌더링: 실제 시프트 ---------------------------------------------------------


def test_boost_shift_replaces_only_timestamp():
    """줄 뒷부분에 같은 문자열이 또 있어도 맨 앞 것만 바뀐다 — str.replace() 였다면 둘 다 바뀐다."""
    line = "[2025-Nov-03 22:28:07.123456] <info>: req at [2025-Nov-03 22:28:07.123456]\n"
    out = shift_log_line(line, datetime(2026, 7, 16, 16, 5, 1, 42, tzinfo=UTC))
    assert out == "[2026-Jul-16 16:05:01.000042] <info>: req at [2025-Nov-03 22:28:07.123456]\n"


def test_boost_without_micros_stays_without_micros():
    """계획 함정 6 — 3종 통틀어 3줄. 없이 들어온 줄은 없이 나간다."""
    line = "[2025-Nov-03 22:28:07] <info>: (SocialGraphHandler.h:106:Follow) Received\n"
    out = shift_log_line(line, datetime(2026, 7, 16, 16, 5, 1, 42, tzinfo=UTC))
    assert out == "[2026-Jul-16 16:05:01] <info>: (SocialGraphHandler.h:106:Follow) Received\n"


def test_line_without_timestamp_passes_through():
    line = "    at SomeStackFrame(foo.cc:12)\n"
    assert shift_log_line(line, datetime(2026, 7, 16, tzinfo=UTC)) == line


def test_thrift_pads_day_with_space():
    """C asctime 은 일자를 공백으로 폭 2 채운다 — `Nov  4`, `Nov 14`."""
    line = "Thrift: Tue Nov  4 02:58:25 2025 TSocket::open() connect() <Host: media-service>\n"
    out = shift_log_line(line, datetime(2026, 7, 6, 1, 2, 3, tzinfo=UTC))
    assert out.startswith("Thrift: Mon Jul  6 01:02:03 2026 TSocket")
    out2 = shift_log_line(line, datetime(2026, 7, 16, 1, 2, 3, tzinfo=UTC))
    assert out2.startswith("Thrift: Thu Jul 16 01:02:03 2026 TSocket")


def test_nginx_shift():
    line = '2025/11/04 02:58:25 [error] 20#20: upstream timed out, host: "localhost:8080"\n'
    out = shift_nginx_line(line, datetime(2026, 7, 16, 16, 5, 1, tzinfo=UTC))
    assert out == '2026/07/16 16:05:01 [error] 20#20: upstream timed out, host: "localhost:8080"\n'


def test_metric_csv_shift_keeps_no_micros():
    line = '2025-11-03 22:27:07,0.0069,"container_label=""cadvisor""",cadvisor\n'
    out = shift_csv_line(line, 0, datetime(2026, 7, 16, 16, 5, 1, 999, tzinfo=UTC))
    assert out == '2026-07-16 16:05:01,0.0069,"container_label=""cadvisor""",cadvisor\n'


def test_trace_csv_shift_keeps_micros_and_quoted_field():
    line = (
        'abc,def,ghi,home-timeline-service,read_home,2025-11-03 22:43:20.922164,15,,,,,'
        '"{""internal.span.format"": ""proto"", ""a"": 1}",\n'
    )
    out = shift_csv_line(line, 5, datetime(2026, 7, 16, 16, 5, 1, 42, tzinfo=UTC))
    assert "2026-07-16 16:05:01.000042" in out
    assert out.endswith('"{""internal.span.format"": ""proto"", ""a"": 1}",\n')
    assert out.count(",") == line.count(",")


# --- CSV 필드 스팬 --------------------------------------------------------------


def test_csv_field_span_skips_quoted_commas():
    line = 'a,"b,c,d",e\n'
    assert line[slice(*csv_field_span(line, 0))] == "a"
    assert line[slice(*csv_field_span(line, 1))] == '"b,c,d"'
    assert line[slice(*csv_field_span(line, 2))] == "e\n"


def test_csv_field_span_handles_escaped_quotes():
    line = 'a,"say ""hi"", ok",e\n'
    assert line[slice(*csv_field_span(line, 1))] == '"say ""hi"", ok"'


def test_csv_field_span_rejects_missing_field():
    with pytest.raises(ValueError, match="필드 9 없음"):
        csv_field_span("a,b,c\n", 9)


# --- 모달리티 정렬 (계획 0-3 / 함정 4) --------------------------------------------


@pytest.mark.parametrize("prefix", SCENARIOS)
def test_shift_preserves_modality_offsets(prefix):
    """세 모달리티에 같은 t0 을 쓰면 시프트 후에도 모달리티 간 편차가 원본과 같다."""
    mins = _modality_mins(prefix)
    t0 = measure_t0(mins.values())
    anchor = datetime(2026, 7, 16, 16, 0, 0, tzinfo=UTC)
    shifted = {k: shift_ts(v, t0, anchor) for k, v in mins.items()}

    assert shifted["log"] == anchor  # log 가 가장 이르다
    lag = (shifted["trace"] - shifted["log"]).total_seconds()
    assert lag == pytest.approx(TRACE_LAG[prefix], abs=0.1)
    for k in mins:
        assert (shifted[k] - anchor) == (mins[k] - t0)


@pytest.mark.parametrize("prefix", SCENARIOS)
def test_t0_is_measured_not_folder_name(prefix):
    """폴더명 시각을 t0 으로 쓰면 안 된다 (계획 함정 4) — 실측 min 과 다르다."""
    folder = glob.glob(f"datasets/sn/log_data/{prefix}_*/")[0].replace("\\", "/").rstrip("/")
    stamp = folder.split("/")[-1][len(prefix) + 1 :][:15]  # YYYYmmdd_HHMMSS
    folder_ts = datetime.strptime(stamp, "%Y%m%d_%H%M%S").replace(tzinfo=UTC)

    t0 = measure_t0(_modality_mins(prefix).values())
    assert t0 != folder_ts
    assert t0 > folder_ts  # 수집 시작 후에 첫 줄이 찍힌다


def _modality_mins(prefix: str) -> dict[str, datetime]:
    logs = []
    for f in glob.glob(scen_dir("log", prefix) + "*_.log"):
        rd = read_nginx if "Nginx" in f else read_log
        ts = [r.ts for r in rd(f)]
        if ts:
            logs.append(min(ts))
    metrics = []
    for f in glob.glob(scen_dir("metric", prefix) + "*.csv"):
        ts = [r.ts for r in read_csv(f, "timestamp").rows]
        if ts:
            metrics.append(min(ts))
    trace = read_csv(scen_dir("trace", prefix) + "all_traces.csv", "start_time")
    return {
        "log": min(logs),
        "metric": min(metrics),
        "trace": min(r.ts for r in trace.rows),
    }
