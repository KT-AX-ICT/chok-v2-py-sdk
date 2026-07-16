# 계획 02 — collectors(tailer) · normalization · buffer

엣지 파이프라인의 ①수집 ②정규화 ③버퍼 계층 구현 설계. 인터페이스 계약은 ADR-005에서 확정된
것을 따르며, 이 문서는 그 내부 구현 방향과 계약 보완 1건을 기록한다.

- 브랜치: `feat/tailer-normalization-buffer` (base: `feat/interface-contracts`)
- 트리거 신호 근거: [ADR-003](../decisions/ADR-003-realtime-signal-scope.md), [trigger-policy](../trigger-policy.md)
- 입력 경로·레이아웃: [ADR-004](../decisions/ADR-004-replayer-data-layout.md) — `var/{log,metric,trace}/<service>.jsonl`

## 범위

**포함**: `collectors/`(JSONL tailer 3종), `normalization/`(3종 + common), `buffer/`(MemoryBuffer),
필요한 Settings 필드, 단위 테스트.

**범위 밖**: Runner 통합·기동 시 경로 검증 실행(ADR-004 — Runner 소관. 단 collector 가 검증 헬퍼를
제공한다), trigger/snapshot/transport, 리플레이어.

## 전제 — 리플레이어 D4(JSONL 필드 집합) 미결 대응

리플레이어 출력 레코드의 필드 집합이 미확정이므로:

- tailer 는 "파일에서 새 줄 → dict" 까지만 책임진다. 필드 집합을 몰라도 완성 가능.
- normalization 은 **모달리티별 필드 매핑 테이블**을 상수로 분리해, D4 확정 시 테이블만 수정한다.
- 검증은 리플레이어 실출력 대신 **테스트 픽스처 JSONL** 로 한다 (실측 포맷 — boost/nginx 타임스탬프,
  kebab 서비스명 — 을 그대로 축약). 리플레이어 완성 후 통합 검증을 추가한다.

## 결정 사항

| # | 결정 | 근거 |
|---|---|---|
| C1 | tailer 는 **파일별 byte offset** 을 인메모리로 기억하고 신규 라인만 읽는다 | 리플레이어가 append 로 쌓는 파일을 30초마다 이어 읽는 가장 단순한 방식 |
| C2 | `RawBatch.sources: list[str]` 필드 추가 + 레코드 dict 에 `_source`(파일명) 주입 | missing/empty 구분에 "파일 존재 정보"가 필요. 파일시스템 접근은 collector 에 가두고 판정 책임은 normalizer 전담 유지(ADR-005). **계약 변경 — 팀 공유 필요** |
| C3 | 기대 로스터는 **Settings**(`RCA_EXPECTED_SERVICES`, 기본값 SN 서비스 목록) | Code_Stop 처럼 파일이 처음부터 안 생기는 소스의 missing 판정에는 관측 밖 기준이 필요. 설정이면 TT 확장 시 값만 교체 |
| C4 | `observed_from/until` = 직전 poll 시각 ~ 현재 poll 시각 (벽시계, naive) | collector 가 레코드 timestamp 를 파싱하지 않기 위함(파싱은 정규화 소관). 리플레이어가 벽시계로 타임시프트하므로 poll 시각 ≈ 데이터 시각 |
| C5 | buffer 축출 기준은 벽시계가 아니라 **watermark**(관측된 `observed_until` 최대값) | 시계 어긋남·재생 정지에도 버퍼가 스스로 비워지지 않음. ADR-004 미결(배속 vs 윈도)에도 안전 |
| C6 | 모든 시각은 naive `datetime`. tz 정보가 들어오면 변환 없이 버린다 | ADR-005 §시각 통일, 정규화 스펙 §1-2(표시 형식 통일만) |
| C7 | JSON 파싱 실패 줄은 스킵하고 카운트만 남긴다 | 한 줄 오염이 30초 루프를 멈추면 안 됨 |

## ① collectors — `JsonlTailCollector`

세 모달리티가 동일한 tail 로직을 쓰므로 공통 구현 하나를 두고, `Log/Metric/TraceCollector` 는
modality 와 하위 디렉터리명만 지정한다.

```
poll() 한 번의 흐름:
1. <source_root>/<modality>/*.jsonl 나열 → sources (존재 파일명 목록)
2. 파일별 seek(offset) → 신규 완성 라인만 읽기 → json.loads → dict + "_source" 주입
3. offset 갱신. RawBatch(modality, observed_from, observed_until, records, sources) 반환
```

