"""SDK에 포함된 AnoMod SN 원본을 replayer Source/Loaded로 조립한다."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

from demo.replayer.scenarios import SCENARIOS, discover_prefix
from demo.replayer.scheduler import Loaded, load, measure_start, merged

BASELINE_PREFIX = "Normal_Baseline"
INCIDENT_PREFIXES = SCENARIOS


@dataclass(frozen=True)
class Dataset:
    """재생 준비가 끝난 원본 한 세트."""

    name: str
    prefix: str
    loaded: list[Loaded]
    t0: datetime
    end: datetime | None = None
    output_names: dict[tuple[str, str], str] = field(default_factory=dict)

    def output_filename(self, item: Loaded) -> str:
        """원본 schema 충돌 때만 격리한 출력 이름을 돌려준다."""
        key = (item.source.modality, item.source.filename)
        return self.output_names.get(key, item.source.filename)


def _measure_end(loaded: list[Loaded]) -> datetime:
    latest = max((record.ts for record, _ in merged(loaded)), default=None)
    if latest is None:
        raise ValueError("재생할 timestamp 레코드가 없다")
    # 재생 창은 [start, end)라 마지막 레코드도 포함되도록 1µs 뒤를 끝으로 둔다.
    return latest + timedelta(microseconds=1)


def load_dataset(
    dataset_root: Path,
    name: str,
    prefix: str,
    *,
    measure_end: bool = False,
) -> Dataset:
    sources = discover_prefix(dataset_root, prefix)
    if not sources:
        raise FileNotFoundError(
            f"'{prefix}' 데이터가 없습니다: {dataset_root} "
            "(SDK datasets/sn 원본 포함 여부를 확인하세요)"
        )
    loaded = load(sources)
    t0 = measure_start(loaded)
    end = _measure_end(loaded) if measure_end else None
    return Dataset(name=name, prefix=prefix, loaded=loaded, t0=t0, end=end)


def load_all(dataset_root: Path) -> tuple[Dataset, dict[str, Dataset]]:
    baseline = load_dataset(dataset_root, "normal", BASELINE_PREFIX, measure_end=True)
    incidents = {
        name: load_dataset(dataset_root, name, prefix)
        for name, prefix in INCIDENT_PREFIXES.items()
    }
    isolated = _isolate_shared_header_conflicts([baseline, *incidents.values()])
    return isolated[0], {
        name: isolated[index]
        for index, name in enumerate(INCIDENT_PREFIXES, start=1)
    }


def _isolate_shared_header_conflicts(datasets: list[Dataset]) -> list[Dataset]:
    """서로 다른 원본 header가 같은 출력 파일에 섞이지 않도록 파일만 분리한다.

    AnoMod의 ``kill_media`` memory metric에는 다른 세트에 없는 ``restartcount``
    컬럼이 있다. 행이나 header를 맞춰 쓰면 원본을 변형하게 되므로, 최초 schema는
    기존 basename을 유지하고 다른 schema만 ``__<dataset>`` 파일에 그대로 쓴다.
    collector는 ``*.csv``를 tail하므로 별도 설정 없이 두 schema를 모두 읽는다.
    """
    headers: dict[tuple[str, str], str] = {}
    result: list[Dataset] = []
    for dataset in datasets:
        output_names: dict[tuple[str, str], str] = {}
        for item in dataset.loaded:
            if item.header is None:
                continue
            key = (item.source.modality, item.source.filename)
            previous = headers.setdefault(key, item.header)
            if previous != item.header:
                path = Path(item.source.filename)
                output_names[key] = f"{path.stem}__{dataset.name}{path.suffix}"
        result.append(replace(dataset, output_names=output_names))
    return result
