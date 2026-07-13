"""런타임 — collect→normalize→buffer→detect→(bundle→send) 를 30초 루프로 오케스트레이션."""

from rca_sdk.runtime.runner import Runner

__all__ = ["Runner"]
