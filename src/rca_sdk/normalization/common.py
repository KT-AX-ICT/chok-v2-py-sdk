"""정규화 공용 헬퍼 (타임스탬프 파싱, 서비스명 정규화 등).

canonical_service 규칙은 normalization-spec §1-1 참조.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# nginx alias (normalization-spec §1-1)
ALIASES = {"nginxwebserver": "nginx", "nginxthrift": "nginx"}


def canonical_service(name: str | None) -> str | None:
    """서비스명을 canonical 형으로 정규화한다.

    규칙(normalization-spec §1-1): 소문자화·특수문자 제거·"service" 접미사 제거·ALIASES 적용.
    단, 인프라(DB/캐시) 명칭은 특수문자만 제거하고 유지한다.
    """
    # TODO: 규칙 구현 + 인프라 예외 처리. 기존 trigger/correlation.canonical_service 에서 포팅.
    raise NotImplementedError("canonical_service 스캐폴드")


def parse_timestamp(value: Any) -> datetime:
    """다양한 원본 타임스탬프 표현을 datetime 으로 변환한다 (스캐폴드 최소 구현).

    모든 시각(레코드 timestamp·배치 observed_from/until)은 datetime 으로 통일한다.
    표시/전송 시 YYYY-MM-DD HH:MM:SS.fff 포맷으로 직렬화한다(별도 serializer).
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"unsupported timestamp type: {type(value)!r}")
