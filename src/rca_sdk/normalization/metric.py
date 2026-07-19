"""메트릭 정규화 — CSV 컬럼 dict → NormalizedMetric (정규화 스펙 §5, 계획 03 §2)."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from rca_sdk.normalization.base import Normalizer
from rca_sdk.normalization.common import canonical_service, parse_timestamp
from rca_sdk.schemas.events import NormalizedBatch, NormalizedMetric, RawBatch

logger = logging.getLogger(__name__)

NODE_SERVICE = "__node__"
_CONTAINER_DIM = "container_label_com_docker_compose_service"
# metric_name → 단위 (미정의는 None)
_UNITS = {"container_cpu": "fraction", "system_cpu_usage": "percent"}


class MetricNormalizer(Normalizer):
    def normalize(self, batch: RawBatch) -> NormalizedBatch:
        records = []
        for rec in batch.records:
            normalized = self._normalize_record(rec)
            if normalized is not None:
                records.append(normalized)
        counts = Counter(r.service for r in records if r.service)
        # 서비스 행은 socialnet_container_*, 노드 행은 system_* 아티팩트가 담는다 (계획 03 N2)
        expected = [*self.expected_services, NODE_SERVICE]
        has_container = any(s.startswith("socialnet_container_") for s in batch.sources)
        has_system = any(s.startswith("system_") for s in batch.sources)
        present = {
            svc for svc in expected if (has_system if svc == NODE_SERVICE else has_container)
        }
        return NormalizedBatch(
            modality=batch.modality,
            observed_from=batch.observed_from,
            observed_until=batch.observed_until,
            records=records,
            roster=self._build_roster(expected, present, counts),
        )

    def _normalize_record(self, rec: dict[str, Any]) -> NormalizedMetric | None:
        source = rec.get("_source", "")
        metric_name = source.rsplit(".", 1)[0].removeprefix("socialnet_")
        if _CONTAINER_DIM in rec:
            dimension = rec[_CONTAINER_DIM]
            service = canonical_service(dimension)
        elif "instance" in rec:
            dimension = rec["instance"]
            service = NODE_SERVICE  # 노드 지표 (§5) — cpu_spike 신호 원천
        else:
            dimension = None
            service = None
        try:
            return NormalizedMetric(
                timestamp=parse_timestamp(rec["timestamp"]),
                service=service,
                metric_name=metric_name,
                value=float(rec["value"]),
                dimension=dimension,
                unit=_UNITS.get(metric_name),
            )
        except (KeyError, ValueError, TypeError):
            logger.warning("%s: metric 행 해석 실패 스킵 (계획 03 N3)", source)
            return None
