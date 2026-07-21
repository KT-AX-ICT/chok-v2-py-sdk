"""code_stop · log — nginx_error. 배치 내 nginx connection_error 건수가 임계 초과면 발화.

NginxThrift 게이트웨이가 죽은 서비스로 연결 시도할 때마다 발생(TTransportException / resolve host).
어느 하위 서비스가 죽었는지는 간접 호출이면 특정 불가 → 국소화는 중앙 RCA(설계 §5.6).
"""

from __future__ import annotations

from datetime import datetime

from rca_sdk.schemas.events import Modality, NormalizedBatch, NormalizedLog
from rca_sdk.trigger.base import NumericThresholdDetector


class NginxErrorDetector(NumericThresholdDetector):
    MODALITY = Modality.LOG
    DETECTOR_TYPE = "nginx_error"

    def _value_and_meta(
        self, new_batch: NormalizedBatch
    ) -> tuple[float, str | None, datetime] | None:
        # 배치 내 nginx connection_error(TTransportException/resolve host) 건수를 센다.
        # 게이트웨이(nginx) 로그로 한정 — 다른 서비스의 연결 에러를 nginx 로 오집계하지 않도록.
        count = sum(
            1
            for rec in new_batch.records
            if (
                isinstance(rec, NormalizedLog)
                and rec.service == "nginx"
                and rec.event_type == "connection_error"
            )
        )
        if count == 0:
            return None  # 연결 에러 0건 → 무발화
        return (float(count), "nginx", new_batch.observed_until)
