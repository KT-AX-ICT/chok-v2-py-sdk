"""리더 — 원본 파일에서 **타임스탬프만** 파싱해 `(시각, 원본 줄)` 을 산출한다 (계획 01 Phase 1).

줄을 해석하지 않는다. level/message/service/span_id 를 뜯는 것은 콜렉터 일이다.
타임시프트도 하지 않는다 (Phase 2).

`rca_sdk.normalization.common.parse_timestamp()` 는 쓰지 않는다 — `fromisoformat` 기반이라
영문 월(`Nov`)을 파싱하지 못한다. 계획 0-2 의 규칙 파서를 쓴다.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

# 계획 0-2 — 파싱해야 하는 것은 이게 전부다. (마이크로초 선택적: 함정 6)
BOOST = re.compile(r"^\[(\d{4}-[A-Za-z]{3}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]")
NGINX = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})")
# 계획 0-2 표에 없는 3번째 변형. boost 로그 파일 안에 thrift 라이브러리가 직접 찍는 줄로,
# C asctime 포맷(`Tue Nov  4 02:58:25 2025`)이라 BOOST 가 잡지 못한다. 실측: Code_Stop 의
# ComposePostService_.log 200행. 빠뜨리면 "media-service 연결 실패" 증거가 통째로 유실된다.
THRIFT = re.compile(r"^Thrift: ([A-Za-z]{3} [A-Za-z]{3} [ \d]\d \d{2}:\d{2}:\d{2} \d{4}) ")

# log/metric 은 타임존 표기가 물리적으로 없다 → UTC 로 명시 해석한다 (계획 0-2).
# naive 로 두면 실행 환경에 따라 어긋난다.
_BOOST_FMTS = ("%Y-%b-%d %H:%M:%S.%f", "%Y-%b-%d %H:%M:%S")  # 함정 6
_NGINX_FMT = "%Y/%m/%d %H:%M:%S"
_THRIFT_FMT = "%a %b %d %H:%M:%S %Y"
_CSV_FMTS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")  # trace=start_time / metric=timestamp


class Record(NamedTuple):
    """`(시각, 원본 줄)`. `line` 은 줄바꿈 문자까지 포함한 원본 그대로다."""

    ts: datetime
    line: str


class CsvSource(NamedTuple):
    """CSV 한 개. 라이터가 헤더를 먼저 써야 하므로 헤더를 행과 분리해 돌려준다 (계획 0-1).

    파일이 없거나 0바이트면 `header is None`, `rows` 는 0건이다.
    """

    header: str | None
    rows: Iterator[Record]


def parse_boost(s: str) -> datetime:
    """계획 0-2 의 규칙 파서. 마이크로초 없는 변형(함정 6)까지 받는다."""
    for fmt in _BOOST_FMTS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    raise ValueError(s)


def _parse(s: str, fmts: tuple[str, ...]) -> datetime:
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    raise ValueError(s)


def _lines(path: Path) -> Iterator[str]:
    """원본 줄을 바이트 그대로 흘린다. 파일 부재·0바이트는 정상 — 0건 (함정 2).

    27MB 파일이 있으므로 제너레이터로 흘린다. 전량 리스트 적재 금지 (함정 5).
    `newline=""` 로 개행 변환을 끄고 `surrogateescape` 로 비 UTF-8 바이트까지 보존해,
    받은 줄을 그대로 되쓰면 원본과 바이트 동일하다.
    """
    if not path.is_file():
        return
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
        yield from f


def read_log(path: str | Path) -> Iterator[Record]:
    """boost 평문 로그 (`<Service>_.log`). 줄 맨 앞 `[...]` 가 시각이다 (계획 0-2)."""
    last_ts: datetime | None = None
    for line in _lines(Path(path)):
        m = BOOST.match(line)
        if m:
            last_ts = parse_boost(m.group(1))
        else:
            t = THRIFT.match(line)
            if t:
                last_ts = _parse(t.group(1), (_THRIFT_FMT,))
            elif last_ts is None:
                # 첫 줄부터 시각이 없으면 이어붙일 앞 줄이 없다 — 조용히 버리지 않고 알린다.
                raise ValueError(f"{path}: 시각 없는 첫 줄: {line[:80]!r}")
            # 그 외 시각 없는 줄은 앞 레코드의 연속으로 보고 앞 시각을 물려준다.
            # 줄을 버리면 "누락 없음"(계획 0-5)이 깨진다. MVP 3종에서는 0건.
        yield Record(last_ts, line)


def read_nginx(path: str | Path) -> Iterator[Record]:
    """nginx error_log (`NginxThrift_.log`). 줄 맨 앞, 대괄호 없음 (계획 0-2).

    Perf_CPU / Svc_Kill 에서는 이 파일이 0바이트다 → 0건 (함정 2).
    """
    for line in _lines(Path(path)):
        m = NGINX.match(line)
        if not m:
            raise ValueError(f"{path}: nginx 시각을 찾지 못함: {line[:80]!r}")
        yield Record(_parse(m.group(1), (_NGINX_FMT,)), line)


def _csv_rows(path: Path, index: int) -> Iterator[Record]:
    for i, line in enumerate(_lines(path)):
        if i == 0:
            continue  # 헤더는 read_csv() 가 이미 돌려줬다
        # 줄을 해석하지 않는다 — 시각 컬럼 하나만 꺼내고 줄은 통째로 들고 간다.
        # 임베디드 개행이 없음을 3종 전수 확인했으므로 물리 줄 1개 = 레코드 1개다.
        fields = next(csv.reader([line]))
        yield Record(_parse(fields[index], _CSV_FMTS), line)


def read_csv(path: str | Path, ts_column: str) -> CsvSource:
    """metric CSV(`timestamp`) 와 `all_traces.csv`(`start_time`).

    정렬하지 않는다 — 원본 순서 그대로 흘린다. `all_traces.csv` 와 metric 7종이 시간순이
    아니지만, 정렬은 스케줄러 몫이다 (계획 0-6'). 리더는 어느 파일에도 순서를 부여하지 않는다.
    """
    p = Path(path)
    header: str | None = next(_lines(p), None)  # 파일 부재·0바이트 → None
    if header is None:
        return CsvSource(None, iter(()))
    index = next(csv.reader([header])).index(ts_column)
    return CsvSource(header, _csv_rows(p, index))
