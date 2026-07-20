# 스냅샷 번들 계약

`schemas/snapshot.py` 의 `SnapshotBundle`. 트리거 발화 시 1회 생성·전송한다.

## 윈도 구성 (ADR-001 에서 확정)

```
      ┌──────── pre (버퍼: ~3분 30초) ────────┐ ▲ 트리거 ┌── post (3분) ──┐
 ─────┤ ... 정규화 이벤트 롤링 버퍼 ...        ├─┼───────┤ 계속 수집       ├────▶ 시간
      └──────────────────────────────────────┘ │       └─────────────────┘
                                              발화 시점
```

- `pre_events`  = 트리거 직전 pre 윈도(`PRE_SEC`, 180초) 내용 — 버퍼 보존(`RCA_BUFFER_RETENTION_SEC`, 210초)과는 다른 값
- `post_events` = 발화 후 `RCA_POST_TRIGGER_WAIT_SEC`(기본 180초) 동안 추가 수집

## 필드

| 필드 | 설명 |
|---|---|
| `bundle_id` | 번들 UUID |
| `trigger` | `TriggerInfo` (발화시각·모달리티·suspect·score) |
| `window_start` / `window_end` | 포함 이벤트의 시간 범위 |
| `pre_events` / `post_events` | 정규화 이벤트 목록 |
