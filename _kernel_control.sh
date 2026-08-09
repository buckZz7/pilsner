#!/usr/bin/env bash
# Kernel control: Bonsai 1-bit vs Q8 on the eval/ FC harness (simple
# single-call tasks).
#
# Decent Bonsai score here + failure on tau2's complex schemas =
# genuine precision collapse (the quant loses arg accuracy, not the
# engine). Failure EVERYWHERE = Q1_0 kernel artifact in this llama.cpp
# build (degrading more than the weights).
#
# Usage on the eval box AFTER the ladder: bash _kernel_control.sh
set -euo pipefail
SERV=/root/llama.cpp/build/bin/llama-server
cd /root/pilsner
mkdir -p /root/ctrl_out

BONSAI=/root/models/bonsai-1bit/Bonsai-27B-Q1_0.gguf
Q8=/root/models/qwen36-q8/Qwen3.6-27B-Revised-q8_0.gguf

run_control() {
  local name=$1 gguf=$2
  "$SERV" --host 0.0.0.0 --port 8000 -m "$gguf" -c 16384 --parallel 1 \
    --cache-type-k q8_0 --cache-type-v q8_0 --reasoning off --no-webui \
    > /root/ctrl_$name.log 2>&1 &
  local pid=$!
  local ok=""
  for i in $(seq 1 90); do
    if curl -s http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  if [ -z "$ok" ]; then echo "CTRL $name server failed"; kill $pid 2>/dev/null || true; return 1; fi
  echo "== control: $name =="
  PILSNER_MODEL=$name \
  PILSNER_BASE_URL=http://127.0.0.1:8000/v1 \
  PILSNER_SEED=41 \
  PILSNER_CATALOG=mixed \
  PILSNER_OUT=/root/ctrl_out \
  python3 -m eval.runner || echo "CTRL $name FAILED"
  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true
  sleep 3
}

run_control bonsai-1bit "$BONSAI"
run_control qwen36-q8   "$Q8"
echo "CONTROL_DONE — compare the two report_seed41.json files in /root/ctrl_out"
