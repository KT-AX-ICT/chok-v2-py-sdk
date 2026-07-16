# collectors — ① 수집

원천 소스(log·metric·trace)를 관측해 **정규화 이전의 원시 레코드**를 산출한다.

- `base.Collector` — 모달리티별 tailer 가 구현하는 추상 인터페이스. `poll()` 이 관측 루프마다
  직전 이후 새로 유입된 원시 레코드를 순회 산출한다.
- `log.py` / `metric.py` / `trace.py` — 모달리티별 tailer 골격.

원시 → 표준 이벤트 변환은 다음 단계(`normalization/`)가 맡는다. 파일 포맷·tail 방식·산출 dict
필드는 구현 단계에서 팀이 원천 데이터에 맞춰 확정한다.

참고: [docs/architecture.md](../../../docs/architecture.md)
