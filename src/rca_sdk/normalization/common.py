"""정규화 공용 헬퍼 (타임스탬프 파싱, 서비스명 정리 등)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def parse_timestamp(value: Any) -> datetime:
    """다양한 원본 타임스탬프 표현을 aware datetime 으로 변환한다 (스캐폴드 최소 구현)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"unsupported timestamp type: {type(value)!r}")
