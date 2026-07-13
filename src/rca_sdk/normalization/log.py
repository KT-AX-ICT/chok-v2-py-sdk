"""로그 원시 라인 → NormalizedEvent (스캐폴드)."""

from __future__ import annotations

from typing import Any

from rca_sdk.schemas.events import NormalizedEvent


def normalize_log(raw: dict[str, Any]) -> NormalizedEvent:
    # TODO: level/message/service 추출. docs/data-schema.md 확정 후 구현.
    raise NotImplementedError("normalize_log 스캐폴드")
