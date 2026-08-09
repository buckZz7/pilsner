#!/usr/bin/env bash
# Companion battery: Bonsai 1-bit + Q8 with THINKING ON (their
# methodology: thinking mode, matched config) — the apples-to-apples
# reproduction of PrismML's tau2 claims on our box.
#
# Run AFTER the ladder + the MTP probe (probe must show thinking
# terminates; runaways make this battery meaningless). Usage on the eval
# box: bash _companion_battery.sh
set -euo pipefail
SERV=/root/llama.cpp/build/bin/llama-server
T2=/root/tau2-bench
cd /root/pilsner
mkdir -p /root/receipts

BONSAI_1BIT=/root/models/bonsai-1bit/Bonsai-27B-Q1_0.gguf
Q8=/root/models/qwen36-q8/Qwen3.6-27B-Revised-q8_0.gguf

run_battery() {
  local name=$1 gguf=$2 seed=$3
  if [ -f "/root/receipts/report_tau2_seed$seed.json" ]; then
    echo "=== $name SKIPPED (receipt exists) ==="; return 0
  fi
  echo "=== COMPANION $name (reasoning ON) ==="
  # reasoning on, otherwise identical to the ladder rung
  "$SERV" --host 0.0.0.0 --port 8000 -m "$gguf" -c 32768 --parallel 2 \
    --cache-type-k q8_0 --cache-type-v q8_0 --reasoning on --no-webui \
    > /root/serve_${name}_think.log 2>&1 &
  local pid=$!
  local ok=""
  for i in $(seq 1 90); do
    if curl -s http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  if [ -z "$ok" ]; then echo "$name server failed"; kill $pid 2>/dev/null || true; return 1; fi
  PILSNER_MODEL=$name \
  PILSNER_BASE_URL=http://127.0.0.1:8000/v1 \
  PILSNER_T2_DIR=$T2 \
  PILSNER_T2_TASKS=50 \
  PILSNER_T2_TRIALS=1 \
  PILSNER_T2_MAX_STEPS=50 \
  PILSNER_T2_MAX_STEPS_SECONDS=600 \
  PILSNER_SEED=$seed \
  PILSNER_REASONING=on \
  PILSNER_ENGINE=llama.cpp \
  PILSNER_ENGINE_VERSION=$("$SERV" --version 2>/dev/null | grep -aoE "[0-9a-f]{7,}" | head -1 || echo unknown) \
  PILSNER_PARALLEL=2 \
  PILSNER_CTX=16384 \
  PILSNER_OUT=/root/receipts \
  python3 -m arena.run_tau2 || echo "COMPANION $name FAILED"
  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true
  sleep 3
}

# seeds 31/32: companion slots (thinking-on receipts)
run_battery bonsai-1bit-think "$BONSAI_1BIT" 31
run_battery qwen36-q8-think   "$Q8"          32
echo "COMPANION_DONE"
echo "compare: report_tau2_seed31 (1-bit thinking) vs seed2 (1-bit off);"
echo "         report_tau2_seed32 (Q8 thinking) vs seed1 (Q8 off)"
