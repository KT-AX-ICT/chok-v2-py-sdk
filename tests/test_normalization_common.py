"""정규화 공용 헬퍼 테스트 — 스펙 §1-1(서비스명)·§1-2(시간) + 계획 02 C6(naive)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rca_sdk.normalization.common import canonical_service, parse_timestamp


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("UserService", "user"),
        ("user-service", "user"),
        ("SocialGraphService", "socialgraph"),
        ("social-graph-service", "socialgraph"),
        ("NginxThrift", "nginx"),
        ("nginx-thrift", "nginx"),
        ("nginx-web-server", "nginx"),
        ("media-service", "media"),
        ("MediaService_", "media"),          # 로그 파일명 stem
        ("text-service", "text"),
        ("unique-id-service", "uniqueid"),
        ("url-shorten-service", "urlshorten"),
        ("user-mention-service", "usermention"),
        ("user-timeline-service", "usertimeline"),
        ("home-timeline-service", "hometimeline"),
        ("post-storage-service", "poststorage"),
        ("compose-post-service", "composepost"),
        # 인프라는 특수문자만 제거하고 유지 (§1-1)
        ("user-mongodb", "usermongodb"),
        ("social-graph-mongodb", "socialgraphmongodb"),
        ("url-shorten-memcached", "urlshortenmemcached"),
    ],
)
def test_canonical_service_table(raw, expected):
    assert canonical_service(raw) == expected


def test_canonical_service_none():
    assert canonical_service(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2025-Nov-04 00:01:57.490560", datetime(2025, 11, 4, 0, 1, 57, 490560)),  # boost 상세
        ("2025-Nov-04 00:01:57", datetime(2025, 11, 4, 0, 1, 57)),                 # boost 초 단위
        ("2025/11/04 02:58:25", datetime(2025, 11, 4, 2, 58, 25)),                 # nginx
        ("2025-11-04 00:02:21", datetime(2025, 11, 4, 0, 2, 21)),                  # metric CSV
        ("2025-11-04 00:20:00.521000", datetime(2025, 11, 4, 0, 20, 0, 521000)),   # trace CSV
    ],
)
def test_parse_timestamp_formats(raw, expected):
    parsed = parse_timestamp(raw)
    assert parsed == expected
    assert parsed.tzinfo is None  # naive 보장 (C6)


def test_parse_timestamp_drops_tz_without_conversion():
    parsed = parse_timestamp("2025-11-04T00:02:21+09:00")
    assert parsed == datetime(2025, 11, 4, 0, 2, 21)  # 변환 없이 버림
    assert parsed.tzinfo is None


def test_parse_timestamp_aware_datetime_becomes_naive():
    aware = datetime(2025, 11, 4, 1, 2, 3, tzinfo=UTC)
    assert parse_timestamp(aware) == datetime(2025, 11, 4, 1, 2, 3)


def test_parse_timestamp_garbage_raises():
    with pytest.raises(ValueError):
        parse_timestamp("not-a-time")
