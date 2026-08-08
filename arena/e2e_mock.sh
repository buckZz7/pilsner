#!/usr/bin/env bash
# GPU-free end-to-end check of the tau2 arena plumbing.
# Starts the mock OpenAI server, runs the arena runner against it,
# expects a receipt. Requires a tau2-bench checkout (uv sync'ed).
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${MOCK_PORT:-8999}"
T2_DIR="${PILSNER_T2_DIR:-$PWD/../tau2-bench}"

python3 arena/mock_openai.py "$PORT" &
MOCK_PID=$!
trap 'kill $MOCK_PID 2>/dev/null || true' EXIT
sleep 0.7

PILSNER_MODEL=mock \
PILSNER_BASE_URL="http://127.0.0.1:$PORT/v1" \
PILSNER_T2_DIR="$T2_DIR" \
PILSNER_T2_TASKS=2 \
PILSNER_T2_TRIALS=1 \
PILSNER_T2_MAX_STEPS=4 \
PILSNER_SEED=1 \
PILSNER_OUT=outputs \
python3 -m arena.run_tau2

echo "---"
ls -la outputs/report_tau2_seed1.json
