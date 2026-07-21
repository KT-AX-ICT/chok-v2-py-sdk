# runtime — 관측 루프

30초 주기로 파이프라인을 한 바퀴 돌린다. 설계 근거는
[계획 05](../../../docs/plans/05-runner-scenario-replay.md).

- `runner.Runner` — 구성요소를 **주입받는다**(`sources`·`buffer`·`detectors`·`snapshot`·`transport`).
  `tick()` 이 1회 사이클, `run()` 이 sleep 루프.
- `runner.build_runner(settings)` — Settings 만으로 실운용 Runner 를 조립한다.
  배선의 정답(어떤 detector 를 어떤 condition 으로, 보존값은 얼마로)을 여기 한 곳에 둔다.

## tick 순서가 계약이다

```
poll → normalize → buffer.append
     → snapshot.finalize_ready       ← evaluate 앞이어야 한다
     → detector.evaluate(since=...)
     → snapshot.register_triggers
     → transport.send                ← 마지막이어야 한다
```

- **`append` 가 먼저** — 창 기반 detector(`cpu_spike`·`restart_marker`)가 버퍼를 되돌아본다.
- **`finalize_ready` 가 `evaluate` 앞** — 이 틱에 완성된 번들의 창 끝이 곧 이번 평가의
  하한(`since`)이다. 뒤집으면 방금 전송한 구간으로 즉시 재발화한다
  ([계획 04 §7-3](../../../docs/plans/04-memory-buffer.md)).
- **`send` 가 마지막** — 전송이 실패해도 `_detect_since` 는 이미 전진해 있다. 같은 번들을
  무한 재시도하지 않는다. 실패는 경고 로그로만 남는다.

순서는 `tests/test_runner.py` 가 호출 로그로 고정한다.

## `_detect_since` 는 Runner 만 안다

번들 이력을 아는 유일한 계층이다. detector 는 시각 하나만 받아 무상태를 유지하고(ADR-006),
`SnapshotManager` 는 세션 1건의 생애만 안다.

post 대기 3분 동안은 이 값이 필요 없다 — `register_triggers` 가 재트리거를 기존 세션에
흡수하므로 새 번들 자체가 안 생긴다. 세션이 닫히는 순간 갱신되고, 그때부터 의미가 생긴다.

| 구간 | 재발화를 막는 장치 |
|---|---|
| 트리거 ~ 번들 완성 | `SnapshotManager` 단일 세션 슬롯 |
| 번들 완성 이후 | `_detect_since` = 번들 창 끝 |

## detector condition

임계는 코드에 박지 않고 `Settings.trigger_conditions` 로만 주입한다(계약 §0-5).
값 근거는 [ADR-006](../../../docs/decisions/ADR-006-trigger-detectors.md) 실측.
`DETECTOR_TYPES` 매핑과 키가 짝이 맞아야 하며, 어긋나면 `tests/test_runner_wiring.py` 가 잡는다.

참고: [docs/architecture.md](../../../docs/architecture.md),
[ADR-005](../../../docs/decisions/ADR-005-sdk-structure.md)
