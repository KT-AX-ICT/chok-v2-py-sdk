# ADR-005 — rca_sdk SDK 구조 & 인터페이스 정리

- 상태: 확정
- 날짜: 2026-07-15

RCA 엣지 수집기 SDK 패키지 구조 요약. log·metric·trace를 30초 주기로 관측하다가, 각 trigger 조건에
이상이 걸리면 pre/post-trigger 스냅샷 번들을 조립해 중앙 FastAPI 수집 API로 전송한다. (정상 구간은 미전송)

현재 상태: **인터페이스 계약 확정 + 스캐폴드** — 시그니처/타입은 고정, 내부 로직은 담당자별 구현 예정.


## 패키지 구조 (`src/rca_sdk/`)

| 경로 | 계층 | 역할 | 핵심 인터페이스 |
|---|---|---|---|
| `schemas/` | 계약 | 정규화·전송 데이터 계약(중심 허브) | `RawBatch`, `NormalizedLog/Trace/Metric`, `SourceStatus`, `NormalizedBatch`, `MultimodalSnapshot`, `SnapshotBundle`, `SubmissionResult` |
| `collectors/` | ① 수집 | log/metric/trace tail → 원시 배치 | `Collector.poll() -> RawBatch` |
| `normalization/` | ② 정규화 | 원시 → 모달리티별 정규화 스키마. 소스 present/missing 판정 전담 | `Normalizer.normalize(RawBatch) -> NormalizedBatch` |
| `buffer/` | ③ 버퍼 | 3분 30초 롤링 윈도 유지, 구간 조회 | `MemoryBuffer.append(batch)` / `get_snapshot(start,end) -> MultimodalSnapshot` |
| `trigger/` | ④ 트리거 | 각 trigger 조건으로 이상 감지 → 낱개 근거 | `TriggerDetector.evaluate(new_batch, buffer) -> list[TriggerEvidence]` |
| `snapshot/` | ⑤ 스냅샷 | 트리거 이후 pre/post 윈도 lifecycle 관리·번들 조립 | `SnapshotManager.register_triggers(...)` / `finalize_ready(...) -> list[SnapshotBundle]` |
| `transport/` | ⑥ 전송 | 번들을 FastAPI 수집 API로 POST | `Transport.send(bundle) -> SubmissionResult` |
| `runtime/` | 루프 | 위 전부를 30초 주기로 오케스트레이션 | `Runner.run()` |
| `config.py` | — | 설정 로드(`RCA_` env / `.env`) | `Settings` |
| `cli.py` | — | `rca-collect` 콘솔 진입점 | `main()` |

각 폴더의 `__init__.py`는 그 계층의 공개 API(위 인터페이스)를 re-export 한다.

> correlation·baseline은 설계상 엣지 제외(§0-4/§0-5)라, 관련 파일(`trigger/correlation.py`,
> `trigger/baseline.py`, `resources/baselines/`)과 죽은 코드(옛 트리거 모델·`baseline_profile`)를 **삭제**했다.
> 상세는 현행 리포트(노션에서 확인).

> 원천 데이터는 리플레이어가 `var/{log,metric,trace}/<service>.jsonl`(JSONL)로 공급하고 collector가 tail 한다.
> 경로·레이아웃은 [ADR-004](ADR-004-replayer-data-layout.md), 설정은 `RCA_SOURCE_ROOT`(=`./var`)·`RCA_DATASET_ROOT`(=`./datasets/sn`).

## 핵심 설계 결정 (요약)

- 모든 경계는 **`abc.ABC`** 로 계약 고정 → 각자 병렬 구현해도 통합 충돌 최소화
- 모달리티 **수렴(correlation)은 엣지에서 안 함** → 낱개 근거만 전송, 수렴·근본원인 판정은 중앙 RCA 담당
- 트리거 조건은 **각 trigger별 직접 지정** (정상구간 baseline 산출 안 함, ADR-002 대체)
- 실시간 detector: **`cpu_spike` / `trace_5xx` / `restart_marker`(svc_kill)** (ADR-003)
- 스냅샷: **최초 트리거 anchor ±3분 고정**, 재트리거는 같은 세션 누적 (ADR-001)
- 윈도 경계 **반열림 `[start, end)`**, 모든 시각 **`datetime`(naive)** 통일
- `SnapshotBundle`은 FastAPI 전송 형식으로 **고정**. `raw`는 **정규화 레코드를 JSON 문자열로 직렬화**(원본 라인은 안 들고 감)
- `raw_ref`·원본 라인 모두 **미보관** — 번들 `raw`엔 정규화 레코드를 직렬화해 담는다
- 소스 상태(`SourceStatus`)를 정규화가 `NormalizedBatch.roster`로 출력 → 버퍼 보관 → 스냅샷 윈도 집계로 번들 `modality_info`(missing/empty/data). `present`+`record_count`로 missing/empty 구분

## 남은 미확정

- `transport` 세부(재시도·백오프·인증·멱등키) — **서버 API 계약과 연동** 필요. 나머지 시그니처·타입·번들 형식은 확정.

## 참고 — 소소한 수정 (큰 문제 아님)

- **`examples/basic_sdk/main.py` 교체** — 삭제된 심볼(`correlation`·`NormalizedEvent`·옛 트리거 모델)을 참조해 CI Lint(ruff)가 실패했다. 새 계약(RawBatch→NormalizedBatch→SnapshotBundle) 구성 데모로 교체. *예제일 뿐 SDK 기능엔 영향 없음.*
- **테스트 교체** — 옛 correlation/baseline/버퍼 테스트가 삭제된 기능을 검증해 실패 → 계약 타입·경계 ABC 검증 스모크로 교체(§ pytest 10 passed).

## 참고 문서

> 아래 문서는 superpowers 내부 문서라 저장소에 포함하지 않는다 — **노션에서 확인**.
>
> - 인터페이스 계약 — 컴포넌트 입출력·타입·에러 처리 (확정)
> - 정규화 스펙 — canonical_service·timestamp·3개 스키마·roster_status
> - 현행 리포트 — 스캐폴드 적용 현황·미연결 파일
