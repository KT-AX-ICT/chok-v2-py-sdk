# tail 개편 · normalization · buffer 테스트 리포트

> 대상: `tests/test_collectors.py`(개편) · `tests/test_normalization_common.py`(신규) ·
> `tests/test_normalizers.py`(신규) · `tests/test_buffer.py`(신규)
> 설계: [계획 03](../docs/plans/03-tail-rework-normalization.md) ·
> [계획 04](../docs/plans/04-memory-buffer.md)
> 실행일: 2026-07-19 · 브랜치 `feat/tailer-normalization-buffer`

## 실행 환경·전체 결과

| 항목 | 값 |
|---|---|
| 명령 | `uv run pytest` / `uv run ruff check .` |
| 플랫폼 | Windows (win32), Python 3.11.9, pytest 9.1.1 |
| 결과 | **96 passed** (collectors 23 · normalization_common 29 · normalizers 18 · buffer 16 · smoke 10), lint clean |
| 테스트 데이터 | tmp_path·인라인 픽스처 (SN 실측 라인/행 축약, fixture 파일 커밋 없음 — ADR-004) |

이전 리포트(collector-test-report.md, JSONL 가정 16종)는 리플레이어 실구현 확인으로
**계획 03 기준 테스트로 대체**되었다.

## 1. collectors (23) — 원본 라인/CSV tail

### 공통 tail 동작 (LogCollector 로 검증)

| 테스트 | 입력 (I) | 기대 출력 (O) | 결과 |
|---|---|---|---|
| empty_dir_returns_empty_batch | 빈 log/ 디렉터리 | records=[] · sources=[] | ✅ |
| log_line_wrapped_as_raw | `MediaService_.log` 에 boost 라인 1줄 | `[{"raw": 원본라인, "_source": "MediaService_.log"}]` | ✅ |
| offset_continues_between_polls | poll① 후 2줄 추가 append | poll② 는 신규 2줄만 | ✅ |
| incomplete_last_line_deferred | `"done\npartial"` (개행 없는 끝) | poll① `["done"]` → 개행 완성 후 poll② `["partial"]` | ✅ |
| zero_byte_file_listed_in_sources | 0바이트 `NginxThrift_.log` (Perf_CPU 실측) | sources 포함 + records=[] (empty 재료) | ✅ |
| blank_line_skipped | `"a\n\n \nb\n"` | `["a", "b"]` (공백 줄 무시) | ✅ |
| truncated_file_reread_from_start | 2줄 소비 후 파일을 1줄로 truncate (--reset) | offset 리셋, `["fresh"]` 재독 | ✅ |
| non_log_extension_ignored | `summary.txt` (재생 대상 아님) | sources·records 모두 제외 | ✅ |
| observed_window_is_continuous | 연속 poll 2회 | poll①.until == poll②.from | ✅ |
| new_file_appearing_mid_run | 가동 중 새 파일 등장 | 자연 수용 (offset 0 부터) | ✅ |
| file_deleted_between_glob_and_read | stat 시점 FileNotFoundError 주입 | 예외 없이 완료, 해당 파일만 관측 제외 | ✅ |
| first_poll_window_starts_at_creation | 생성 20ms 후 첫 poll | observed_from < observed_until (폭 0 아님) | ✅ |
| validate_source_layout_ok / missing | 정상 레이아웃 / metric·trace 부재 | 통과 / `SourceLayoutError`(절대경로+CWD) | ✅✅ |

### CSV 프레이밍 (CsvTailCollector)

| 테스트 | 입력 (I) | 기대 출력 (O) | 결과 |
|---|---|---|---|
| csv_header_consumed_and_rows_dicted | 헤더+행 1개 (`socialnet_container_cpu.csv` 실측형) | 헤더는 레코드 아님, 행은 `{timestamp: "…", value: "0.006794", …}` | ✅ |
| csv_header_remembered_across_polls | poll② 에 행만 append (헤더 없음) | 기억한 헤더로 dict 프레이밍 계속 | ✅ |
| csv_header_only_file_is_empty_source | 헤더만 있는 파일 | sources 포함 + records=[] (empty 재료) | ✅ |
| csv_quoted_comma_field | tags `"{""a"": 1, ""b"": 2}"` (인용 콤마) | `tags == '{"a": 1, "b": 2}'` 한 필드로 유지 | ✅ |
| csv_column_mismatch_skipped | 4컬럼 헤더 + `"1,2"` 불량 행 + 정상 행 | 불량 행만 스킵, 정상 행 1건 | ✅ |
| csv_truncate_relearns_header | truncate 후 다른 헤더(`ts,v`)로 재작성 | 새 헤더 재학습 → `{"ts": "1", "v": "2", …}` | ✅ |
| each_collector_owns_its_subdir ×3 | log/metric/trace 각 하위 디렉터리 | 담당 modality·파일만 처리 | ✅✅✅ |

## 2. normalization common (29)

### canonical_service — 스펙 §1-1 표 전체 (파라미터 21종)

