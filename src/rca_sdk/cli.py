"""`rca-collect` 콘솔 진입점. 인자 파싱 후 runtime.runner 를 기동한다."""

from __future__ import annotations

import argparse

from rca_sdk import __version__
from rca_sdk.config import load_settings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rca-collect", description="RCA edge collector")
    p.add_argument("--version", action="version", version=f"rca-collect {__version__}")
    p.add_argument("--once", action="store_true", help="루프 대신 1회 관측만 수행 (디버그)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    # TODO: from rca_sdk.runtime.runner import Runner; Runner(settings).run(once=args.once)
    print(f"rca-collect {__version__} - endpoint={settings.collect_endpoint} once={args.once}")
    print("runner not implemented (scaffold). see runtime/runner.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
