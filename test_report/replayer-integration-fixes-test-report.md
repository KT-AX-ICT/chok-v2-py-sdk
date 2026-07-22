# 리플레이어 실연동 준비 — 수정 3건 테스트 리포트

> 대상: `demo/replayer` 실물 통합(계획 06) 준비 중 발견한 문제 3건과 그 수정
> 브랜치: `feat/replayer-e2e-run`
> 실행일: 2026-07-22

## 배경

`demo/replayer`(`origin/feat/replayer`, 옛 브랜치)를 현재 `main` 위에 가져와 붙이는 과정에서,
"리플레이어가 쓴 실물 파일 → 실제 tailer → 실제 normalizer" 경로를 코드로 직접 추적하다가
기존 `test_report/scenario-replay-report.md`(가짜 컬렉터 기반)에는 드러나지 않았던 문제 3건을
찾았다. 전부 TDD로 고쳤다.

## 실행 환경·명령

| 항목 | 값 |
|---|---|
| 명령 | `uv run pytest tests/ demo/replayer/tests -q` |
| 플랫폼 | Windows (win32), Python 3.11.9, pytest 9.1.1 |
| 결과 | SDK `tests/`: **231 passed** (28.4s) · `demo/replayer/tests`: **94 passed** (47.0s) — 실패·스킵 없음 |
| 린트 | `ruff check` / `ruff format --check` 전부 clean |

---

## ① 경로 검증이 구현만 되고 배선이 안 되어 있던 문제

`validate_source_layout()`(`src/rca_sdk/collectors/tail.py`)은 이미 구현·단위테스트까지 있었지만,
`README.md`에 "호출은 Runner 소관"이라 적혀 있으면서 정작 `build_runner()`가 부르지 않고 있었다.
`source_root`가 없어도 `rca-collect`가 예외 없이 0건만 관측하며 조용히 돌아, "경로 오류"와
"이상 없음"이 구분되지 않는 상태였다.

| 테스트 | 검증 내용 | 결과 |
|---|---|---|
| `test_raises_on_missing_source_layout`(신규) | `source_root` 하위 log/metric/trace 부재 시 `build_runner()`가 `SourceLayoutError`로 즉시 실패 | ✅ |
| `test_wires_three_modalities` | 3개 모달리티 컬렉터 배선 (기존, `source_root` fixture로 이관) | ✅ |
| `test_buffer_uses_configured_retention` | 버퍼 보존값 배선 (기존, 이관) | ✅ |
| `test_normalizers_get_expected_services` | normalizer 에 expected_services 주입 (기존, 이관) | ✅ |
| `test_detectors_get_conditions_from_settings` | detector 조건값 배선, ADR-006 확정치 (기존, 이관) | ✅ |
| `test_every_configured_condition_reaches_a_detector` | 조건만 있고 detector 안 다는 실수 방지 (기존, 이관) | ✅ |
| `test_transport_targets_configured_endpoint` | transport 엔드포인트 배선 (기존, 이관) | ✅ |
| `test_tick_on_empty_source_root_is_quiet` | 레이아웃은 있는데 파일이 없으면 예외 없이 빈 tick (기존) | ✅ |

수정: `runner.py:127`에 `validate_source_layout(settings.source_root)` 한 줄 추가. 기존 6개 테스트가
레이아웃 없는 `tmp_path`로 `build_runner()`를 부르고 있어서 같이 깨졌으나, 검증 자체를 완화하는
대신 각 테스트가 유효한 레이아웃을 만들도록 `source_root` fixture로 고쳐 통과시켰다.

---

## ② Thrift 포맷 로그 200줄이 실제 파이프라인에서 조용히 드롭되던 문제

`ComposePostService_.log`(Code_Stop_MediaService 시나리오, 1001줄 중 200줄)에 boost/nginx
어느 쪽에도 안 맞는 C asctime 포맷(`Thrift: Tue Nov  4 02:58:25 2025 ...`)이 있는데,
`LogNormalizer`가 이 형식을 몰라서 전부 드롭하고 있었다. `readers.py`(리플레이어)는 이미 이
형식을 인식해서 재생 충실도는 지키고 있었지만, 그다음 단계인 정규화가 못 받아준 것.

기존 `scenario-replay-report.md`에 이 드롭이 안 보였던 건 그 리포트가 쓰는 가짜 하네스
(`tests/replay/harness.py`)의 자체 타임스탬프 정규식도 이 포맷을 인식 못 해, 애초에
"시각 없는 줄"로 판정돼 드롭 집계 대상(`raw_polled`)에도 못 들어갔기 때문 — 실제 파일 기준
경로를 처음 추적하면서 드러난 맹점이었다.