| 입력 (I) | 출력 (O) |
|---|---|
| `UserService` · `user-service` | `user` |
| `SocialGraphService` · `social-graph-service` | `socialgraph` |
| `NginxThrift` · `nginx-thrift` · `nginx-web-server` | `nginx` (ALIASES) |
| `MediaService_` (로그 파일명 stem) · `media-service` | `media` |
| unique-id·url-shorten·user-mention·user-timeline·home-timeline·post-storage·compose-post·text | 접미사 제거형 12종 전부 일치 |
| `user-mongodb` · `social-graph-mongodb` · `url-shorten-memcached` | 인프라 예외 — 특수문자만 제거 유지 |
| `None` | `None` |

### parse_timestamp — 3계열 + naive 보장 (8종)

| 입력 (I) | 출력 (O) | 결과 |
|---|---|---|
| `2025-Nov-04 00:01:57.490560` (boost 마이크로초) | `datetime(2025,11,4,0,1,57,490560)` | ✅ |
| `2025-Nov-04 00:01:57` (boost 초) | `datetime(2025,11,4,0,1,57)` | ✅ |
| `2025/11/04 02:58:25` (nginx) | `datetime(2025,11,4,2,58,25)` | ✅ |
| `2025-11-04 00:02:21` (metric CSV) | `datetime(2025,11,4,0,2,21)` | ✅ |
| `2025-11-04 00:20:00.521000` (trace CSV) | `datetime(2025,11,4,0,20,0,521000)` | ✅ |
| `2025-11-04T00:02:21+09:00` (tz 포함) | tz **변환 없이 버림** → naive 00:02:21 (C6) | ✅ |
| aware datetime 객체 | naive 로 (동일 시각) | ✅ |
| `"not-a-time"` | `ValueError` | ✅ |

모든 출력은 `tzinfo is None` 단언 포함 (naive 보장).

## 3. normalizers (18)

### LogNormalizer — {"raw": 라인} 입력

| 테스트 | 입력 (I) | 기대 출력 (O) | 결과 |
|---|---|---|---|
| boost_line_parsed | 실측 boost `Starting the media-service…` 라인 (`MediaService_.log`) | service=`media` · log_type=`service_log` · level=`info` · code_loc=`MediaService.cpp:44` · **event_type=`service_start`** (restart_marker 원천) | ✅ |
| nginx_line_parsed_anonymous_resolve_host | 실측 nginx `Could not resolve host` 라인 | service=`nginx` · log_type=`nginx_log` · level=`error` · code_loc=`compose.lua:62` · event_type=`connection_error` · **target_service=None** (익명 — Code_Stop 신호 보존) | ✅ |
| connect_target_extracted | `Could not connect to media-service:9090` | event_type=`connection_error` · **target_service=`media`** | ✅ |
| unparseable_line_skipped | 타임스탬프 없는 줄 + 정상 줄 | 불량 줄만 스킵, 1건 산출 (N3) | ✅ |
| window_preserved | 빈 배치 | observed_from/until 원본 유지 | ✅ |

### MetricNormalizer — CSV 컬럼 dict 입력

| 테스트 | 입력 (I) | 기대 출력 (O) | 결과 |
|---|---|---|---|
| container_metric_normalized | `socialnet_container_cpu.csv` 행 (dimension=`user-service`) | service=`user` · metric_name=`container_cpu` (socialnet_ 제거) · value=0.006794 · unit=`fraction` | ✅ |
| system_metric_is_node | `system_cpu_usage.csv` 행 (instance=`node-exporter:9100`) | **service=`__node__`** (cpu_spike 원천) · unit=`percent` | ✅ |
| unknown_dimension_service_none | `jaeger_spans_rate.csv` 행 (양쪽 컬럼 없음) | service=None · unit=None | ✅ |
| bad_metric_value_skipped | value=`"?"` | 행 스킵, records=[] (N3) | ✅ |

### TraceNormalizer — all_traces.csv 컬럼 dict 입력

| 테스트 | 입력 (I) | 기대 출력 (O) | 결과 |
|---|---|---|---|
| trace_row_normalized | 실측 13컬럼 행 (service=`nginx-web-server`, duration_us=490, 공백 다수) | service=`nginx` · duration_ms=0.49 · 공백 parent/status/logs → None · tags JSON 파싱 | ✅ |
| trace_status_code_parsed | http_status_code=`"500"` | **500 (int)** — trace_5xx 신호 원천 | ✅ |
| trace_bad_tags_kept_as_empty_dict | tags=`"{broken"` | tags={} + warning (행은 유지) | ✅ |
| trace_missing_start_time_skipped | start_time=`""` | 행 스킵 (N3) | ✅ |

### roster + Settings (5)

| 테스트 | 입력 (I) | 기대 출력 (O) | 결과 |
|---|---|---|---|
| log_roster_missing_empty_data | expected=[media,nginx,text] · sources=[Text,Nginx] · text 1건 | **media=(False,0) missing** · nginx=(True,0) empty · text=(True,1) data — Code_Stop 실측 재현 | ✅ |
| metric_roster_includes_node | expected=[user] · container+system 파일 존재 | user=(True,1) · **__node__=(True,0) 자동 포함** | ✅ |
| trace_roster_single_artifact | all_traces.csv 존재, nginx 행 1건 | nginx=(True,1) · media=(True,0) — 단일 아티팩트 규칙 | ✅ |
| trace_roster_missing_when_no_file | sources=[] | nginx=(False,0) | ✅ |
| settings_default_expected_services | `Settings()` 기본값 | canonical 12종 (media·nginx 포함) | ✅ |

