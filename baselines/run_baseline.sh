#!/usr/bin/env bash
# Serve any stock model + run the harness against it.
# Base-agnostic: pass any HF id. Example for a fresh base:
#   ./baselines/run_baseline.sh Qwen/Qwen3.8-27B qwen3.8-27b 1
set -euo pipefail

HF_ID="${1:?usage: run_baseline.sh <hf_model_id> <served_name> [seed] [port]}"
NAME="${2:?usage: run_baseline.sh <hf_model_id> <served_name> [seed] [port]}"
SEED="${3:-1}"
PORT="${4:-8000}"

export PILSNER_MODEL="$NAME"
export PILSNER_BASE_URL="http://localhost:$PORT/v1"
export PILSNER_SEED="$SEED"

echo "== Serving $HF_ID as $NAME on :$PORT =="
python -m vllm.entrypoints.openai.api_server \
  --model "$HF_ID" \
  --served-model-name "$NAME" \
  --dtype auto \
  --max-model-len 8192 \
  --port "$PORT" &
SERVER_PID=$!

trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

echo "== Waiting for server =="
for i in $(seq 1 60); do
  if curl -sf "$PILSNER_BASE_URL/models" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "== Running harness (seed $SEED) =="
cd "$(dirname "$0")/.."
python -m eval.runner

echo "== Done. Report: outputs/report_seed${SEED}.json =="
