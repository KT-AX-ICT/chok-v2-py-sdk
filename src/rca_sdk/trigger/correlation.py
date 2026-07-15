"""[미사용 · 전체 주석처리] 다중 모달리티 → CandidateIncident 수렴.

사유: correlation(모달리티 수렴)은 엣지 SDK에서 제외됨 — 인터페이스 계약 §0-4.
      수렴·suspect 판정은 중앙 RCA가 담당하므로 엣지 파이프라인에서 호출하지 않는다.
      기존 로직은 참고용으로 남기되 아래 전체를 주석처리한다. (2026-07-15)
"""

# from __future__ import annotations
#
# import re
#
# from rca_sdk.trigger.models import CandidateIncident, ModalitySignal
#
#
# def canonical_service(name: str | None) -> str | None:
#     """서비스명을 모달리티 간 비교 가능한 정규형으로 (UserService/user-service → user)."""
#     if not name:
#         return None
#     s = re.sub(r"[^a-z0-9]", "", name.lower())
#     s = re.sub(r"service$", "", s)
#     return s or None
#
#
# def correlate(signals: list[ModalitySignal]) -> list[CandidateIncident]:
#     groups: dict[str, dict] = {}
#     for sig in signals:
#         if not sig.triggered:
#             continue
#         for c in sig.candidates:
#             canon = canonical_service(c.service) or "_global"
#             g = groups.setdefault(canon, {"services": set(), "cands": [], "mods": set()})
#             if c.service:
#                 g["services"].add(c.service)
#             g["cands"].append(c)
#             g["mods"].add(sig.modality)
#
#     incidents: list[CandidateIncident] = []
#     for canon, g in groups.items():
#         corr = len(g["mods"])
#         mean_sev = sum(c.severity for c in g["cands"]) / max(1, len(g["cands"]))
#         suspect = sorted(g["services"])[0] if g["services"] else "_global"
#         incidents.append(
#             CandidateIncident(
#                 incident_id=canon,
#                 suspect_service=suspect,
#                 modalities_triggered=sorted(g["mods"]),
#                 candidates=g["cands"],
#                 corroboration=corr,
#                 score=round(mean_sev * corr, 4),
#             )
#         )
#     incidents.sort(key=lambda i: i.score, reverse=True)
#     return incidents
