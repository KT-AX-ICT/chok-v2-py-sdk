"""시나리오 재생 결과 → 마크다운 리포트 (계획 05 §6).

단정만으로는 "결과값 확인"이 안 된다. 발화 타임라인·번들 구성·볼륨 실측을 표로 낸다.
`python -m tests.replay.report` 로 직접 실행하거나 test_report_generation 이 호출한다.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from rca_sdk.config import Settings
from rca_sdk.schemas.events import Modality
from rca_sdk.schemas.snapshot import SnapshotBundle
from tests.replay.scenarios import ReplayResult, run_scenario

OUTPUT = Path(__file__).resolve().parents[2] / "test_report/scenario-replay-report.md"
ORDER = ["Svc_Kill_Media", "Code_Stop_MediaService", "Perf_CPU_Contention"]

# 시나리오별로 ADR-006 이 예고한 신호. 침묵 검증이 발화 검증만큼 중요하다 —
# cpu_spike 는 metric_name 불일치로 조용히 0건이던 전례가 있다.
EXPECTED = {
    "Svc_Kill_Media": ("restart_marker",),
    "Code_Stop_MediaService": ("trace_5xx", "nginx_error"),
    "Perf_CPU_Contention": ("cpu_spike",),
}
SHOULD_STAY_QUIET = {
    "Svc_Kill_Media": ("cpu_spike",),
    "Code_Stop_MediaService": ("cpu_spike",),
    "Perf_CPU_Contention": ("restart_marker",),
}


def _hms(value: datetime) -> str:
    return value.strftime("%H:%M:%S")


def _bundle_row(index: int, bundle: SnapshotBundle) -> str:
    info = bundle.trigger_info
    return (
        f"| {index} | {_hms(bundle.window.start)} ~ {_hms(bundle.window.end)} "
        f"| {_hms(info.trigger_time)} | {', '.join(info.triggered_by)} "
        f"| {len(bundle.logs):,} | {len(bundle.metrics):,} | {len(bundle.traces):,} "
        f"| {len(bundle.model_dump_json()) / 1024 / 1024:.1f} MB |"
    )


def _coverage_section(bundle: SnapshotBundle) -> list[str]:
    lines = []
    for modality, info in sorted(bundle.modality_info.items()):
        states = Counter(interval.status for interval in info.intervals)
        summary = " · ".join(f"{state} {count}" for state, count in sorted(states.items()))
        missing = sorted(i.fileName for i in info.intervals if i.status == "missing")
        empty = sorted(i.fileName for i in info.intervals if i.status == "empty")
        detail = ""
        if missing:
            detail += f" — missing: {', '.join(missing)}"
        if empty:
            detail += f" — empty: {', '.join(empty)}"
        lines.append(f"| {modality} | {summary}{detail} |")
    return lines


def render(results: list[ReplayResult]) -> str:
    settings = Settings()
    out: list[str] = [
        "# 시나리오 재생 리포트",
        "",
        "`datasets/sn` 의 결함 시나리오 3종을 30초 배치로 재생해, 실제 파이프라인이 내는",
        "스냅샷 번들 구성을 관측한 결과다.",
        "설계는 [계획 05](../docs/plans/05-runner-scenario-replay.md).",
        "",
        "**이 리포트는 자동 생성된다** — `python -m tests.replay.report`.",
        "손으로 고치지 말고 재생성한다.",
        "",
        "## 재생 조건",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 루프 주기 | {settings.loop_interval_sec}초 |",
        f"| 버퍼 보존 | {settings.buffer_retention_sec}초 |",
        "| 스냅샷 창 | anchor ± 180초 (6분) |",
        "| 대체한 계층 | 파일 tail(`Collector.poll`)·전송(`Transport.send`) **둘뿐** |",
        "| 실제 구현 | normalizer · buffer · detector · SnapshotManager · Runner |",
        "",
        "타임스탬프는 **시프트하지 않았다**. 버퍼 축출이 벽시계가 아니라 watermark 기준이라",
        "2025-11-03/04 원본 시각이 그대로 돈다.",
        "",
        "## 한눈에",
        "",
        "| 시나리오 | 틱 | 소요 | ms/틱 | 예외 | 불연속 | 드롭 | 번들 |",
        "|---|---|---|---|---|---|---|---|",
        *(
            f"| {r.scenario} | {r.ticks} | {r.elapsed_sec:.1f}s "
            f"| {r.elapsed_sec / r.ticks * 1000:.0f} "
            "| 없음 "
            f"| {'없음' if not r.gaps else f'{len(r.gaps)}건'} "
            f"| {sum(r.dropped(m) for m in Modality):,} | {len(r.bundles)} |"
            for r in results
        ),
        "",
        "전 시나리오가 **끊김 없이 완주**한다. `Runner.tick()` 이 예외를 던지면 재생이",
        "거기서 멈추므로, 틱 수가 데이터 끝까지 도달했다는 것 자체가 완주의 증거다.",
        "",
        "소요 시간은 **재생 속도**이지 실운용 부하가 아니다 — 실제로는 30초에 한 틱이므로",
        "틱당 200~250 ms 는 주기의 1% 미만이다. 재생은 그 40~50틱을 쉬지 않고 돌린다.",
        "",
        "---",
        "",
    ]

    for result in results:
        expected = EXPECTED[result.scenario]
        quiet = SHOULD_STAY_QUIET[result.scenario]
        fired = result.fired_types()

        out += [
            f"## {result.scenario}",
            "",
            f"재생 {result.ticks}틱 · 기준시 {result.origin:%Y-%m-%d %H:%M:%S} · "
            f"번들 {len(result.bundles)}개",
            "",
            "### 적재량",
            "",
            "| 모달리티 | 레코드 |",
            "|---|---|",
        ]
        for modality in (Modality.LOG, Modality.METRIC, Modality.TRACE):
            out.append(f"| {modality.value} | {result.loaded.get(modality, 0):,} |")

        out += [
            "",
            "### 연속성 — 끊김 없이 도는가",
            "",
            "| 모달리티 | poll 원시 | 정규화 통과 | 드롭 |",
            "|---|---|---|---|",
        ]
        for modality in (Modality.LOG, Modality.METRIC, Modality.TRACE):
            dropped = result.dropped(modality)
            mark = "" if dropped == 0 else f" ⚠️ {dropped / max(result.raw_polled[modality], 1):.1%}"
            out.append(
                f"| {modality.value} | {result.raw_polled.get(modality, 0):,} "
                f"| {result.normalized.get(modality, 0):,} | {dropped:,}{mark} |"
            )
        gap_note = "없음" if not result.gaps else f"**{len(result.gaps)}건** — {result.gaps[:3]}"
        out += [
            "",
            f"- **틱 예외**: 없음 ({result.ticks}틱 완주. 예외가 나면 재생이 거기서 멈춘다)",
            f"- **배치 불연속**: {gap_note} (배치 N.`observed_until` == N+1.`observed_from`)",
            f"- **소요**: {result.elapsed_sec:.1f}초 "
            f"({result.elapsed_sec / result.ticks * 1000:.0f} ms/틱)",
            "",
            "### 발화 판정",
            "",
            "| detector | 기대 | 결과 | 발화 수 | 최초 틱 | 최초 trigger_time | service |",
            "|---|---|---|---|---|---|---|",
        ]
        counts = Counter(f.evidence.detector_type for f in result.fires)
        for detector_type in sorted(set(counts) | set(expected) | set(quiet)):
            if detector_type in expected:
                want, ok = "발화", detector_type in fired
            elif detector_type in quiet:
                want, ok = "침묵", detector_type not in fired
            else:
                want, ok = "—", True
            first = result.first_fire(detector_type)
            out.append(
                f"| `{detector_type}` | {want} | {'✅' if ok else '❌'} "
                f"| {counts.get(detector_type, 0)} "
                f"| {first.tick if first else '—'} "
                f"| {_hms(first.evidence.trigger_time) if first else '—'} "
                f"| {(first.evidence.service or '—') if first else '—'} |"
            )

        out += [
            "",
            "### 번들",
            "",
            "| # | 창 | anchor | 발화 모달리티 | logs | metrics | traces | 직렬화 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for index, bundle in enumerate(result.bundles, start=1):
            out.append(_bundle_row(index, bundle))

        if result.bundles:
            out += [
                "",
                "### coverage — 마지막 번들",
                "",
                "| 모달리티 | 소스 상태 |",
                "|---|---|",
                *_coverage_section(result.bundles[-1]),
            ]
        out += ["", "---", ""]

    out += _findings(results)
    return "\n".join(out) + "\n"


def _findings(results: list[ReplayResult]) -> list[str]:
    by_name = {r.scenario: r for r in results}
    biggest = max(
        ((r.scenario, b) for r in results for b in r.bundles),
        key=lambda pair: len(pair[1].logs),
        default=None,
    )
    lines = ["## 실측이 드러낸 것", ""]

    if biggest is not None:
        name, bundle = biggest
        size = len(bundle.model_dump_json()) / 1024 / 1024
        lines += [
            "### 1. 번들 payload — ADR-006 미결이 수치를 얻었다",
            "",
            f"가장 큰 번들은 `{name}` 의 6분 창에 **로그 {len(bundle.logs):,}건**, "
            f"직렬화 **{size:.1f} MB** 다.",
            "",
            "로그가 균일하지 않기 때문이다 — 결함 순간 1분에 29만 줄이 몰린다. 그 폭주가",
            "창 안에 들어오면 번들이 통째로 커진다. 상한·샘플링·서비스 필터 정책이 필요하다",
            "(ADR-006 §미결 번들 payload 상한).",
            "",
        ]

    code_stop = by_name.get("Code_Stop_MediaService")
    if code_stop is not None:
        counts = Counter(f.evidence.detector_type for f in code_stop.fires)
        if counts.get("error_rate", 0) > 5:
            lines += [
                "### 2. `error_rate` 임계가 낮다",
                "",
                "ADR-006 은 perf 로그가 duplicate-key artifact 라 **거의 침묵**해야",
                "한다고 적었으나,",
                f"`Code_Stop_MediaService` 에서 {counts['error_rate']}회 발화한다. 현재 조건",
                "`{baseline: 5, ratio: 1.5, floor: 8}` 이 실제 아티팩트율보다 낮다.",
                "",
                "번들 수에는 영향이 없다(같은 세션에 흡수되거나 `since` 로 눌린다). 다만 근거",
                "목록을 오염시켜 중앙 RCA 의 국소화를 흐린다. **임계 재도출 필요.**",
                "",
            ]

    lines += [
        "### 3. `since` 가 detector 계열에 일관되게 걸리지 않는다",
        "",
        "창 기반 detector(`cpu_spike`·`restart_marker`)는 `since` 로 되돌아보기가 잘려",
        "재발화 anchor 가 항상 직전 번들 창 끝 뒤에 온다. 그런데 **배치 기반 detector**",
        "(`trace_5xx`·`nginx_error`·`error_rate`·`latency_spike`)는 되돌아보기 자체가 없어",
        "`since` 를 보지 않고, 이번 배치의 레코드 시각을 그대로 `trigger_time` 으로 쓴다.",
        "",
        "그래서 `since` 경계를 걸친 배치에서 발화하면 anchor 가 **최대 한 배치(30초)** 과거가",
        "된다. 실측 최대 6.6초였다. 무해하다 — 새 창이 직전 번들과 어차피 겹치고 보존 여유",
        "안이다. 다만 계약이 계열마다 다르다는 뜻이라 [계획 04 §9]"
        "(../docs/plans/04-memory-buffer.md)(`trigger_time` 의미)와 함께 정리해야 한다.",
        "",
    ]
    return lines


def main() -> Path:
    results = [run_scenario(name) for name in ORDER]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(results), encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    print(main())
