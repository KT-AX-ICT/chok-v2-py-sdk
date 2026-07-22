"""표준 라이브러리만 쓰는 mock ingest 서버 (계획 06 §1).

rca-collect 가 트리거 시 보내는 SnapshotBundle 을 받아 window·trigger_info·모달리티별
레코드 수를 한 줄 로그로 남기고 200 을 돌려준다. `demo/replayer` 와 같은 이유로
pyproject.toml 에 등록하지 않는다 — 등록하면 wheel 에 들어가 실서비스 설치본에 딸려간다.

실행(저장소 루트에서): python scripts/mock_ingest_server.py
"""

from __future__ import annotations

import io
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8000  # settings.collect_endpoint 기본값(http://localhost:8000/ingest)에 맞춘다


def summarize(bundle: dict) -> str:
    """수신 로그 한 줄. window·trigger_info·모달리티별 레코드 수만 뽑는다."""
    window = bundle.get("window", {})
    trigger = bundle.get("trigger_info", {})
    triggered_by = ",".join(trigger.get("triggered_by", []))
    return (
        f"[수신] window={window.get('start')}~{window.get('end')} "
        f"trigger={trigger.get('trigger_time')}({triggered_by}) "
        f"logs={len(bundle.get('logs', []))} "
        f"metrics={len(bundle.get('metrics', []))} "
        f"traces={len(bundle.get('traces', []))}"
    )


class IngestHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/ingest":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        bundle = json.loads(self.rfile.read(length))
        print(summarize(bundle))
        body = json.dumps({"accepted": True, "job_id": "mock"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass  # 접속 로그 기본 출력은 끈다 — summarize() 한 줄이면 충분


def main() -> None:
    # Windows 기본 콘솔은 cp949 라 '—' 를 못 찍고 죽는다 (demo/replayer/cli.py 와 같은 이유).
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")

    server = HTTPServer(("0.0.0.0", PORT), IngestHandler)
    print(f"mock ingest 서버 시작 — http://localhost:{PORT}/ingest")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료됨.")


if __name__ == "__main__":
    main()
