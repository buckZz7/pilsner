#!/usr/bin/env bash
# IQ1 cliff-pinning batteries: IQ1_S (~1.6 bpw) + IQ1_M (~1.75 bpw) for
# Qwen3.6-27B (mradermacher i1 imatrix quants). Answer: is the 1-bit
# collapse bit-depth or group-scale-resolution?
#   - IQ1_S survives + Q1_0 dies -> collapse is scale granularity;
#     a finer-group 1-bit quant is fixable.
#   - IQ1_S dies like Q1_0 -> the cliff is real below ~2 bpw.
# Uses the OLD build (consistent with the ladder; IQ-series loads fine).
# Usage on the eval box after the ladder: bash _iq1_batteries.sh
set -euo pipefail
SERV=/root/llama.cpp/build/bin/llama-server
T2=/root/tau2-bench
cd /root/pilsner
mkdir -p /root/receipts

run_iq1() {
  local name=$1 gguf=$2 seed=$3
  if [ -f "/root/receipts/report_tau2_seed$seed.json" ]; then
    echo "=== $name SKIPPED (receipt exists) ==="; return 0
  fi
  echo "=== BATTERY $name (cliff-pinning) ==="
  "$SERV" --host 0.0.0.0 --port 8000 -m "$gguf" -c 32768 --parallel 2 \
    --cache-type-k q8_0 --cache-type-v q8_0 --reasoning off --no-webui \
    > /root/serve_$name.log 2>&1 &
  local pid=$!
  local ok=""
  for i in $(seq 1 90); do
    if curl -s http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then ok=1; break; fi
    if ! kill -0 $pid 2>/dev/null; then echo "server died:"; tail -5 /root/serve_$name.log; break; fi
    sleep 2
  done
  if [ -z "$ok" ]; then echo "$name server failed"; return 1; fi
  PILSNER_MODEL=$name \
  PILSNER_BASE_URL=http://127.0.0.1:8000/v1 \
  PILSNER_T2_DIR=$T2 \
  PILSNER_T2_TASKS=50 \
  PILSNER_T2_TRIALS=1 \
  PILSNER_T2_MAX_STEPS=50 \
  PILSNER_T2_MAX_STEPS_SECONDS=600 \
  PILSNER_SEED=$seed \
  PILSNER_REASONING=off \
  PILSNER_ENGINE=llama.cpp \
  PILSNER_ENGINE_VERSION=$("$SERV" --version 2>/dev/null | grep -aoE "[0-9a-f]{7,}" | head -1 || echo unknown) \
  PILSNER_MODEL_SHA256=$(sha256sum "$gguf" 2>/dev/null | cut -d' ' -f1) \
  PILSNER_GPU_CLOCK=$(nvidia-smi --query-gpu=clocks.gr --format=csv,noheader 2>/dev/null | head -1) \
  PILSNER_PARALLEL=2 \
  PILSNER_CTX=16384 \
  PILSNER_OUT=/root/receipts \
  python3 -m arena.run_tau2 || echo "BATTERY $name FAILED"
  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true
  sleep 3
}

run_iq1 qwen36-iq1s /root/models/qwen36-iq1s/Qwen3.6-27B-IQ1_S.gguf 7
run_iq1 qwen36-iq1m /root/models/qwen36-iq1m/Qwen3.6-27B-IQ1_M.gguf 8
echo "IQ1_BATTERIES_DONE"
