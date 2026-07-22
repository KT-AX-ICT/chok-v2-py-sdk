"""로그 정규화 — {"raw": 원본 라인} → NormalizedLog (정규화 스펙 §3, 계획 03 §2)."""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime
from typing import Any

from rca_sdk.normalization.base import Normalizer
from rca_sdk.normalization.common import canonical_service, parse_timestamp
from rca_sdk.schemas.events import NormalizedBatch, NormalizedLog, RawBatch

logger = logging.getLogger(__name__)

# boost: [ts] <level>: (file:line:func) message
#
# func 는 `.*?` 다. C++ 람다·펑터는 함수명이 `operator()` 로 찍혀 **괄호를 품는다** —
# `[^)]*` 로 두면 첫 `)` 에서 멈춰 그 줄이 통째로 버려진다(실데이터에서 TextService
# 400줄/시나리오가 조용히 사라졌다). 비탐욕 + 뒤의 `\) ` 앵커로 마지막 닫는 괄호를 잡는다.
_BOOST_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\] <(?P<level>\w+)>: "
    r"\((?P<file>[^:()]+):(?P<line>\d+):(?P<func>.*?)\) (?P<msg>.*)$"
)
# nginx: YYYY/MM/DD HH:MM:SS [level] message
_NGINX_RE = re.compile(
    r"^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) \[(?P<level>\w+)\] (?P<msg>.*)$"
)
# thrift: boost 로그 파일 안에 thrift 라이브러리가 직접 찍는 3번째 변형 — C asctime 이고
# level 표기가 없다 (demo/replayer/readers.py 의 THRIFT 와 짝). 실측: Code_Stop 의
# ComposePostService_.log 1001줄 중 200줄. 못 잡으면 media-service 연결 실패 증거가 유실된다.
_THRIFT_RE = re.compile(
    r"^Thrift: (?P<ts>[A-Za-z]{3} [A-Za-z]{3} [ \d]\d \d{2}:\d{2}:\d{2} \d{4}) (?P<msg>.*)$"
)
_THRIFT_TS_FMT = "%a %b %d %H:%M:%S %Y"
_LUA_LOC_RE = re.compile(r"([\w.]+\.lua:\d+)")
_CONNECT_TARGET_RE = re.compile(r"Could not connect to ([A-Za-z0-9-]+):\d+")
# 익명 resolve-host 는 target 없음 그대로 둔다 — Code_Stop 신호 (ADR-003)
_CONNECTION_ERROR_MARKERS = ("Could not resolve host", "Could not connect", "TTransportException")


class LogNormalizer(Normalizer):
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        records = []
        for rec in batch.records:
            normalized = self._normalize_record(rec)
            if normalized is not None:
                records.append(normalized)
        counts = Counter(r.service for r in records if r.service)
        # 파일명 → canonical 로 접어 "서비스 파일 존재" 를 판정한다 (계획 03 N2)
        present = {
            svc
            for src in batch.sources
            if (svc := canonical_service(src.removesuffix(".log"))) is not None
        }
        return NormalizedBatch(
            modality=batch.modality,
            observed_from=batch.observed_from,
            observed_until=batch.observed_until,
            records=records,
            roster=self._build_roster(self.expected_services, present, counts),
        )

    def _normalize_record(self, rec: dict[str, Any]) -> NormalizedLog | None:
        raw = rec.get("raw", "")
        source = rec.get("_source", "")
        service = canonical_service(source.removesuffix(".log"))
        level: str | None
        is_thrift = False
        match = _BOOST_RE.match(raw)
        if match:
            code_loc = f"{match['file']}:{match['line']}"
            level = match["level"]
        else:
            match = _NGINX_RE.match(raw)
            if match:
                lua = _LUA_LOC_RE.search(match["msg"])
                code_loc = lua.group(1) if lua else None
                level = match["level"]
            else:
                match = _THRIFT_RE.match(raw)
                if match is None:
                    logger.warning("%s: 해석 불가 로그 줄 스킵 (계획 03 N3)", source)
                    return None
                is_thrift = True
                code_loc = None  # file:line 표기가 없다
                level = None  # level 표기가 없다
        message = match["msg"]
        try:
            timestamp = (
                datetime.strptime(match["ts"], _THRIFT_TS_FMT)
                if is_thrift
                else parse_timestamp(match["ts"])
            )
        except (ValueError, TypeError):
            logger.warning("%s: timestamp 해석 실패 줄 스킵 (계획 03 N3)", source)
            return None
        if message.startswith("Starting"):
            event_type = "service_start"  # restart_marker 원천 (trigger-policy)
        elif any(marker in message for marker in _CONNECTION_ERROR_MARKERS):
            event_type = "connection_error"
        else:
            event_type = "normal_log"
        target = _CONNECT_TARGET_RE.search(message)
        return NormalizedLog(
            timestamp=timestamp,
            service=service,
            log_type="nginx_log" if service == "nginx" else "service_log",
            level=level,
            code_loc=code_loc,
            message=message,
            target_service=canonical_service(target.group(1)) if target else None,
            event_type=event_type,
        )
