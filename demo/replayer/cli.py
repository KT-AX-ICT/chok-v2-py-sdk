"""`python -m demo.replayer <scenario>` 진입점 (계획 Phase 4).

경로는 SDK 설정에서 읽는다 — 리플레이어가 쓰는 `var/` 와 콜렉터가 tail 하는 `var/` 가 같은 값이어야
하므로 `RCA_SOURCE_ROOT` / `RCA_DATASET_ROOT` 를 공유한다 (`ADR-004`). 상대경로는 CWD 기준이다.

`pyproject.toml` 에 콘솔 스크립트를 등록하지 않는다 — 등록하면 wheel 에 들어가 실서비스 설치본에
`rca-replay` 가 생긴다. 저장소 루트에서 `python -m demo.replayer` 로 실행한다.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from rca_sdk.config import load_settings

from .runlog import COMPLETED, INTERRUPTED, RunLog
from .scenarios import SCENARIOS, discover
from .scheduler import load, measure_start, replay
from .writer import Writer
from .writer import reset as reset_var


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m demo.replayer",
        description="SN 원본을 타임시프트 재생해 var/ 로 원천 로그를 만든다",
    )
    p.add_argument("scenario", choices=sorted(SCENARIOS), help="재생할 시나리오")
    p.add_argument(
        "--duration",
        type=float,
        metavar="SEC",
        help="이 초만큼만 재생하고 정지 (생략 시 데이터 끝까지)",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="var/{log,metric,trace} 를 비우고 시작 (실행 이력은 보존)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()

    dataset_root = Path(settings.dataset_root).resolve()
    source_root = Path(settings.source_root).resolve()

    sources = discover(dataset_root, args.scenario)
    if not sources:
        # 오류의 실제 원인은 대개 "엉뚱한 데서 실행했다"이므로 CWD 를 함께 알린다 (`ADR-004`).
        print(
            f"[오류] 시나리오 '{args.scenario}' 의 데이터를 찾지 못했습니다.\n"
            f"  dataset_root = {dataset_root}\n"
            f"  현재 작업 디렉터리(CWD) = {Path.cwd()}\n"
            f"  저장소 루트에서 실행하고 있는지 확인하세요.",
        )
        return 2

    runlog = RunLog(source_root)
    if args.reset:
        now = datetime.now(UTC)
        reset_var(source_root)
        runlog.reset(now)

    loaded = load(sources)
    t0 = measure_start(loaded)
    anchor = datetime.now(UTC)

    print(
        f"재생: {args.scenario} — 파일 {len(sources)}개, t0={t0.isoformat()}"
        + (f", {args.duration}초" if args.duration else ", 끝까지")
    )
    runlog.start(args.scenario, anchor)
    try:
        with Writer(source_root) as writer:
            written = replay(loaded, writer, anchor, t0, args.duration)
    except KeyboardInterrupt:
        runlog.finish(INTERRUPTED, datetime.now(UTC))
        print("\n중단됨 (interrupted).")
        return 130
    runlog.finish(COMPLETED, datetime.now(UTC))
    print(f"완료: {written:,}줄 → {source_root}")
    return 0