## 4. buffer (16) — MemoryBuffer

시각은 전부 고정 기준시 `T0`에서 만든 naive datetime이다. **실제 벽시계를 쓰지 않는 것 자체가
"축출 기준은 watermark이지 벽시계가 아니다"(B3)를 보장한다.** 아래 표의 `at(n)`은 `T0 + n초`.

### 적재·조회

| 테스트 | 입력 (I) | 기대 출력 (O) | 결과 |
|---|---|---|---|
| records_within_window_returned | 배치[0,30] 레코드 at(10)·at(20) | 조회[0,30) → `[at(10), at(20)]` | ✅ |
| window_is_half_open | 레코드 at(10)·at(20)·at(30), 조회 `[10, 30)` | **start 포함·end 제외** → `[at(10), at(20)]` | ✅ |
| empty_window_returns_empty_snapshot | 조회 구간에 레코드 없음 | `logs == []` | ✅ |
| records_sorted_by_timestamp | 파일 순서로 at(50)→at(10)→at(30) 유입 | **timestamp 오름차순** `[10, 30, 50]` (B4) | ✅ |
| modalities_are_separated | log·metric·trace 각 1건 | `logs`/`metrics`/`traces` 각 1건 | ✅ |

### 축출 — watermark 기준 (B3)

| 테스트 | 입력 (I) | 기대 출력 (O) | 결과 |
|---|---|---|---|
| evicts_records_older_than_retention | retention=60, 레코드 at(10) 후 배치 until=90 | 임계 30 → at(10) **축출**, at(70) 유지 | ✅ |
| keeps_record_exactly_at_eviction_threshold | 레코드 at(30), 임계 정확히 30 | **경계값 유지** `[at(30), at(70)]` | ✅ |
| eviction_uses_watermark_not_wall_clock | 2025년 레코드, watermark 낮음 | 실제 현재가 2026이어도 **축출 안 됨** | ✅ |
| history_evicted_with_records | 배치[0,30] 후 배치[300,330] | 옛 구간 coverage 사라짐 | ✅ |

### coverage 집계 (B2)

| 테스트 | 입력 (I) | 기대 출력 (O) | 결과 |
|---|---|---|---|
| zero_record_batch_kept_in_coverage | 레코드 0건 배치 + roster(nginx present) | 이력 유지 → `(True, 0)` **empty 판정 재료** | ✅ |
| coverage_present_is_or_across_batches | 배치1 present=False, 배치2 present=True | **OR** → `present=True` | ✅ |
| coverage_record_count_is_summed | count 3 + count 5 | **합계** 8 | ✅ |
| coverage_excludes_batch_ending_at_window_start | 배치[0,30] count=10, 조회 `[30,60)` | `until == start`라 **제외** → count=0 (이중 계산 방지) | ✅ |
| coverage_three_states | roster media(F,0)·nginx(T,0)·text(T,7) | **missing·empty·data** 3상태 구분 | ✅ |

### 독립성 (deep copy)

| 테스트 | 입력 (I) | 기대 출력 (O) | 결과 |
|---|---|---|---|
| snapshot_records_are_deep_copies | 스냅샷 레코드의 `service` 변조 | 버퍼 원본 불변 → 재조회 시 `media` | ✅ |
| snapshot_unaffected_by_later_eviction | 스냅샷 취득 후 버퍼에서 해당 레코드 축출 | **이미 꺼낸 스냅샷은 그대로** `[at(10)]` | ✅ |

## 관찰 사항

- 스킵 경로 테스트(불량 JSON 컬럼·불량 값·해석 불가 줄)에서 잡히는 `logging.warning` 은
  전부 **의도된 동작** (계획 03 N3 — 스킵 사실을 로그로 남김).
- boost 영문월 파싱은 `strptime %b`(로케일 의존) 대신 월 매핑 테이블을 사용 —
  한국어 Windows 로케일에서도 결정적으로 동작.

## 커버리지 관점

- collectors: LineTailCollector 전 분기 (offset·미완성 줄·truncate·삭제 레이스·프레이밍 훅) +
  CsvTailCollector 헤더 생명주기 (학습→기억→truncate 재학습).
- normalization: 스펙 §1-1 표 전체 · §1-2 3계열 · §3 파생 필드 규칙(실측 트리거 신호 3종 원천
  포함) · §4 공백/JSON 처리 · §5 container/__node__ 구분 · §2 roster 3상태.
- buffer: 축출(임계·경계값·watermark 기준) · 반열림 구간 · 정렬 · deep copy 독립성 ·
  coverage 집계(OR·합계·겹침 경계·3상태) · 모달리티 분리.
- 의도적으로 안 한 것: 리플레이어 실출력 통합 검증(리플레이어 완성 후),
  Runner 배선(범위 밖 — 계획 02·04), 파이프라인 3계층 결합 시나리오 테스트.
