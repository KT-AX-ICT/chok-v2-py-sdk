"""공용 픽스처."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rca_sdk.schemas.events import Modality, NormalizedEvent


@pytest.fixture
def make_event():
    def _make(service="media-service", modality=Modality.TRACE, ts=None, **attrs):
        return NormalizedEvent(
            modality=modality,
            timestamp=ts or datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC),
            service=service,
            attributes=attrs,
        )

    return _make