| 테스트 | 검증 내용 | 결과 |
|---|---|---|
| `test_thrift_line_parsed`(신규) | 실측 Thrift 포맷 줄 → 서비스명/시각/메시지 정상 추출, `level`/`code_loc`는 표기가 없어 `None` | ✅ |
| `test_boost_line_parsed` | boost 포맷 회귀 없음 | ✅ |
| `test_nginx_line_parsed_anonymous_resolve_host` | nginx 포맷 회귀 없음 | ✅ |
| `test_connect_target_extracted` | 대상 서비스 추출 회귀 없음 | ✅ |
| `test_unparseable_line_skipped` | 셋 다 안 맞는 진짜 해석 불가 줄은 여전히 스킵 (N3 유지) | ✅ |

수정: `log.py`에 `_THRIFT_RE` 추가, `_normalize_record`를 boost/nginx/thrift 3분기로 정리.
실측 검증: 실제 `ComposePostService_.log` 파일(1001줄)을 직접 정규화 — **수정 전 200줄 드롭 →
수정 후 0줄 드롭.** ADR-003이 지목한 실제 detector 신호(`NginxThrift_.log`의
"Could not resolve host")와는 무관한 파일이라 발화 결과에는 영향 없음 — 순수하게 이 파일의
증거가 유실되던 것만 고친 것.

---

## ③ `--reset`이 디렉터리째 지워서 `validate_source_layout()`과 충돌하던 문제

①을 고친 뒤, 다른 팀원이 제안한 "리셋을 rca-collect보다 먼저 실행"하는 순서를 검토하던 중
발견. `demo/replayer/writer.py: reset()`이 `shutil.rmtree()`로 모달리티 디렉터리를 **통째로**
지우고, `Writer.open()`이 실제로 쓸 때(모달리티마다 첫 데이터 시점이 다름 — trace는
t0+126초까지 지연)에야 다시 만든다. 리셋을 먼저 실행하는 순서에서는 그 사이 `rca-collect`가
뜨면 아직 안 생긴 모달리티 디렉터리 때문에 ①에서 추가한 `SourceLayoutError`로 바로 크래시한다
— ①과 팀원 제안을 합쳤을 때만 드러나는 상호작용 문제였다.

| 테스트 | 검증 내용 | 결과 |
|---|---|---|
| `test_reset_clears_modality_dir_contents`(계약 변경) | 리셋 후 내용은 비되, 디렉터리 자체는 즉시 재생성 | ✅ |
| `test_reset_keeps_run_history_and_other_entries` | `.replay/`·무관 파일은 그대로, `log/`는 빈 디렉터리로 남음 | ✅ |
| `test_reset_on_first_run_creates_empty_dirs`(계약 변경) | `var/`가 한 번도 없던 첫 실행도 리셋 한 번으로 3개 디렉터리 즉시 생성 | ✅ |
| `test_reset_never_removes_source_root` | `source_root` 자체는 안 건드림 (회귀 없음) | ✅ |
| `test_reset_then_write_starts_clean` | 리셋 반복 후에도 정상 append (회귀 없음) | ✅ |

수정: `reset()`에 `d.mkdir(parents=True, exist_ok=True)` 한 줄 추가 — 지우고 바로 빈 채로
재생성. 실제 데이터 삭제 범위(내용)는 그대로고, 삭제 후 디렉터리 골격이 즉시 복원된다는 것만
바뀐다. `src/rca_sdk`(배포 wheel 대상)는 전혀 안 건드림 — 변경 범위는 `demo/replayer`(테스트
툴링)에 한정.

---

## 관찰 사항

- coverage 판정(missing/empty/data)에서, 원본이 0바이트인 소스(`kill_media`/`cpu`의
  `NginxThrift_.log`)는 **실제 리플레이어 경로에서는 파일 자체가 안 생겨 "missing"**으로
  관측된다 — `demo/replayer/tests/test_integration.py:73-76`에 `assert not out_path.exists()`로
  이미 명시돼 있다. 기존 `scenario-replay-report.md`는 원본 파일을 직접 읽는 가짜 컬렉터 기준이라
  같은 케이스를 "empty"로 기록했다. 계획 06 §6 리포트를 실물로 재작성할 때 이 표기 차이가
  버그가 아니라 경로 차이에서 오는 것임을 미리 알아둬야 한다.
- ③의 수정은 코드 레벨 검증(단위테스트)까지만 했다 — `rca-collect`와 `demo.replayer` 두 프로세스를
  실제로 동시에 띄워 순서를 바꿔가며 확인하는 실물 E2E는 아직 안 함(계획 06 §4 몫).

## 커버리지 관점 정리

이번에 건드린 세 갈래(경로 검증 배선·Thrift 정규화·reset 디렉터리 재생성) 모두 회귀 테스트로
고정됐고, SDK 전체 스위트(231)·리플레이어 전체 스위트(94) 다 통과한다. 의도적으로 남겨둔 것:
실제 두 프로세스(`rca-collect`+`demo.replayer`) 동시 실행 기반 E2E 검증 — 이건 계획 06 §4의
수동 시나리오 3종 실행에서 다뤄질 예정이다.
