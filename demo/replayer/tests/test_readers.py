"""리플레이어 리더 테스트 (계획 01 Phase 1 검증).

실데이터(`datasets/sn/`)로 확인한다. 새 fixture 파일은 만들지 않는다 (ADR-004).
합성 데이터가 필요하면 `tmp_path` 를 쓴다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from demo.replayer.readers import parse_boost, read_csv, read_log, read_nginx

# ADR-004 — 경로는 CWD(저장소 루트) 기준으로 푼다. `parents[N]` 로 루트를 계산하지 않는다.
DATASETS = Path("datasets/sn")
SCENARIOS = ("Perf_CPU_Contention", "Svc_Kill_Media", "Code_Stop_MediaService")


def scenario_dir(modality: str, prefix: str) -> Path:
    # 폴더명에 타임스탬프가 붙어 exact match 가 아니다 → 접두어로 찾는다.
    (found,) = sorted(DATASETS.joinpath(modality).glob(f"{prefix}_*"))
    return found


def raw_line_count(path: Path) -> int:
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
        return sum(1 for _ in f)


def test_parse_boost_handles_missing_microseconds():
    # 함정 6 — `.%f` 없는 변형이 실데이터에 2건 있다. 파서가 죽으면 재생이 통째로 멈춘다.
    assert parse_boost("2025-Nov-03 22:28:07.123456").microsecond == 123456
    assert parse_boost("2025-Nov-03 22:28:07").microsecond == 0


def test_parse_boost_is_utc_aware():
    # log/metric 은 타임존 표기가 물리적으로 없다 → UTC 를 명시 부여한다 (계획 0-2).
    assert parse_boost("2025-Nov-03 22:28:07").tzinfo is not None


def test_parse_boost_rejects_unknown_format():
    with pytest.raises(ValueError):
        assert parse_boost("2025/11/03 22:28:07")


def test_read_log_line_count_matches_source():
    # 검증 — 3종 시나리오 각각에서 리더 산출 줄 수 == 원본 파일 줄 수
    for prefix in SCENARIOS:
        for path in sorted(scenario_dir("log_data", prefix).glob("*_.log")):
            reader = read_nginx if path.name.startswith("Nginx") else read_log
            assert sum(1 for _ in reader(path)) == raw_line_count(path), path


def test_read_log_lines_are_byte_identical_to_source():
    # 검증 — 산출한 줄이 원본 줄과 바이트 동일 (줄바꿈 포함, 변환 없음)
    path = scenario_dir("log_data", "Perf_CPU_Contention") / "MediaService_.log"
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
        assert [r.line for r in read_log(path)] == list(f)


def test_read_log_timestamps_are_tz_aware_and_parsed_from_line_head():
    path = scenario_dir("log_data", "Perf_CPU_Contention") / "MediaService_.log"
    for record in read_log(path):
        assert record.ts.tzinfo is not None
        # 줄을 해석하지 않는다 — 시각만 파싱하고 줄은 통째로 들고 간다.
        assert record.line.startswith(f"[{record.ts.strftime('%Y-%b-%d')}")


def test_read_log_missing_file_yields_nothing():
    # 함정 2 — Code_Stop 은 MediaService_.log 자체가 없다 (서비스가 죽어서). 예외 아님.
    path = scenario_dir("log_data", "Code_Stop_MediaService") / "MediaService_.log"
    assert not path.exists()
    assert list(read_log(path)) == []


def test_read_log_reads_thrift_lines_in_boost_file():
    # 계획 0-2 표에 없는 3번째 변형 — Code_Stop 의 ComposePostService_.log 200행이
    # C asctime 포맷이다. BOOST 만 쓰면 전량 유실돼 줄 수 검증이 깨진다.
    path = scenario_dir("log_data", "Code_Stop_MediaService") / "ComposePostService_.log"
    thrift = [r for r in read_log(path) if r.line.startswith("Thrift: ")]
    assert len(thrift) == 200
    assert all(r.ts.tzinfo is not None for r in thrift)


def test_read_nginx_empty_file_yields_nothing():
    # 함정 2 — Perf_CPU / Svc_Kill 의 NginxThrift_.log 는 0바이트다. 예외 아님.
    path = scenario_dir("log_data", "Perf_CPU_Contention") / "NginxThrift_.log"
    assert path.stat().st_size == 0
    assert list(read_nginx(path)) == []


def test_read_nginx_parses_error_log_format():
    # 함정 1 — NginxThrift_.log 만 nginx error_log 포맷이다. 단일 파서 가정 시 200행 전량 유실.
    path = scenario_dir("log_data", "Code_Stop_MediaService") / "NginxThrift_.log"
    records = list(read_nginx(path))
    assert len(records) == 200 == raw_line_count(path)
    assert all(r.ts.tzinfo is not None for r in records)
    assert records[0].line.startswith(records[0].ts.strftime("%Y/%m/%d %H:%M:%S"))


def test_read_csv_row_count_matches_source_excluding_header():
    # 검증 — CSV 는 헤더 제외한 줄 수가 원본과 같아야 한다 (metric 15 + trace 1, 3종 전부)
    for prefix in SCENARIOS:
        for path in sorted(scenario_dir("metric_data", prefix).glob("*.csv")):
            source = read_csv(path, "timestamp")
            assert sum(1 for _ in source.rows) == raw_line_count(path) - 1, path

        path = scenario_dir("trace_data", prefix) / "all_traces.csv"
        source = read_csv(path, "start_time")
        assert sum(1 for _ in source.rows) == raw_line_count(path) - 1, path


def test_read_csv_returns_header_separately():
    # 계획 0-1 — 라이터가 헤더를 먼저 써야 하므로 헤더는 행과 분리해 돌려준다.
    path = scenario_dir("metric_data", "Perf_CPU_Contention") / "system_cpu_usage.csv"
    source = read_csv(path, "timestamp")
    assert source.header == "timestamp,value,metric,instance\n"
    # 헤더는 행에 섞여 나오지 않는다.
    assert all("timestamp,value" not in r.line for r in source.rows)


def test_read_csv_metric_rows_are_utc_aware_and_byte_identical():
    path = scenario_dir("metric_data", "Perf_CPU_Contention") / "system_cpu_usage.csv"
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
        raw = list(f)[1:]  # 헤더 제외
    records = list(read_csv(path, "timestamp").rows)
    assert [r.line for r in records] == raw
    assert all(r.ts.tzinfo is not None for r in records)
    assert records[0].line.startswith(records[0].ts.strftime("%Y-%m-%d %H:%M:%S"))


def test_read_csv_trace_start_time_keeps_microseconds():
    # trace 의 start_time 은 `%Y-%m-%d %H:%M:%S.%f` 이고 UTC 임이 전수 대조로 확정됐다 (계획 0-2).
    path = scenario_dir("trace_data", "Perf_CPU_Contention") / "all_traces.csv"
    source = read_csv(path, "start_time")
    assert source.header is not None and source.header.startswith("trace_id,span_id")
    first = next(source.rows)
    assert first.ts.tzinfo is not None
    assert first.ts.strftime("%Y-%m-%d %H:%M:%S.%f") in first.line


def test_read_csv_does_not_sort_and_keeps_source_order():
    # 함정 3 — all_traces.csv 는 시간순이 아니다. 리더는 정렬하지 않고 원본 순서를 유지한다
    # (정렬은 스케줄러의 병합 몫 — Phase 4). 첫 행을 t0 으로 쓰면 안 된다는 근거.
    path = scenario_dir("trace_data", "Perf_CPU_Contention") / "all_traces.csv"
    timestamps = [r.ts for r in read_csv(path, "start_time").rows]
    assert timestamps != sorted(timestamps)
    assert min(timestamps) < timestamps[0]


def test_read_csv_missing_file_yields_no_header_and_no_rows():
    # 함정 2 — 파일 존재를 가정하지 않는다.
    source = read_csv(DATASETS / "metric_data" / "does_not_exist.csv", "timestamp")
    assert source.header is None
    assert list(source.rows) == []


def test_read_csv_empty_file_yields_no_header_and_no_rows(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    source = read_csv(path, "timestamp")
    assert source.header is None
    assert list(source.rows) == []


def test_read_csv_finds_ts_column_by_name_not_position(tmp_path):
    # 시각 컬럼이 첫 컬럼이 아니어도 이름으로 찾는다 (trace 의 start_time 은 6번째 컬럼).
    path = tmp_path / "m.csv"
    path.write_bytes(b"a,timestamp\n1,2025-11-03 22:26:39\n")
    records = list(read_csv(path, "timestamp").rows)
    assert len(records) == 1
    assert records[0].ts.hour == 22
    assert records[0].ts.tzinfo is not None


def test_read_csv_keeps_quoted_commas_in_line_intact(tmp_path):
    # 줄을 해석하지 않는다 — 따옴표 안의 쉼표가 있어도 줄은 통째로 보존된다.
    line = '2025-11-03 22:26:39,1,"instance=""node"",x"\n'
    path = tmp_path / "q.csv"
    # write_bytes — write_text 는 Windows 에서 \n 을 \r\n 으로 바꿔 원본이 아니게 된다.
    path.write_bytes(("timestamp,value,metric\n" + line).encode())
    assert [r.line for r in read_csv(path, "timestamp").rows] == [line]


def test_readers_are_lazy_generators():
    # 함정 5 — 27MB 파일이 있다. 전량 리스트 적재 없이 첫 줄만 꺼낼 수 있어야 한다.
    path = scenario_dir("log_data", "Perf_CPU_Contention") / "SocialGraphService_.log"
    assert path.stat().st_size > 20_000_000
    first = next(read_log(path))  # 통째로 읽었다면 여기서 오래 걸린다
    assert first.ts.tzinfo is not None