- **미완성 줄 방어**: 마지막 줄에 개행이 없으면(리플레이어가 쓰는 도중) 그 줄 시작으로 offset 을
  되돌리고 다음 poll 에서 다시 읽는다.
- offset 은 인메모리만 — SDK 재시작 시 처음부터 다시 읽는다. 데모 수명(수십 분)에서 영속화는 YAGNI.
- 경로 검증 헬퍼: 모달리티 디렉터리 부재 시 해석된 절대경로 + CWD 를 담아 실패하는 함수를 제공
  (호출은 Runner 소관, ADR-004 "디렉터리 부재 체크").

## ② normalization

- `common.canonical_service()` — 스펙 §1-1: 소문자화 → 특수문자 제거 → **인프라 키워드(mongodb ·
  redis · memcached 등) 포함 시 여기서 정지** → `service` 접미사 제거 → `ALIASES`(nginx) 적용.
- `common.parse_timestamp()` — naive 반환으로 보강(C6). boost 영문 월(`2025-Nov-04`, 마이크로초
  유무 2형) · nginx(`2025/11/04`) · ISO 계열을 처리한다.
- `Log/Metric/TraceNormalizer.normalize()` — 원시 dict → `NormalizedLog/Metric/Trace`.
  필드 매핑 테이블 상수 분리(D4 대응). log 는 스펙 §3 파생 필드까지:
  - `event_type`: `Starting …` → `service_start` / 연결 실패 패턴 → `connection_error` / 그 외 `normal_log`
  - `code_loc` · `target_service` 추출 (nginx 계열 연결 오류에서만)
  - **`restart_marker`(Svc_Kill) 와 Code_Stop 국소화가 이 필드들에 의존한다** — trigger-policy 참조.
- roster 산출: `기대 로스터(C3) × batch.sources(C2) × 소스별 레코드 수` →
  `SourceStatus(source, present, record_count)`. missing = 기대에 있는데 sources 에 없음,
  empty = present 인데 0건.

## ③ buffer — `MemoryBuffer`

- 내부: 모달리티별 `(timestamp, record)` 리스트 + 배치별 `(관측 구간, roster)` 이력.
- `append(batch)`: 레코드 적재, watermark 갱신, `watermark − window_sec` 이전 레코드·이력 축출(C5).
- `get_snapshot(start, end)`: 반열림 `[start, end)` 필터 → `model_copy(deep=True)` 독립 복사본,
  `coverage` = 구간과 겹치는 배치들의 roster 를 모달리티별로 집계한 `MultimodalSnapshot`.

## 테스트 전략 (TDD)

| 대상 | 케이스 |
|---|---|
| tailer | offset 이어읽기 · 미완성 줄 · 파일 부재(예외 없이 0건) · 0바이트 파일 · 파싱 실패 줄 스킵 |
| canonical_service | 스펙 §1-1 표 전체 (`UserService→user`, `nginx-thrift→nginx`, `user-mongodb→usermongodb`) |
| parse_timestamp | boost 마이크로초 유/무 · nginx 포맷 · naive 보장 |
| normalizer | 모달리티별 스펙 예시 레코드 → 스키마 일치, event_type/code_loc/target_service 규칙 |
| roster | missing / empty / data 3상태 각각 |
| buffer | watermark 축출 · 반열림 경계 `[start, end)` · deep copy 독립성 · coverage 집계 |
| 시나리오 픽스처 | SN오류정리 실측 패턴 축약 JSONL — `Starting` 2회(간격 보존) · 500 span · resolve-host 에러. detector 담당자 재사용 가능 |

## 팀 조율 항목 (구현과 병행)

1. ⚠️ **리플레이어가 `system_*.csv` 를 범위 밖으로 둔 것** — `cpu_spike` 의 신호 원천(host CPU
   plateau, `__node__`)이라 재생에 포함돼야 한다. 빠진 채면 Perf CPU 트리거가 성립 불가. **최우선.**
2. `RawBatch.sources` 계약 변경(C2) 공유 — schemas 는 공용 계약.
3. D4 제안 전달: "타임시프트된 `timestamp` + 모달리티 원본 필드 평탄화 + 한 줄 JSON".
4. 리플레이어 출력 타임스탬프의 tz 표기 여부 확인 (우리는 naive 로 통일, C6).
