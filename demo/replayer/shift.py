"""시프트 — 시각을 재생 시점으로 옮기고 **줄 안의 타임스탬프만** 치환한다 (계획 Phase 2).

`new_ts = T0 + (orig_ts - t0)`. 개별 시각을 독립적으로 바꾸지 않고 하나의 앵커에서 평행이동하므로
원본의 간격이 그대로 남는다 (계획 0-5 "간격 보존").

줄의 나머지 부분은 건드리지 않는다. 타임스탬프의 **바이트 범위만** 잘라내 새 값을 끼운다.
`str.replace()` 를 쓰지 않는다 — 같은 문자열이 메시지 본문에도 있으면 거기까지 바뀐다.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .readers import BOOST, NGINX, THRIFT

# strftime 의 `%b`/`%a` 는 로케일에 따라 바뀐다. 출력 바이트가 실행 환경에 좌우되면 안 되므로
# 이름을 직접 박는다. 원본은 C 로케일로 찍혔다.
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")  # datetime.weekday(): 월=0


def measure_t0(timestamps: Iterable[datetime]) -> datetime:
    """시나리오의 기준 시각 = **전 모달리티 통틀어 실측 min** (계획 함정 4).

    폴더명의 시각을 쓰면 안 된다. 모달리티마다 수집 시작이 달라, 모달리티별 t0 을 쓰면 trace 가
    126~179초 앞당겨져 원본에 없던 정렬이 생긴다 (계획 0-3). 세 모달리티에 **같은 t0** 을 써야 한다.

    비어 있으면 `min()` 이 ValueError 를 낸다 — 재생할 게 없다는 뜻이라 조용히 넘기지 않는다.
    """
    return min(timestamps)


def shift_ts(ts: datetime, t0: datetime, anchor: datetime) -> datetime:
    """`anchor + (ts - t0)`. `anchor` 는 재생 시작 시각으로, 실행 내내 **고정**이다.

    레코드마다 `now()` 를 다시 부르면 간격이 실행 속도에 좌우돼 원본과 달라진다.
    """
    return anchor + (ts - t0)


def _render_boost(ts: datetime, micros: bool) -> str:
    s = (
        f"{ts.year:04d}-{_MONTHS[ts.month - 1]}-{ts.day:02d} "
        f"{ts.hour:02d}:{ts.minute:02d}:{ts.second:02d}"
    )
    return f"{s}.{ts.microsecond:06d}" if micros else s


def _render_nginx(ts: datetime) -> str:
    return (
        f"{ts.year:04d}/{ts.month:02d}/{ts.day:02d} "
        f"{ts.hour:02d}:{ts.minute:02d}:{ts.second:02d}"
    )


def _render_thrift(ts: datetime) -> str:
    """C `asctime` — `Tue Nov  4 02:58:25 2025`.

    일자는 **공백으로 폭 2 채움**(`%e`)이라 `{:2d}` 다. `%e` 는 Windows strftime 에 없다.
    """
    return (
        f"{_DAYS[ts.weekday()]} {_MONTHS[ts.month - 1]} {ts.day:2d} "
        f"{ts.hour:02d}:{ts.minute:02d}:{ts.second:02d} {ts.year:04d}"
    )


def _render_csv(ts: datetime, micros: bool) -> str:
    s = (
        f"{ts.year:04d}-{ts.month:02d}-{ts.day:02d} "
        f"{ts.hour:02d}:{ts.minute:02d}:{ts.second:02d}"
    )
    return f"{s}.{ts.microsecond:06d}" if micros else s


def _splice(line: str, start: int, end: int, value: str) -> str:
    return line[:start] + value + line[end:]


def shift_log_line(line: str, new_ts: datetime) -> str:
    """boost 로그 한 줄 (`read_log` 와 짝). BOOST → THRIFT 순으로 찾는다.

    시각이 없는 줄은 **그대로 돌려준다.** `read_log` 가 그런 줄에 앞 레코드의 시각을 물려주므로
    여기로 들어오지만, 치환할 문자열이 없다. 버리면 "누락 없음"(계획 0-5)이 깨진다.
    """
    m = BOOST.match(line)
    if m:
        s, e = m.span(1)
        # 마이크로초 없이 들어온 줄은 없이 내보낸다 (계획 함정 6 — 3종 통틀어 3줄 존재).
        return _splice(line, s, e, _render_boost(new_ts, "." in m.group(1)))
    t = THRIFT.match(line)
    if t:
        s, e = t.span(1)
        return _splice(line, s, e, _render_thrift(new_ts))
    return line


def shift_nginx_line(line: str, new_ts: datetime) -> str:
    """nginx error_log 한 줄 (`read_nginx` 와 짝)."""
    m = NGINX.match(line)
    if not m:
        return line
    s, e = m.span(1)
    return _splice(line, s, e, _render_nginx(new_ts))


def csv_field_span(line: str, index: int) -> tuple[int, int]:
    """CSV 한 줄에서 `index` 번째 필드의 **원본 바이트 범위**를 찾는다.

    `csv.writer` 로 되쓰지 않는 이유: `all_traces.csv` 의 `tags` 필드는 쉼표와 이스케이프된 따옴표를
    품고 있어(`"{""component"": ""nginx"", ...}"`), 재직렬화하면 인용 방식이 원본과 달라질 수 있다.
    타임스탬프 자리만 도려내면 나머지는 원본 바이트 그대로 남는다.
    """
    i, n, field = 0, len(line), 0
    start = 0
    while True:
        in_quotes = False
        start = i
        while i < n:
            c = line[i]
            if in_quotes:
                if c == '"':
                    if i + 1 < n and line[i + 1] == '"':
                        i += 2  # 이스케이프된 따옴표
                        continue
                    in_quotes = False
            elif c == '"':
                in_quotes = True
            elif c == ",":
                break
            i += 1
        if field == index:
            return start, i
        if i >= n:
            raise ValueError(f"필드 {index} 없음 (총 {field + 1}개): {line[:80]!r}")
        i += 1  # 쉼표를 건너뛴다
        field += 1


def shift_csv_line(line: str, ts_index: int, new_ts: datetime) -> str:
    """metric CSV(`timestamp`, 0번) 와 `all_traces.csv`(`start_time`, 5번) 한 줄 (`read_csv` 와 짝).

    metric 은 소수점이 없고 trace 는 6자리다 — 원본에 있던 대로 낸다.
    """
    s, e = csv_field_span(line, ts_index)
    return _splice(line, s, e, _render_csv(new_ts, "." in line[s:e]))
