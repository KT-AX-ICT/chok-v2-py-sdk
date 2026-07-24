#!/usr/bin/env bash
# SN 원본 infinite simulator + 기존 rca-collect 단일 실행 스크립트.
#
# TODO(timestamp-contract): SDK/FastAPI/Spring timestamp 계약이 정리되기 전에는
# trigger/bundle 생성 후 Spring 저장이 422로 실패할 수 있다. 이 스크립트는 계약을 바꾸지 않는다.

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -z "${RCA_SOURCE_ROOT:-}" ]]; then
  RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  export RCA_SOURCE_ROOT="./var/demo-runs/$RUN_ID"
fi

for modality in log metric trace; do
  directory="$RCA_SOURCE_ROOT/$modality"
  mkdir -p "$directory"
  if find "$directory" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
    echo "[run_demo_server] 오류: RCA_SOURCE_ROOT는 빈 실행 경로여야 합니다: $directory" >&2
    exit 2
  fi
done

echo "[run_demo_server] source_root=$RCA_SOURCE_ROOT"
echo "[run_demo_server] 의존성/진입점 확인"
uv run python -c "import demo.simulator, rca_sdk"

SIMULATOR_PID=""
COLLECTOR_PID=""

cleanup() {
  trap - EXIT INT TERM
  [[ -n "$COLLECTOR_PID" ]] && kill -TERM "$COLLECTOR_PID" 2>/dev/null || true
  [[ -n "$SIMULATOR_PID" ]] && kill -TERM "$SIMULATOR_PID" 2>/dev/null || true
  [[ -n "$COLLECTOR_PID" ]] && wait "$COLLECTOR_PID" 2>/dev/null || true
  [[ -n "$SIMULATOR_PID" ]] && wait "$SIMULATOR_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[run_demo_server] rca-collect 시작"
uv run --no-sync rca-collect &
COLLECTOR_PID=$!

echo "[run_demo_server] simulator 시작"
uv run --no-sync python -m demo.simulator "$@" &
SIMULATOR_PID=$!

while kill -0 "$COLLECTOR_PID" 2>/dev/null && kill -0 "$SIMULATOR_PID" 2>/dev/null; do
  sleep 1
done

status=0
if ! kill -0 "$COLLECTOR_PID" 2>/dev/null; then
  wait "$COLLECTOR_PID" || status=$?
  echo "[run_demo_server] rca-collect 종료(status=$status)" >&2
else
  wait "$SIMULATOR_PID" || status=$?
  echo "[run_demo_server] simulator 종료(status=$status)" >&2
fi
exit "$status"
