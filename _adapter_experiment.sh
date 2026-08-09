#!/usr/bin/env bash
# Adapter experiment: Bonsai 1-bit through the entity-inject proxy.
# If the score lifts off the 0.16 baseline (seed2), the serving-layer
# thesis is proven: part of the 1-bit collapse is fixable by salient
# entity re-injection. The arena's first challenger, measured on its
# own ruler.
#
# Usage on the eval box after the ladder: bash _adapter_experiment.sh
set -euo pipefail
SERV=/root/llama.cpp/build/bin/llama-server
T2=/root/tau2-bench
cd /root/pilsner
mkdir -p /root/receipts
SEED=9

if [ -f "/root/receipts/report_tau2_seed$SEED.json" ]; then
  echo "adapter battery already exists — nothing to do"; exit 0
fi

echo "=== serving bonsai-1bit on :8001 ==="
"$SERV" --host 0.0.0.0 --port 8001 -m /root/models/bonsai-1bit/Bonsai-27B-Q1_0.gguf \
  -c 32768 --parallel 2 --cache-type-k q8_0 --cache-type-v q8_0 \
  --reasoning off --no-webui > /root/serve_bonsai-1bit-adapter.log 2>&1 &
pid=$!
ok=""
for i in $(seq 1 90); do
  if curl -s http://127.0.0.1:8001/v1/models >/dev/null 2>&1; then ok=1; break; fi
  if ! kill -0 $pid 2>/dev/null; then echo "server died:"; tail -5 /root/serve_bonsai-1bit-adapter.log; break; fi
  sleep 2
done
if [ -z "$ok" ]; then echo "server failed"; exit 1; fi

echo "=== starting entity-inject adapter :8000 -> :8001 ==="
nohup python3 -m arena.adapter_entity_inject --listen 8000 \
  --upstream http://127.0.0.1:8001/v1 > /root/adapter.log 2>&1 &
apid=$!
sleep 2

echo "=== BATTERY bonsai-1bit + adapter (seed $SEED) ==="
PILSNER_MODEL=bonsai-1bit-adapter \
PILSNER_BASE_URL=http://127.0.0.1:8000/v1 \
PILSNER_USER_MODEL=openai/bonsai-1bit \
PILSNER_USER_BASE_URL=http://127.0.0.1:8001/v1 \
PILSNER_T2_DIR=$T2 \
PILSNER_T2_TASKS=50 \
PILSNER_T2_TRIALS=1 \
PILSNER_T2_MAX_STEPS=50 \
PILSNER_T2_MAX_STEPS_SECONDS=600 \
PILSNER_SEED=$SEED \
PILSNER_REASONING=off \
PILSNER_ENGINE=llama.cpp \
PILSNER_ENGINE_VERSION=$("$SERV" --version 2>/dev/null | grep -aoE "[0-9a-f]{7,}" | head -1 || echo unknown) \
PILSNER_PARALLEL=2 \
PILSNER_CTX=16384 \
PILSNER_OUT=/root/receipts \
python3 -m arena.run_tau2 || echo "ADAPTER BATTERY FAILED"

kill $apid 2>/dev/null || true
kill $pid 2>/dev/null || true
echo "ADAPTER_EXPERIMENT_DONE"
echo "compare: seed$SEED (adapter) vs seed2 (baseline 0.16)"
