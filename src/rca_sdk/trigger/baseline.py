"""사전 계산된 baseline 프로파일 로더 (docs/decisions/ADR-002).

정상 구간에서 산출한 모달리티별 기준치(예: cpu_max, 서비스별 error/latency)를 담은 JSON 을
resources/baselines/<name>.json 에서 읽어 detector 가 편차 비교에 쓴다.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_baseline(profile: str = "sn_normal") -> dict[str, Any]:
    """resources/baselines/<profile>.json 로드."""
    ref = resources.files("rca_sdk.resources.baselines").joinpath(f"{profile}.json")
    with resources.as_file(ref) as path:
        return json.loads(path.read_text(encoding="utf-8"))
