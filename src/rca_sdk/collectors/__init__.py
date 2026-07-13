"""① 수집 계층 — 원천 log/metric/trace 를 지속 관측(tail)해 원시 레코드를 흘려보낸다."""

from rca_sdk.collectors.base import Collector

__all__ = ["Collector"]
