"""시나리오 → 데이터셋 파일 탐색 (계획 Phase 4).

시나리오는 **인자로만** 받고 경로에 인코딩하지 않는다 (`ADR-004`). 접두어로
`datasets/sn/<모달리티>/` 하위를 찾는다 — 폴더명에 수집 시각이 붙어 exact match 가 아니라 glob 이다.
"""

from __future__ import annotations

import glob
from dataclasses import dataclass
from pathlib import Path

# `ADR-004` 승계. 값은 SN 디렉터리 접두어.
SCENARIOS = {
    "cpu": "Perf_CPU_Contention",
    "kill_media": "Svc_Kill_Media",
    "code_media": "Code_Stop_MediaService",
}


@dataclass(frozen=True)
class Source:
    """재생 대상 파일 하나. `filename` 이 곧 `var/<modality>/` 아래 출력 이름이다."""

    modality: str  # log / metric / trace
    filename: str  # 원본 basename = 출력 basename
    path: Path
    kind: str  # boost / nginx / csv — 리더·시프터 선택
    ts_column: str | None = None  # csv 만


def _one_dir(dataset_root: Path, modality: str, prefix: str) -> Path | None:
    """`<dataset_root>/<modality>_data/<prefix>_*/` — 시나리오당 하나여야 한다.

    없으면 None (그 모달리티가 이 시나리오에 없을 수 있다). 둘 이상이면 데이터가 모호하니 실패한다.
    """
    hits = sorted(glob.glob(str(dataset_root / f"{modality}_data" / f"{prefix}_*") + "/"))
    if not hits:
        return None
    if len(hits) > 1:
        raise ValueError(f"{modality}_data 에서 {prefix}_* 가 여러 개다: {hits}")
    return Path(hits[0])


def discover(dataset_root: Path, scenario: str) -> list[Source]:
    """시나리오의 재생 대상 전부. 존재하는 파일만 담는다 (Code_Stop 은 MediaService_.log 가 없다).

    빈 리스트면 데이터셋이 없다는 뜻 — 호출부(CLI)가 경로·CWD 를 알리고 실패한다.
    """
    prefix = SCENARIOS[scenario]
    sources: list[Source] = []

    log_dir = _one_dir(dataset_root, "log", prefix)
    if log_dir:
        for p in sorted(log_dir.glob("*_.log")):
            kind = "nginx" if "Nginx" in p.name else "boost"
            sources.append(Source("log", p.name, p, kind))

    metric_dir = _one_dir(dataset_root, "metric", prefix)
    if metric_dir:
        for p in sorted(metric_dir.glob("*.csv")):
            sources.append(Source("metric", p.name, p, "csv", ts_column="timestamp"))

    trace_dir = _one_dir(dataset_root, "trace", prefix)
    if trace_dir:
        p = trace_dir / "all_traces.csv"
        if p.is_file():
            sources.append(Source("trace", p.name, p, "csv", ts_column="start_time"))

    return sources
