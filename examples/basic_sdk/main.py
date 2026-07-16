"""최소 사용 예제 (스캐폴드).

SDK 의 데이터 계약(RawBatch → NormalizedBatch → SnapshotBundle)을 구성해 보여준다.
파이프라인 내부 로직은 아직 스캐폴드(TODO)라, 여기서는 계약 타입만 시연한다.
"""

from __future__ import annotations

from datetime import datetime

from rca_sdk.schemas import (
    Modality,
    NormalizedBatch,
    NormalizedLog,
    RawBatch,
    SnapshotBundle,
    SourceStatus,
    TriggerInfo,
    Window,
)
from rca_sdk.schemas.snapshot import BundleRecord


def main() -> None:
    now = datetime.now()

    # ① 수집 — 원시 배치
    raw = RawBatch(
        modality=Modality.LOG,
        observed_from=now,
        observed_until=now,
        records=[{"service": "user-service", "level": "error"}],
    )
    print("raw records:", len(raw.records))

    # ② 정규화 — 모달리티별 스키마 + 소스 상태(roster)
    norm = NormalizedBatch(
        modality=Modality.LOG,
        observed_from=now,
        observed_until=now,
        records=[NormalizedLog(timestamp=now, canonical_service="user", level="error")],
        roster=[SourceStatus(source="UserService", present=True, record_count=1)],
    )
    print("normalized:", norm.records[0].canonical_service, norm.roster[0].present)

    # ⑤~⑥ 전송 번들 (raw = 정규화 레코드를 JSON 문자열로)
    bundle = SnapshotBundle(
        window=Window(start=now, end=now),
        trigger_info=TriggerInfo(trigger_time=now, triggered_by=["log"]),
        logs=[BundleRecord(timestamp=now, service="user", raw='{"level":"error"}')],
    )
    print("bundle:", bundle.bundle_version, bundle.trigger_info.triggered_by)


if __name__ == "__main__":
    main()
