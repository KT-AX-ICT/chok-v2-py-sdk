# runtime — 오케스트레이션

파이프라인 전 단계를 관측 루프로 묶는다. 한 tick:

```
collectors.poll → normalization → buffer.add
  → trigger 감지·수렴
  → 발화 시: snapshot 조립 → transport 전송 / 미발화 시: 관찰 지속
```

- `runner.Runner` — `tick()`(1회 사이클) / `run()`(루프). 현재 스텁.

루프 주기는 `config.loop_interval_sec` 로 설정한다. 각 단계 인스턴스 구성은 구현 단계에서 채운다.

참고: [docs/architecture.md](../../../docs/architecture.md)
