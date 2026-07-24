"""연속 재생 경계에서만 필요한 demo 출력 필터."""

from __future__ import annotations

from demo.replayer.readers import Record
from demo.replayer.scheduler import Loaded


def keep_baseline_record(record: Record, loaded: Loaded) -> bool:
    """normal baseline의 cold-start marker를 연속 운영 데이터에서 제외한다.

    AnoMod의 각 시나리오는 독립 환경을 기동해 수집했기 때문에 모든 데이터셋 첫머리에
    서비스별 ``Starting...`` 로그가 있다. 독립 재생에서는 정상 1회지만, baseline과 다음
    시나리오를 이어 붙이면 210초 detector window 안에서 2회로 합쳐져 재시작으로 오인된다.

    원본은 건드리지 않고 baseline 출력에서만 boost 로그의 기동 줄을 생략한다. 장애 신호인
    ``kill_media``의 media 기동+재기동 2회에는 이 predicate를 적용하지 않는다.
    """
    if loaded.source.modality != "log" or loaded.source.kind != "boost":
        return True
    _, separator, message = record.line.rpartition(") ")
    return not (separator and message.startswith("Starting"))
