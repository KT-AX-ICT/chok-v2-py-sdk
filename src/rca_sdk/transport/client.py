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
                content=bundle.model_dump_json(by_alias=True),
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                data = {}
            return SubmissionResult(accepted=data.get("accepted", True), job_id=data.get("job_id"))
        except httpx.HTTPError as e:
            return SubmissionResult(accepted=False, error=str(e))
        except ValueError as e:
            # resp.json() 이 JSON 이 아니거나(JSONDecodeError), 응답 형태가 SubmissionResult
            # 검증을 통과 못함(pydantic ValidationError — ValueError 서브클래스) — 둘 다 여기.
            # raise_for_status() 를 이미 통과했으므로 서버는 2xx 로 수신·처리했다는 뜻이라,
            # accepted=False 로 잘못 보고하지 않는다(실전에서 job_id 타입 불일치로 이 경로를
            # 안 타면 프로세스 전체가 죽었었다, 2026-07-23).
            return SubmissionResult(accepted=True, error=f"응답 파싱 실패(전송 자체는 성공): {e}")
