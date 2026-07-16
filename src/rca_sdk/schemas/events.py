"""정규화 데이터 계약.

- 레코드: 모달리티별 3개 스키마(NormalizedLog / NormalizedTrace / NormalizedMetric).
  필드는 정규화 스펙(노션에서 확인)에서 정의.
- 배치: RawBatch(수집) → NormalizedBatch(정규화) → MultimodalSnapshot(버퍼 조회).

주의: 모든 시각은 `datetime`(naive, TZ 변환 없음)으로 통일한다. 전송/표시 시
`YYYY-MM-DD HH:MM:SS.fff` 포맷으로 직렬화한다(정규화 스펙 §1-2).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Modality(StrEnum):
    LOG = "log"
    METRIC = "metric"
    TRACE = "trace"


# --- 모달리티별 정규화 레코드 (normalization-spec §3~5) ---


class NormalizedLog(BaseModel):
    """정규화 로그 1줄 (normalized_logs)."""

    timestamp: datetime                  # 표시/전송 시 "YYYY-MM-DD HH:MM:SS.fff"
    canonical_service: str | None = None
    log_type: str | None = None          # "service_log" | "nginx_log"
    level: str | None = None             # "info" | "warn" | "error" ...
    code_loc: str | None = None          # "MediaService.cpp:44" 등, 없으면 None
    message: str | None = None
    target_service: str | None = None    # 메시지 내 대상 서비스, 없으면 None
    event_type: str | None = None        # "service_start" | "connection_error" | "normal_log"


class NormalizedTrace(BaseModel):
    """정규화 span 1개 (normalized_traces)."""

    timestamp: datetime
    canonical_service: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None    # 공백이면 None
    operation: str | None = None
    duration_us: int | None = None
    duration_ms: float | None = None     # duration_us / 1000
    http_status_code: int | None = None  # 공백은 None
    tags: dict[str, Any] = Field(default_factory=dict)
    logs: Any | None = None              # JSON이면 파싱, 아니면 원본/None


class NormalizedMetric(BaseModel):
    """정규화 metric row 1개 (normalized_metrics)."""

    timestamp: datetime
    canonical_service: str | None = None  # 노드 지표는 "__node__"
    metric_name: str | None = None
    value: float | None = None
    dimension: str | None = None
    unit: str | None = None


NormalizedRecord = NormalizedLog | NormalizedTrace | NormalizedMetric


# --- 배치 계약 (interface-contract §2.1~2.3) ---


class SourceStatus(BaseModel):
    """정규화가 배치마다 출력하는 소스 관측 상태 (roster).

    윈도 구간으로 집계하면 번들 `modality_info`(missing/empty/data)가 된다.
    `present`/`record_count`가 함께 있어야 missing(파일 없음)과 empty(있지만 0건)를 구분한다.
    """

    source: str                          # artifact / canonical_service
    present: bool                        # 소스(파일/데이터)가 존재했는가
    record_count: int = 0                # 이번 배치의 레코드 수


class RawBatch(BaseModel):
    """Collector 산출물 — 원시 레코드 + 관측 범위."""

    modality: Modality
    observed_from: datetime              # 관측 시간 하한
    observed_until: datetime             # 관측 시간 상한 (watermark)
    records: list[dict[str, Any]] = Field(default_factory=list)


class NormalizedBatch(BaseModel):
    """Normalizer 산출물 — 정규화 레코드 + 관측 범위(유지)."""

    modality: Modality
    observed_from: datetime
    observed_until: datetime
    records: list[NormalizedRecord] = Field(default_factory=list)
    roster: list[SourceStatus] = Field(default_factory=list)  # 소스 상태 (modality_info 원천)


class MultimodalSnapshot(BaseModel):
    """MemoryBuffer.get_snapshot 산출물 — 윈도 구간의 모달리티별 정규화 레코드 (독립 복사본)."""

    logs: list[NormalizedLog] = Field(default_factory=list)
    metrics: list[NormalizedMetric] = Field(default_factory=list)
    traces: list[NormalizedTrace] = Field(default_factory=list)
    coverage: dict[str, list[SourceStatus]] = Field(default_factory=dict)  # modality → 윈도 roster
