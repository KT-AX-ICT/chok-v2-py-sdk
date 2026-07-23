#!/usr/bin/env bash
# 로컬 개발용 편의 스크립트 — 리플레이어와 rca-collect 를 한 번에 띄운다.
#
# rca-collect(src/rca_sdk) 는 실서비스 진입점이라 var/{log,metric,trace} 가 이미 존재하는
# "진짜" 로그 경로라고 가정하고, 없으면 즉시 실패한다(collectors/tail.py 의
# validate_source_layout). 리플레이어(demo/replayer)는 그 자리에 SN 데이터셋을 타임시프트
# 재생해 채워주는 로컬 전용 도구라 pyproject.toml 에 등록돼 있지 않다 — 그래서 rca-collect 가
# 직접 리플레이어를 실행하도록 묶지 않고, 이 스크립트에서만 둘을 함께 띄운다.
#
# 실행 전에 ingest 서버(예: scripts/mock_ingest_server.py, 또는 RCA_COLLECT_ENDPOINT 로
# 지정한 실제 서버)가 떠 있어야 번들 전송이 성공한다.
#
# 사용법: scripts/run_local_demo.sh <scenario: cpu|kill_media|code_media> [duration_sec]
#   duration_sec 생략 시 데이터 끝까지 재생한다.

set -euo pipefail
cd "$(dirname "$0")/.."

SCENARIO="${1:?사용법: scripts/run_local_demo.sh <scenario: cpu|kill_media|code_media> [duration_sec]}"
DURATION="${2:-}"

REPLAY_PID=""
COLLECT_PID=""

cleanup() {
  echo "[run_local_demo] 종료 처리 중..."
  [[ -n "$COLLECT_PID" ]] && kill -TERM "$COLLECT_PID" 2>/dev/null || true
  [[ -n "$REPLAY_PID" ]] && kill -TERM "$REPLAY_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 배열(DURATION_ARGS=())을 "${arr[@]}"로 확장하면 macOS 기본 bash(3.2)에서 `set -u` 와 맞물려
# "unbound variable" 로 죽는 구버전 버그가 있다 — 배열 대신 분기로 우회한다.
if [[ -n "$DURATION" ]]; then
  echo "[run_local_demo] 리플레이어 시작: $SCENARIO ${DURATION}초"
  python -m demo.replayer "$SCENARIO" --reset --duration "$DURATION" &
else
  echo "[run_local_demo] 리플레이어 시작: $SCENARIO (끝까지)"
  python -m demo.replayer "$SCENARIO" --reset &
fi
REPLAY_PID=$!

sleep 2

echo "[run_local_demo] rca-collect 시작"
rca-collect &
COLLECT_PID=$!

wait "$REPLAY_PID"
echo "[run_local_demo] 리플레이어 종료됨 — rca-collect 는 계속 돕니다 (Ctrl+C 로 둘 다 종료)."
wait "$COLLECT_PID"
