"""최소 사용 예제 (스캐폴드).

동작하는 코어(buffer/correlation)만 시연한다. collectors~runner 는 구현 후 확장.
"""

from __future__ import annotations

from datetime import UTC, datetime

from rca_sdk.buffer import MemoryBuffer
from rca_sdk.schemas.events import Modality, NormalizedEvent
from rca_sdk.trigger.correlation import correlate
from rca_sdk.trigger.models import Candidate, ModalitySignal


def main() -> None:
    buf = MemoryBuffer(window_sec=210)
    buf.add(
        NormalizedEvent(
            modality=Modality.TRACE,
            timestamp=datetime.now(UTC),
            service="media-service",
            attributes={"status": 500},
        )
    )
    print("buffer size:", len(buf))

    cand = Candidate(service="media-service", signal="trace_5xx", value=70, baseline=0)
    sig = ModalitySignal(modality="trace", triggered=True, candidates=[cand])
    signals = [sig]
    for inc in correlate(signals):
        print(f"incident suspect={inc.suspect_service} corr={inc.corroboration} score={inc.score}")


if __name__ == "__main__":
    main()
