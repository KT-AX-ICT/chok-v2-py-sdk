"""트레이스 정규화 — all_traces.csv 컬럼 dict → NormalizedTrace (정규화 스펙 §4, 계획 03 §2)."""

from __future__ import annotations

import json
import logging
from typing import Any

from rca_sdk.normalization.base import Normalizer
from rca_sdk.normalization.common import canonical_service, parse_timestamp
from rca_sdk.schemas.events import NormalizedBatch, NormalizedTrace, RawBatch

logger = logging.getLogger(__name__)


class TraceNormalizer(Normalizer):
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        records = []
        for rec in batch.records:
            normalized = self._normalize_record(rec)
            if normalized is not None:
                records.append(normalized)
        return NormalizedBatch(
            modality=batch.modality,
            observed_from=batch.observed_from,
            observed_until=batch.observed_until,
            records=records,
        )

    def _normalize_record(self, rec: dict[str, Any]) -> NormalizedTrace | None:
        source = rec.get("_source", "")
        try:
            timestamp = parse_timestamp(rec["start_time"])
            duration_us = int(rec["duration_us"]) if rec.get("duration_us") else None
            status = int(rec["http_status_code"]) if rec.get("http_status_code") else None
        except (KeyError, ValueError, TypeError):
            logger.warning("%s: trace 행 해석 실패 스킵 (계획 03 N3)", source)
            return None
        tags: dict[str, Any] = {}
        if rec.get("tags"):
            try:
                tags = json.loads(rec["tags"])
            except (json.JSONDecodeError, TypeError):
                logger.warning("%s: tags JSON 해석 실패 — 빈 dict 유지", source)
        logs: Any | None = None
        if rec.get("logs"):
            try:
                logs = json.loads(rec["logs"])
            except (json.JSONDecodeError, TypeError):
                logs = rec["logs"]  # JSON 아니면 원본 유지 (§4)
        return NormalizedTrace(
            timestamp=timestamp,
            service=canonical_service(rec.get("service")),
            trace_id=rec.get("trace_id") or None,
            span_id=rec.get("span_id") or None,
            parent_span_id=rec.get("parent_span_id") or None,
            operation=rec.get("operation") or None,
            duration_us=duration_us,
            duration_ms=duration_us / 1000 if duration_us is not None else None,
            http_status_code=status,
            tags=tags,
            logs=logs,
        )
