"""로컬 구동 스크립트 (스캐폴드).

sample_data 를 원천으로 SDK 파이프라인을 1회(또는 루프) 돌려본다.
Runner 구현 후 활성화한다.
"""

from __future__ import annotations

from rca_sdk.config import load_settings


def main() -> None:
    settings = load_settings()
    print(f"source_root={settings.source_root} endpoint={settings.collect_endpoint}")
    # TODO: from rca_sdk.runtime.runner import Runner; Runner(settings).run(once=True)
    print("Runner 미구현 (스캐폴드).")


if __name__ == "__main__":
    main()
