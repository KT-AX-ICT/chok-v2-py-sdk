# buffer — ③ 버퍼

정규화 배치를 시간 기반 롤링 메모리 버퍼로 유지하고, 트리거 이후 스냅샷 조립이 구간 조회로
pre/post 를 가져가게 한다. 설계 근거는 [계획 04](../../../docs/plans/04-memory-buffer.md) 참조.

- `memory_buffer.MemoryBuffer(retention_sec)` — `append(NormalizedBatch)` / `get_snapshot(start, end)`
- **보존 기간은 pre 윈도가 아니라 pre + post 를 담을 만큼 주입받는다** (기본 390 =
  `buffer_window_sec` 210 + `post_trigger_wait_sec` 180, 주입은 Runner 소관). 버퍼는 pre/post
  의미를 모르고 "얼마나 오래 들고 있을지"만 안다 — 정책은 `snapshot/` 소관.
  210 만 두면 post 조회 여유가 1 tick 뿐이라 finalize 가 조금만 밀려도 조용히 잘린다 (계획 04 §1).
- 축출 기준은 벽시계가 아니라 **watermark**(관측된 `observed_until` 최대값). 재생 정지·시계
  어긋남에도 버퍼가 스스로 비지 않는다. 임계값과 정확히 같은 시각의 레코드는 유지한다.
- `get_snapshot` 은 반열림 `[start, end)` 필터 → `model_copy(deep=True)` 독립 복사본 →
  timestamp 오름차순 정렬. 배치 내 레코드는 파일 단위로 읽혀 시간순이 아니므로 여기서 정렬한다.
- `coverage` 는 구간과 겹치는 배치들의 roster 를 source 별로 접은 것 —
  `present`=OR, `record_count`=합계. 레코드 0건 배치도 이력에 남아 empty 판정 재료가 된다.

참고: [ADR-001](../../../docs/decisions/ADR-001-snapshot-window.md),
[docs/snapshot-contract.md](../../../docs/snapshot-contract.md)
