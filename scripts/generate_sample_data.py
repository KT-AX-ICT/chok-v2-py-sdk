"""AnoMod/SN_data 에서 examples/sample_data 발췌 생성 (스캐폴드).

MVP 세 시나리오(cpu / kill_media / code_media)의 log/metric/trace 를 소량 잘라 복사한다.
"""

from __future__ import annotations

import argparse

SCENARIOS = {
    "cpu": "Perf_CPU_Contention",
    "kill_media": "Svc_Kill_Media",
    "code_media": "Code_Stop_MediaService",
}


def main() -> None:
    p = argparse.ArgumentParser(description="SN_data → examples/sample_data 발췌")
    p.add_argument("--sn-root", default="../AnoMod/SN_data", help="AnoMod SN_data 경로")
    p.add_argument("--limit", type=int, default=500, help="모달리티별 최대 라인 수")
    args = p.parse_args()
    print(f"sn_root={args.sn_root} limit={args.limit}")
    # TODO: 각 시나리오/모달리티에서 앞 N라인 발췌 복사.
    print("발췌 로직 미구현 (스캐폴드). 대상:", ", ".join(SCENARIOS))


if __name__ == "__main__":
    main()
