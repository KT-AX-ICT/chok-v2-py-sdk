# ADR-007 — SnapshotManager 설계

- 상태: 확정
- 날짜: 2026-07-19
- 관련: 인터페이스 계약 §2.5, [ADR-001](ADR-001-snapshot-window.md)(스냅샷 윈도), [ADR-004](ADR-004-replayer-data-layout.md)(모달리티 동기 tail), [ADR-006](ADR-006-trigger-detectors.md)(트리거 detector)

## 맥락

트리거(`TriggerDetector`)는 "언제·어느 모달리티가 이상인지"(`TriggerEvidence`)만 낸다. 실제 RCA 분석에 필요한 건 그 시점 **앞뒤 원본 관측 데이터**다. `SnapshotManager`는 트리거 시각(anchor)을 중심으로 Pre(앞 3분 30초)/Post(뒤 3분)를 버퍼에서 떠 하나의 `SnapshotBundle`로 조립해 전송 계층에 넘긴다.

## 결정

### 인터페이스 (계약 §2.5, 고정)

```python
class SnapshotManager:
    def register_triggers(self, evidences: list[TriggerEvidence], buffer: MemoryBuffer) -> None: ...
    def finalize_ready(self, observed_until: datetime, buffer: MemoryBuffer) -> list[SnapshotBundle]: ...
```

### 1. register / finalize 2단계

번들은 트리거 즉시 못 만든다 — Post(뒤 3분)가 아직 안 쌓였기 때문.
- **register_triggers** (트리거 발화 시, 이벤트): 최초 `trigger_time`을 anchor로 세션을 열고 **Pre를 즉시 캡처**. 버퍼는 롤링(오래된 것 축출)이라 지나면 Pre 구간이 사라지므로 즉시 캡처가 핵심.
- **finalize_ready** (매 30초 틱, 타이머): `observed_until >= window_end`면 **Post를 캡처**해 번들 완성 후 세션 종료.

### 2. 단일 활성 세션 + window 고정

- 동시에 세션 **1개**. 최초 트리거가 열고, 창이 닫힐 때까지 재트리거는 같은 세션에 누적. finalize 후 종료 → 다음 트리거는 새 세션. **한 인시던트 = 번들 1개.**
- `window_start = anchor - 180초`, `window_end = anchor + 180초`(앞뒤 대칭). **재트리거로 연장·재anchor 안 함**(§2.5).
- Pre를 210초로 두는 비대칭 안은 **보류·검증 중**이다. `anchor = 발단 + 탐지 지연`이라 지연이 Pre만 갉아먹는다는 논거인데, 실측 전이라 대칭을 유지한다. 경위와 철회된 근거는 [ADR-001 §비대칭 검토](ADR-001-snapshot-window.md) 참조.
- 재트리거는 `triggered_by`(발화 모달리티)에 누적. anchor·window·Pre는 최초 값 고정.

### 3. 반열림 창 — anchor 중복 방지

- Pre = `get_snapshot(window_start, anchor)` = `[window_start, anchor)`
- Post = `get_snapshot(anchor, window_end)` = `[anchor, window_end)`
- anchor 경계 레코드가 **정확히 한 번만** 담긴다. Pre가 Post보다 앞서므로 이어붙이면 시간순.

### 4. finalize = 단일 watermark

- `observed_until` 하나로 "언제 닫을지"만 판단. `get_snapshot`이 버퍼에 있는 것만 반환하므로 per-modality가 자동 처리.
- 이 시스템은 러너가 매 틱 metric/log/trace를 같은 시각에 poll → 3모달리티 `observed_until`이 동기 진행(ADR-004). 계약의 **"개별 기준 / 느린 모달리티 안 기다림"은 여기선 no-op** — 셋이 window_end에 같이 도달해 Post가 잘리지 않는다.

### 5. `BundleRecord.raw` = 정규화 레코드 JSON

버퍼는 정규화 레코드(`NormalizedLog/Trace/Metric`)만 쥔다(원본 raw 필드는 스키마에 없음). 따라서 `raw`에 **정규화 레코드를 `model_dump_json()`으로 직렬화**해 담는다 — 중앙 RCA는 정규화 데이터를 받는다. `service = canonical_service`.

### 6. `modality_info` 3상태 (완성)

coverage(roster)를 Pre+Post로 접되 규칙은 버퍼의 윈도 집계와 동일하게 **present=OR, count=합계**.
`count>0 → "data"`, `count==0 & present → "empty"`, `count==0 & !present → "missing"`.
`present`와 `record_count`가 **둘 다** 있어야 missing(파일 부재)과 empty(파일은 있고 0건)가 갈린다.
coverage 비면 빈 dict.

### 7. window 폭은 상수

`PRE_SEC = POST_SEC = 180`(모듈 상수). config(`buffer_window_sec`/`post_trigger_wait_sec`) 주입은 후속 — 현재 `SnapshotManager`에 주입 경로가 없어 두 값이 드리프트할 수 있고, 테스트가 상수와 config가 같은지 핀으로 고정한다.

## 결과/영향

- `src/rca_sdk/snapshot/assembler.py` — `SnapshotManager` + `_CaptureSession`(dataclass) + `_rec`/`_modality_info` 헬퍼. `snapshot/__init__.py`는 기존 export 유지.
- 검증: 단위 13 테스트 통과, `ruff`·`mypy` 클린. `MemoryBuffer` 구현 후에도 **의도적으로 FakeBuffer 대역을 쓴다** — SnapshotManager가 계약(`get_snapshot`)에만 의존함을 보이기 위함.
- `_CaptureSession.evidences`는 계약 §2.5 "evidence 취합"용으로 누적하나, 현재 `SnapshotBundle/TriggerInfo`에 evidence 필드가 없어(미래 `TriggerInfo.raw` 예약) 번들엔 안 실린다 — 향후 소비용 보관.

## 미결

- **러너 통합** — 매 틱 `evaluate → register_triggers`, `finalize_ready(observed_until)` 호출. observed_until = 러너 루프 watermark.
- **Transport 연동** — finalize가 낸 번들을 `Transport.send`로.
- **window 설정화** — `PRE_SEC`/`POST_SEC` 상수 → config 주입(§7).
- **재트리거 다중 세션** — 현재 단일 세션. 인시던트가 짧게 반복되면 재검토(MVP 밖).
- **지속형 이상의 세션 재개 — §2 "한 인시던트 = 번들 1개"가 깨진다.** detector가 무상태라 이상이 지속되는 동안 매 틱 발화하는데, finalize로 세션이 닫히면 다음 틱 발화가 **새 세션을 연다**. 재현: CPU plateau 345초([ADR-006](ADR-006-trigger-detectors.md) 실측 23샘플×15초) → anchor만 60초씩 밀린 **번들 5개**가 거의 같은 구간을 중복 전송. MVP 3종 중 `Perf_CPU_Contention`이 이 케이스다. 선택지 — ⓐ finalize 후 쿨다운 동안 같은 `detector_type` 무시, ⓑ detector에 발화 억제 상태 부여(무상태 원칙 깨짐), ⓒ 현 동작을 인정하고 중앙에서 dedup.
