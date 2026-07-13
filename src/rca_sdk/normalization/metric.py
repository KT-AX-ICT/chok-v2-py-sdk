"""메트릭 원시 샘플 → NormalizedEvent (스캐폴드)."""

from __future__ import annotations

from typing import Any

from rca_sdk.schemas.events import NormalizedEvent


def normalize_metric(raw: dict[str, Any]) -> NormalizedEvent:
    # TODO: name/value/timestamp 추출. docs/data-schema.md 확정 후 구현.
    raise NotImplementedError("normalize_metric 스캐폴드")
