# Collector(tailer) 테스트 리포트

> 대상: `tests/test_collectors.py` → `src/rca_sdk/collectors/` (JsonlTailCollector)
> 브랜치: `feat/tailer-normalization-buffer` (커밋 `64d5db5` 구현, `2d1d146` 견고성 보강)
> 실행일: 2026-07-19

## 실행 환경·명령

| 항목 | 값 |
|---|---|
| 명령 | `uv run pytest tests/test_collectors.py -v` |
| 플랫폼 | Windows (win32), Python 3.11.9, pytest 9.1.1 |
| 결과 | **16 passed** in 0.42s (실패·스킵 없음) |
| 테스트 데이터 | `tmp_path` 픽스처로 매 테스트 즉석 생성 — 커밋된 fixture 파일 없음 (ADR-004) |

참고: 전체 스위트는 26 passed, `ruff check` clean (푸시 시점 기준).

## 테스트별 결과

### 기본 동작

| 테스트 | 검증 내용 | 결과 |
|---|---|---|
| `test_empty_dir_returns_empty_batch` | 빈 디렉터리 poll → 예외 없이 records/sources 모두 빈 배치 | ✅ |
| `test_reads_lines_and_tags_source` | JSONL 2줄 읽기 + 각 레코드에 `_source`(파일명) 주입 + `sources` 목록 (C2) | ✅ |
| `test_offset_continues_between_polls` | 두 번째 poll 은 byte offset 이후의 **신규 줄만** 읽음 (C1) | ✅ |
| `test_each_collector_owns_its_subdir` ×3 | Log/Metric/Trace 서브클래스가 각자 `log/`·`metric/`·`trace/` 하위만 담당 + modality 배선 | ✅ ✅ ✅ |

### 경계 상황 방어

| 테스트 | 검증 내용 | 결과 |
|---|---|---|
| `test_incomplete_last_line_deferred` | 개행 없는 마지막 줄(리플레이어가 쓰는 도중)은 미소비 → 다음 poll 에서 완성본 읽기 | ✅ |
| `test_zero_byte_file_listed_in_sources` | 0바이트 파일도 `sources` 포함 + 0건 — empty 판정 재료 (Perf_CPU 의 nginx 실측 재현) | ✅ |
| `test_bad_json_line_skipped` | 깨진 JSON 줄만 warning 스킵, 앞뒤 정상 줄은 소비 (C7) | ✅ |
| `test_truncated_file_reread_from_start` | 파일 크기 < offset (`rca-replay --reset` 재실행) → offset 리셋 후 처음부터 재독 | ✅ |
| `test_new_file_appearing_mid_run` | 가동 중 새 파일 등장(서비스 재시작) → offset 기본 0 으로 자연 수용 | ✅ |

### 관측 구간·견고성 (검토에서 발견한 이슈 A·B)

| 테스트 | 검증 내용 | 결과 |
|---|---|---|
| `test_observed_window_is_continuous` | 배치 N 의 `observed_until` == 배치 N+1 의 `observed_from` (C4, buffer watermark 가 기대는 연속성) | ✅ |
| `test_file_deleted_between_glob_and_read` | **이슈 A** — 나열과 읽기 사이 파일 삭제 레이스가 poll 전체를 죽이지 않고, 해당 파일만 이번 관측에서 제외 | ✅ |
| `test_first_poll_window_starts_at_creation` | **이슈 B** — 첫 poll 관측 구간이 폭 0 이 아니라 [생성 시각, poll 시각] | ✅ |

### 기동 검증 헬퍼

| 테스트 | 검증 내용 | 결과 |
|---|---|---|
| `test_validate_source_layout_ok` | 정상 레이아웃(log/metric/trace 존재) → 예외 없음 | ✅ |
| `test_validate_source_layout_missing_dir_raises_with_paths` | 하위 디렉터리 부재 → `SourceLayoutError` 에 해석된 절대경로 + CWD 포함 (ADR-004) | ✅ |

## 관찰 사항

- `test_bad_json_line_skipped`·`test_file_deleted_between_glob_and_read` 실행 중 캡처된
  `logging.warning` 은 **의도된 동작** (스킵 사실을 로그로 남기는 설계 C7)이며 실패가 아님.
- Windows 콘솔(cp949)에서 pytest 캡처 로그의 한글 메시지가 깨져 보이는 현상이 있으나
  출력 인코딩 문제일 뿐 테스트 판정과 무관.

## 커버리지 관점 정리

구현(`tail.py`)의 분기 전부에 대응 테스트가 존재한다:
offset 조회·이어읽기 / truncate 감지 / 미완성 줄 유예 / 빈 줄·깨진 JSON·비-dict 스킵 /
`_source` 주입 / sources 집계(0건 포함) / OSError 파일 단위 스킵 / 관측 구간 산출(첫 poll 포함) /
레이아웃 검증 성공·실패.

의도적으로 테스트하지 않은 것: offset 영속화(미구현이 설계 — 재시작 재독 허용),
동시성 실부하(개행 경계 방어로 대체), 필드 의미 해석(normalizer 소관 — 계획 02 경계).
