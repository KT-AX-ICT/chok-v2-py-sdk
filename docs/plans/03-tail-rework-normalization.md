# 계획 03 — 원본 형식 tail 개편 · normalization 구현 설계

리플레이어 실구현(팀원 PR: "타임스탬프만 파싱해 시각을 맞추고 **원본 줄을 그대로** 옮겨 쓴다 —
포맷·파일명·분할 불변")이 확인되면서, 계획 02 의 **JSONL 입력 가정이 깨졌다**. 이 문서는
그에 따른 collectors 개편과 normalization 구현 설계를 기록한다. 계획 02 의 결정 C1~C7 중
**입력 형식(D4 대응 전제)만 대체**하며 나머지(오프셋·roster·watermark·naive 시각·스킵 정책)는 유지한다.

- 브랜치: `feat/tailer-normalization-buffer`
- 정규화 규칙 원천: 정규화 스키마 V0.1 (기술문서), 트리거 신호: [ADR-003](../decisions/ADR-003-realtime-signal-scope.md)·[trigger-policy](../trigger-policy.md)

## §0. 확정된 입력 전제 (리플레이어 실구현 + 원본 실측)

`var/<모달리티>/<원본 파일명>` 에 원본 줄이 그대로 append 된다. 라인 내 타임스탬프 문자열만
치환되므로 **포맷은 원본과 동일**하다.

| 모달리티 | 파일 | 형식 (실측) |
|---|---|---|
| log | `<Service>_.log` ×11~12 (예 `MediaService_.log`), `NginxThrift_.log` | boost: `[2025-Nov-04 00:01:57.490560] <info>: (MediaService.cpp:44:main) Starting …` · nginx: `2025/11/04 02:58:25 [error] 9#9: *816 [lua] compose.lua:62: … Could not resolve host …` |
| metric | `socialnet_container_*.csv` ×4 · `system_*.csv` ×10 · `jaeger_spans_rate.csv` | 헤더 `timestamp,value,metric,<container_label_com_docker_compose_service \| instance>` · timestamp `2025-11-04 00:02:21` (초 단위) |
| trace | `all_traces.csv` 단일 (전 서비스) | 헤더 13컬럼 `trace_id,span_id,parent_span_id,service,operation,start_time,duration_us,http_status_code,http_method,http_url,component,tags,logs` · tags 는 콤마 포함 인용 JSON 문자열 |

- CSV 헤더는 **파일이 비어 있을 때만 1회** 기록된다(파일 맨 앞) — 상태를 가진 collector 만 잡을 수 있다.
- 서비스 로스터 실측 12종 (available_services.json): media · nginx(-web-server) · user · text ·
  unique-id · url-shorten · user-mention · user-timeline · home-timeline · post-storage ·
  compose-post · social-graph.
- ✅ `system_*.csv` 가 재생 범위에 **포함** 확인 — 계획 02 조율 항목 1(cpu_spike 신호 원천) 해소.

## 결정 사항

| # | 결정 | 근거 |
|---|---|---|
| N1 | collector 산출: **CSV 는 `{컬럼명: 값}` dict, log 는 `{"raw": 라인}`** | CSV 헤더는 offset 이어읽기 특성상 첫 배치에만 나타나므로 무상태 normalizer 는 볼 수 없다 — 헤더 기억은 상태를 가진 collector 소관. 구조 파싱(JSONL→dict 와 동급)까지가 collector 라는 기존 경계 유지. 라인 의미 해석(boost/nginx)은 normalizer |
| N2 | roster(SourceStatus) 단위: **canonical 서비스** (노드 지표는 `__node__`) | 소비자(trigger·snapshot)가 "media 침묵"을 모달리티 구분 없이 같은 방식으로 읽는다. 번들 fileName 은 missing 이면 `""` (스펙 허용) |
| N3 | 레코드 단위 파싱 실패는 skip + warning, record_count 는 성공분만 | C7 연장 — 한 줄 오염이 30초 루프를 멈추지 않는다 |
| N4 | 정규화 스키마 필드 명칭 `canonical_service` → **`service`** 로 통일 (값은 canonical 규칙 적용 결과 그대로) | 스키마 간 명칭 단순화. **schemas 공용 계약 필드 개명 — 팀 공유 필요** |

## §1. collectors 개편 — 기존 자산 유지, 프레이밍만 교체

byte offset 이어읽기 · 미완성 줄 유예 · truncate 복구 · 삭제 레이스 방어 · observed 구간 연속성은
**전부 그대로**. "라인 → 레코드" 부분만 바뀐다.

- `JsonlTailCollector` → **`LineTailCollector`** 개명. `json.loads` 자리에 서브클래스 훅
  `_frame(line, path) -> dict | None` 호출. `_source` 주입·sources 집계는 공통층 유지.
- **LogCollector**: glob `*.log`, `_frame` = `{"raw": 라인}` (해석 없음).
- **Metric/TraceCollector**: glob `*.csv`, 파일별 헤더 상태 `dict[파일명, list[컬럼]]` 추가 —
  offset 0 에서 읽은 첫 라인을 헤더로 기억하고 소비(레코드 아님). 이후 라인은 `csv.reader` 로
  1줄 파싱(인용 콤마 안전) → `{컬럼명: 값(str)}`. truncate 리셋 시 헤더도 리셋.
  컬럼 수 불일치 줄은 skip + warning (N3).
- 전제 1레코드=1줄: 리플레이어 자체가 줄 단위 재생이므로 성립 (인용 필드 내 개행 없음 — 실측 확인).
- 기존 테스트 15종은 파일명·내용만 실측형으로 재작성 (구조 유지).

## §2. normalization

### common

- `canonical_service()` — 스펙 §1-1: 소문자화 → 특수문자(`-`·`_` 등) 제거 → 인프라 키워드
  (mongodb · redis · memcached · rabbitmq) 포함 시 **여기서 정지** → `service` 접미사 제거 →
  `ALIASES`(`nginxwebserver`/`nginxthrift` → `nginx`) 적용. 실측 12종 전부 테이블 테스트.
- `parse_timestamp()` — boost 영문월(`2025-Nov-04 00:01:57[.490560]`, 마이크로초 유/무) ·
  nginx `2025/11/04 02:58:25` · 공백 ISO(`2025-11-04 00:02:21[.ffffff]`) → **naive** datetime.
  tz 가 들어오면 변환 없이 버린다 (계획 02 C6).

### LogNormalizer — `{"raw": 라인}` 입력

- `_source` 로 분기: `NginxThrift_.log` → `log_type="nginx_log"`, 그 외 → `"service_log"`.
- boost 정규식 `[ts] <level>: (file:line:func) message` → `code_loc` 은 `file:line` (func 제외, 스펙 예시 준수).
- nginx 정규식 `ts [level] pid#tid: *conn message` → `code_loc` 은 메시지 내 `*.lua:NN` 있으면 추출.
- `event_type`: 메시지 `Starting` 시작 → `service_start` (**restart_marker 원천**) /
  `Could not resolve host` · `Could not connect` · `TTransportException` 포함 → `connection_error` /
  그 외 `normal_log`.
- `target_service`: `Could not connect to <name>:<port>` 패턴에서만 canonical 추출.
  **익명 resolve-host 는 None 유지** — "익명 연결 실패"가 Code_Stop 신호라는 실측(ADR-003)과 일치.
- `service` 필드는 파일명에서: `MediaService_.log` → `media`, `NginxThrift_.log` → `nginx` (N4).

### MetricNormalizer — 컬럼 dict 입력

- `metric_name` = 파일명 stem 에서 `socialnet_` 접두 제거 (`container_cpu`, `system_cpu_usage`).
- `dimension` = 마지막 컬럼 값 (`container_label…` 값 또는 `node-exporter:9100`).
- `service` 필드 = container_label 계열이면 canonical 변환, `instance` 계열(system_*)은 `__node__`,
  둘 다 아니면(예 `jaeger_spans_rate.csv`) None.
- `unit` = 상수 테이블 (`container_cpu: fraction`, `system_cpu_usage: percent`, 미정의 None). `value` float 변환.

### TraceNormalizer — 컬럼 dict 입력

컬럼 직행 매핑: `service` 컬럼→canonical 변환해 `service` 필드로, `start_time`→timestamp, `duration_ms = duration_us/1000`,
공백 `http_status_code`/`parent_span_id` → None, `tags`/`logs` JSON 파싱 (실패 시 원본 유지).

### roster 산출 (N2)

expected = Settings `RCA_EXPECTED_SERVICES` + metric 은 `__node__` 자동 추가.
출력 `SourceStatus(source=canonical, present, record_count=서비스별 정규화 성공 행수)`.
missing = expected 인데 present 아님 / empty = present 인데 0건 / data = 1건 이상.

| 모달리티 | present 규칙 |
|---|---|
| log | 해당 서비스 파일이 `batch.sources` 에 존재 (파일명→canonical 매핑) |
| metric | 서비스: `socialnet_container_*` 존재 · `__node__`: `system_*` 존재 |
| trace | `all_traces.csv` 존재 (전 서비스 공통) |

## §3. Settings 추가

`RCA_EXPECTED_SERVICES: list[str]` — canonical 목록. 기본값 실측 12종:
`media, nginx, user, text, uniqueid, urlshorten, usermention, usertimeline, hometimeline, poststorage, composepost, socialgraph`.

## §4. 문서·계약 여파 (조율 항목 갱신)

1. ~~리플레이어 system_* 제외 충돌~~ → **해소 확인** (§0). 팀원 PR 에서 최종 확인만.
2. ADR-004 의 `var/{log,metric,trace}/<service>.jsonl` 레이아웃 서술이 실구현과 다름 —
   리플레이어 담당자와 공동 갱신 필요 (원본 파일명·원본 형식으로).
3. `RawBatch.sources` 계약(C2)·`SourceStatus.source=canonical`(N2) 공유는 유지.
   추가: 정규화 스키마 필드 개명 `canonical_service` → `service` (N4) — schemas 공용 계약 변경 공유.
4. collectors 개편은 본 브랜치에 추가 커밋으로 반영.

## §5. 테스트 전략 (TDD)

| 대상 | 케이스 |
|---|---|
| collector 재작성 | 기존 15종 실측형 전환 + CSV 헤더 기억 · 헤더만 있는 파일(=0건) · 인용 콤마 행 · 컬럼 수 불일치 · truncate 후 헤더 재학습 |
| canonical_service | 실측 12종 표 + 인프라 예외 (`user-mongodb→usermongodb`) |
| parse_timestamp | boost 마이크로초 유/무 · nginx · 공백 ISO · naive 보장 |
| LogNormalizer | boost/nginx 라인 파싱 · event_type 3종 · 익명 resolve-host 는 target None · code_loc |
| MetricNormalizer | container→canonical · system→`__node__` · unit 테이블 · value 변환 |
| TraceNormalizer | 실측 헤더 행 → 스키마 일치 · 공백 필드 None · tags JSON 파싱 |
| roster | missing(Code_Stop media) / empty(0바이트 nginx) / data 3상태 · metric `__node__` |
