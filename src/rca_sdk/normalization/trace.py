"""트레이스 원시 span → NormalizedEvent (스캐폴드)."""

from __future__ import annotations

from typing import Any

from rca_sdk.schemas.events import NormalizedEvent


def normalize_trace(raw: dict[str, Any]) -> NormalizedEvent:
    # TODO: span_id/duration_us/status/service 추출. docs/data-schema.md 확정 후 구현.
    raise NotImplementedError("normalize_trace 스캐폴드")
