"""placeholder detector — 신호 없는 칸. 항상 [].

시나리오×모달리티 9칸 중 아래 3칸은 이 데이터셋에 **실시간 신호가 없다.** 억지로 모델링하는
대신 `[]` 를 반환하는 자리표시자를 두고, 그 사실 자체를 테스트로 고정한다 (ADR-003·ADR-006):

- svc_kill · metric — cAdvisor 가 같은 라벨로 컨테이너를 즉시 재생성해 시계열이 안 끊긴다
- svc_kill · trace  — gap 의 끝(첫 재개 span)에서야 확인돼 실시간 트리거가 불가하다
- code_stop · metric — 죽은 컨테이너가 목록에 잔존해 span_rate 변화가 없다
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rca_sdk.schemas.events import Modality, NormalizedBatch
from rca_sdk.trigger.code_stop.metric import CodeStopMetricDetector
from rca_sdk.trigger.svc_kill.metric import SvcKillMetricDetector
from rca_sdk.trigger.svc_kill.trace import SvcKillTraceDetector

TS = datetime(2025, 11, 4, 0, 4, 0)


def any_batch(modality: Modality) -> NormalizedBatch:
    return NormalizedBatch(
        modality=modality, observed_from=TS - timedelta(seconds=30), observed_until=TS
    )


def test_svc_kill_metric_placeholder_returns_empty():
    assert SvcKillMetricDetector({}).evaluate(any_batch(Modality.METRIC), None) == []


def test_svc_kill_trace_placeholder_returns_empty():
    assert SvcKillTraceDetector({}).evaluate(any_batch(Modality.TRACE), None) == []


def test_code_stop_metric_placeholder_returns_empty():
    assert CodeStopMetricDetector({}).evaluate(any_batch(Modality.METRIC), None) == []
