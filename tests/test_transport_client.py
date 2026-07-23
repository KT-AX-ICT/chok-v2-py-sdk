"""TransportClient.send 단위 테스트 — 실서버 응답 형태 편차에 대한 방어(2026-07-23).

실물 E2E(code_media, 실제 FastAPI)에서 서버가 `job_id`를 정수(DB PK)로 돌려줬는데
`SubmissionResult.job_id: str` 고정이라 pydantic ValidationError 가 나며 rca-collect
프로세스 전체가 죽었다. httpx.post 는 모듈 레벨 함수 호출이라 monkeypatch 로 스텁한다.
"""

from __future__ import annotations

import json
from datetime import datetime

import httpx

from rca_sdk.schemas.snapshot import SnapshotBundle, TriggerInfo, Window
from rca_sdk.transport.client import TransportClient

TS = datetime(2026, 1, 1)


def _bundle() -> SnapshotBundle:
    return SnapshotBundle(
        window=Window(start=TS, end=TS),
        trigger_info=TriggerInfo(trigger_time=TS, triggered_by=["log"]),
    )


class _FakeResponse:
    def __init__(self, status_code: int, body) -> None:
        self.status_code = status_code
        self._body = body
        self.request = httpx.Request("POST", "http://x")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=self.request, response=self)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def test_send_accepts_integer_job_id(monkeypatch):
    # 실서버 사례 재현: {"accepted": true, "job_id": 2}
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _FakeResponse(201, {"accepted": True, "job_id": 2})
    )
    result = TransportClient("http://x/ingest").send(_bundle())
    assert result.accepted is True
    assert result.job_id == 2
    assert result.error is None


def test_send_survives_non_integer_job_id(monkeypatch):
    # job_id 는 실서버(DB PK) 기준 int 로 고정했다 — 그런데도 서버가 다시 형식을 바꿔서
    # (예: UUID 문자열) 보내는 미래에도, 방어 코드(ValueError 처리)가 살아있어야 한다.
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _FakeResponse(201, {"accepted": True, "job_id": "uuid-1"})
    )
    result = TransportClient("http://x/ingest").send(_bundle())
    assert result.accepted is True  # 전송 자체는 성공(2xx) — 프로세스가 죽지 않는다
    assert result.error is not None


def test_send_handles_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(500, {}))
    result = TransportClient("http://x/ingest").send(_bundle())
    assert result.accepted is False
    assert result.error is not None


def test_send_survives_unparseable_response_body(monkeypatch):
    # 2xx 인데 바디가 JSON 이 아니거나 SubmissionResult 검증을 못 통과하는 경우 —
    # HTTP 레벨 전송(raise_for_status 통과)은 이미 성공했으므로 accepted=True 로 보고하고,
    # 파싱 실패 사실만 error 에 남긴다 (accepted=False 로 잘못 보고하지 않는다).
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _FakeResponse(200, json.JSONDecodeError("x", "y", 0))
    )
    result = TransportClient("http://x/ingest").send(_bundle())
    assert result.accepted is True
    assert result.error is not None


def test_send_treats_non_dict_response_as_empty(monkeypatch):
    # 2xx 인데 바디가 dict 가 아닌 경우(예: 리스트) — data.get() 이 AttributeError 로 죽지 않아야
    # 한다.
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(200, [1, 2, 3]))
    result = TransportClient("http://x/ingest").send(_bundle())
    assert result.accepted is True  # data.get 기본값(True)로 떨어짐
    assert result.job_id is None
