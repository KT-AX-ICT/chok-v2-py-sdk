"""`python -m demo.simulator` 인자 파싱과 실행 준비."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from rca_sdk.config import load_settings

from .catalog import load_all
from .engine import InfiniteSimulator

MODALITIES = ("log", "metric", "trace")


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("0보다 커야 합니다")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("0보다 커야 합니다")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m demo.simulator",
        description="SN normal과 장애 3종을 현재 시각으로 무한 재생한다",
    )
    parser.add_argument(
        "--baseline-sec",
        type=_positive_float,
        default=60.0,
        metavar="SEC",
        help="장애 전에 흘릴 normal 원본 시간(기본: 60)",
    )
    parser.add_argument(
        "--cycles",
        type=_positive_int,
        metavar="N",
        help="장애 3종 순환 횟수; 생략하면 무한 실행",
    )
    return parser


def ensure_empty_source_layout(source_root: Path) -> None:
    """기존 tail 데이터를 다시 읽지 않도록 빈 실행 루트만 허용한다."""
    for modality in MODALITIES:
        directory = source_root / modality
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise ValueError(
                f"RCA_SOURCE_ROOT는 빈 실행 경로여야 합니다: {directory} "
                "(simulator는 실행 중 파일을 삭제하지 않습니다)"
            )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    settings = load_settings()
    dataset_root = Path(settings.dataset_root).resolve()
    source_root = Path(settings.source_root).resolve()

    try:
        ensure_empty_source_layout(source_root)
        baseline, incidents = load_all(dataset_root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[simulator] 시작 실패: {exc}")
        return 2

    print(f"[simulator] dataset_root={dataset_root}")
    print(f"[simulator] source_root={source_root}")
    simulator = InfiniteSimulator(
        source_root=source_root,
        baseline=baseline,
        incidents=incidents,
        baseline_sec=args.baseline_sec,
        cycles=args.cycles,
    )
    try:
        simulator.run()
    except KeyboardInterrupt:
        print("\n[simulator] 중단됨")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
