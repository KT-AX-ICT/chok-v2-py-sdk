"""정규화 공용 헬퍼 (타임스탬프 파싱, 서비스명 정규화).

canonical_service 규칙은 정규화 스펙 §1-1, 시간 통일은 §1-2 + 계획 02 C6 (naive).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# nginx alias (정규화 스펙 §1-1)
ALIASES = {"nginxwebserver": "nginx", "nginxthrift": "nginx"}

# 인프라(DB/캐시)는 본체 서비스 장애와 구분하기 위해 접미사 제거 없이 유지한다 (§1-1)
INFRA_KEYWORDS = ("mongodb", "redis", "memcached", "rabbitmq")

# boost 영문 월 → 숫자 (strptime %b 는 로케일 의존이라 쓰지 않는다)
_MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}
_BOOST_DATE_RE = re.compile(r"^(\d{4})-([A-Z][a-z]{2})-(\d{2}) (.+)$")
_NGINX_DATE_RE = re.compile(r"^(\d{4})/(\d{2})/(\d{2}) (.+)$")


def canonical_service(name: str | None) -> str | None:
    """서비스명을 canonical 형으로 정규화한다 (§1-1).

    소문자화 → 특수문자 제거 → 인프라 키워드 포함 시 정지 → `service` 접미사 제거 → ALIASES.
    """
    if not name:
        return None
    cleaned = re.sub(r"[^a-z0-9]", "", name.lower())
    if any(keyword in cleaned for keyword in INFRA_KEYWORDS):
        return cleaned
    cleaned = cleaned.removesuffix("service")
    return ALIASES.get(cleaned, cleaned)


def parse_timestamp(value: Any) -> datetime:
    """원본 타임스탬프 표현 3계열(boost 영문월·nginx·ISO 공백형)을 naive datetime 으로 변환한다.

    tz 정보가 들어오면 변환 없이 버린다 (계획 02 C6). 실패 시 ValueError/TypeError.
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value))
    if isinstance(value, str):
        text = value.strip()
        boost = _BOOST_DATE_RE.match(text)
        if boost:
            year, month_name, day, rest = boost.groups()
            month = _MONTHS.get(month_name)
            if month is None:
                raise ValueError(f"알 수 없는 월 표기: {value!r}")
            text = f"{year}-{month}-{day} {rest}"
        else:
            nginx = _NGINX_DATE_RE.match(text)
            if nginx:
                year, month, day, rest = nginx.groups()
                text = f"{year}-{month}-{day} {rest}"
        return datetime.fromisoformat(text).replace(tzinfo=None)
    raise TypeError(f"지원하지 않는 timestamp 타입: {type(value)!r}")
