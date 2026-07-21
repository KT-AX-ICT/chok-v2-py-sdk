"""FastAPI 수집 API 전송 계층 (스캐폴드).

트리거 발화 시에만 번들을 전송한다 (정상 구간 전송 없음). send 는 SubmissionResult 를 반환하며,
네트워크 오류 시 예외를 던지지 않고 accepted=False 로 담아 반환한다 (interface-contract §3).
계약은 docs/api-contract.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from rca_sdk.schemas.snapshot import SnapshotBundle, SubmissionResult


class Transport(ABC):
    @abstractmethod
    def send(self, bundle: SnapshotBundle) -> SubmissionResult:
        """번들을 전송하고 결과(SubmissionResult)를 반환한다."""
        raise NotImplementedError


class TransportClient(Transport):
    def __init__(self, endpoint: str, timeout: float = 10.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def send(self, bundle: SnapshotBundle) -> SubmissionResult:
        # TODO: 재시도/백오프, 인증 — 서버팀과 미확정 (docs/api-contract.md).
        try:
            resp = httpx.post(
                self.endpoint,
                content=bundle.model_dump_json(),
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            return SubmissionResult(accepted=False, error=str(e))
        return SubmissionResult(accepted=data.get("accepted", True), job_id=data.get("job_id"))
