"""FastAPI 수집 API 전송 클라이언트 (스캐폴드).

트리거 발화 시에만 번들을 전송한다 (정상 구간 전송 없음). 계약은 docs/api-contract.md.
"""

from __future__ import annotations

import httpx

from rca_sdk.schemas.snapshot import SnapshotBundle


class TransportClient:
    def __init__(self, endpoint: str, timeout: float = 10.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def send(self, bundle: SnapshotBundle) -> dict:
        """번들을 POST 하고 서버 응답(job_id 등)을 반환한다."""
        # TODO: 재시도/백오프. 우선 최소 전송만.
        resp = httpx.post(
            self.endpoint,
            content=bundle.model_dump_json(),
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()
