"""[미사용 · 전체 주석처리] 사전 계산된 baseline 프로파일 로더.

사유: 트리거 조건을 각 trigger별로 직접 지정하기로 함 — 인터페이스 계약 §0-5.
      정상 구간 baseline 산출/로드를 하지 않으므로 load_baseline 호출처가 없다.
      참고용으로 남기되 아래 전체를 주석처리한다. (2026-07-15)
"""

# from __future__ import annotations
#
# import json
# from importlib import resources
# from typing import Any
#
#
# def load_baseline(profile: str = "sn_normal") -> dict[str, Any]:
#     """resources/baselines/<profile>.json 로드."""
#     ref = resources.files("rca_sdk.resources.baselines").joinpath(f"{profile}.json")
#     with resources.as_file(ref) as path:
#         return json.loads(path.read_text(encoding="utf-8"))
