# buffer — ③ 버퍼

정규화 배치를 시간 기반 롤링 메모리 버퍼로 유지하고, 트리거 이후 스냅샷 조립이 구간 조회로
pre/post 를 가져가게 한다. 설계 근거는 [계획 04](../../../docs/plans/04-memory-buffer.md) 참조.

- `memory_buffer.MemoryBuffer(retention_sec)` — `append(NormalizedBatch)` / `get_snapshot(start, end)`
- **보존 기간 = `PRE_SEC(180) + 루프 주기(30) = 210`** (`Settings.buffer_window_sec` 와 동일).
  pre 와 post 는 **시점이 다른 별개 질의**라 더해지지 않는다 — `snapshot/` 이 트리거 시점에
  pre 를 즉시 복사하고, post 는 3분 뒤 따로 떠 간다. 두 질의 각각의 요구가 210 으로 수렴한다
  (유도표: 계획 04 §1). 여유는 각각 1 틱이라, 넓히려면 `retention_sec` 만 올린다.
  버퍼는 pre/post 의미를 모르고 "얼마나 오래 들고 있을지"만 안다.
- 축출 기준은 벽시계가 아니라 **watermark**(관측된 `observed_until` 최대값). 재생 정지·시계
  어긋남에도 버퍼가 스스로 비지 않는다. 임계값과 정확히 같은 시각의 레코드는 유지한다.
- `get_snapshot` 은 반열림 `[start, end)` 필터 → `model_copy(deep=True)` 독립 복사본 →
  timestamp 오름차순 정렬. 배치 내 레코드는 파일 단위로 읽혀 시간순이 아니므로 여기서 정렬한다.
- `coverage` 는 구간과 겹치는 배치들의 roster 를 source 별로 접은 것 —
  `present`=OR, `record_count`=합계. 레코드 0건 배치도 이력에 남아 empty 판정 재료가 된다.

참고: [ADR-001](../../../docs/decisions/ADR-001-snapshot-window.md),
[docs/snapshot-contract.md](../../../docs/snapshot-contract.md)
