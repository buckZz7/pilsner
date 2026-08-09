#!/usr/bin/env bash
# Ternary re-run on the NEW llama.cpp build (the old build can't load
# tensor type 42 — the ternary quant format).
#
# Prereqs: build2 finished (llama_build.log says BUILD_DONE), ladder
# completed. Usage on the eval box: bash _rerun_ternary.sh
set -euo pipefail
SERV=/root/llama.cpp/build2/bin/llama-server
T2=/root/tau2-bench
cd /root/pilsner
mkdir -p /root/receipts

if [ ! -x "$SERV" ]; then
  echo "build2 server missing — is the rebuild done?"; exit 1
fi
echo "new build: $(cd /root/llama.cpp && git rev-parse --short HEAD)"

if [ -f "/root/receipts/report_tau2_seed3.json" ]; then
  echo "ternary receipt already exists — nothing to do"; exit 0
fi

echo "=== BATTERY bonsai-ternary (NEW build) ==="
"$SERV" --host 0.0.0.0 --port 8000 -m /root/models/bonsai-ternary/Ternary-Bonsai-27B-Q2_0.gguf \
  -c 32768 --parallel 2 --cache-type-k q8_0 --cache-type-v q8_0 \
  --reasoning off --no-webui > /root/serve_bonsai-ternary.log 2>&1 &
pid=$!
ok=""
for i in $(seq 1 120); do
  if curl -s http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then ok=1; break; fi
  if ! kill -0 $pid 2>/dev/null; then echo "server died:"; tail -5 /root/serve_bonsai-ternary.log; break; fi
  sleep 2
done
if [ -z "$ok" ]; then echo "ternary server failed to start"; exit 1; fi

PILSNER_MODEL=bonsai-ternary \
PILSNER_BASE_URL=http://127.0.0.1:8000/v1 \
PILSNER_T2_DIR=$T2 \
PILSNER_T2_TASKS=50 \
PILSNER_T2_TRIALS=1 \
PILSNER_T2_MAX_STEPS=50 \
PILSNER_T2_MAX_STEPS_SECONDS=600 \
PILSNER_SEED=3 \
PILSNER_REASONING=off \
PILSNER_ENGINE=llama.cpp \
PILSNER_ENGINE_VERSION=$("$SERV" --version 2>/dev/null | grep -aoE "[0-9a-f]{7,}" | head -1 || echo unknown) \
PILSNER_PARALLEL=2 \
PILSNER_CTX=16384 \
PILSNER_OUT=/root/receipts \
python3 -m arena.run_tau2 || echo "TERNARY RERUN FAILED"
kill $pid 2>/dev/null || true
echo "TERNARY_RERUN_DONE"
