#!/usr/bin/env bash
# Run the Pilsner reference ladder: 5 models x tau2 battery -> receipts.
set -euo pipefail
export PATH=/root/.local/bin:/usr/local/cuda-12.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:${LD_LIBRARY_PATH:-}

SERV=/root/llama.cpp/build/bin/llama-server
T2=/root/tau2-bench
cd /root/pilsner
mkdir -p /root/receipts

run_battery() {
  local name=$1 gguf=$2 ctx=$3 npar=$4
  if [ -f "/root/receipts/report_tau2_seed$SEED.json" ]; then
    echo "=== BATTERY $name SKIPPED (receipt exists, seed $SEED) ==="
    return 0
  fi
  echo "=== BATTERY $name (ctx=$ctx parallel=$npar) ==="
  "$SERV" --host 0.0.0.0 --port 8000 -m "$gguf" -c $ctx --parallel $npar --cache-type-k q8_0 --cache-type-v q8_0 --reasoning off --no-webui > /root/serve_$name.log 2>&1 &
  local pid=$!
  local ok=""
  for i in $(seq 1 90); do
    if curl -s http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then ok=1; break; fi
    if ! kill -0 $pid 2>/dev/null; then echo "server died:"; tail -5 /root/serve_$name.log; break; fi
    sleep 2
  done
  if [ -n "$ok" ]; then
    # smoke 1: plain completion — catch format-garbage or runaway thinking
    SMOKE=$(curl -s -m 45 http://127.0.0.1:8000/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"x","messages":[{"role":"user","content":"Say OK"}],"max_tokens":128}' | python3 -c "import json,sys; d=json.load(sys.stdin); m=(d.get('choices') or [{}])[0].get('message',{}); print('content:', repr((m.get('content') or '')[:30]), '| reasoning_len:', len(m.get('reasoning_content') or ''))" 2>/dev/null || echo SMOKE_TIMEOUT_EMPTY)
    echo "smoke1: $SMOKE"
    # smoke 2: tool call — the scored capability. Must emit valid tool_calls.
    SMOKE2=$(curl -s -m 45 http://127.0.0.1:8000/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"x","messages":[{"role":"user","content":"get_weather in Austin today"}],"tools":[{"type":"function","function":{"name":"get_weather","description":"weather for a city","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],"tool_choice":"auto","max_tokens":128}' | python3 -c "import json,sys; d=json.load(sys.stdin); m=(d.get('choices') or [{}])[0].get('message',{}); tc=m.get('tool_calls') or []; print('tool_calls:', len(tc), '| name:', (tc[0].get('function',{}).get('name') if tc else 'NONE'), '| args:', (tc[0].get('function',{}).get('arguments','')[:40] if tc else ''))" 2>/dev/null || echo SMOKE2_TIMEOUT_EMPTY)
    echo "smoke2: $SMOKE2"
    PILSNER_MODEL=$name \
    PILSNER_BASE_URL=http://127.0.0.1:8000/v1 \
    PILSNER_T2_DIR=$T2 \
    PILSNER_T2_TASKS=50 \
    PILSNER_T2_TRIALS=1 \
    PILSNER_T2_MAX_STEPS=50 \
    PILSNER_T2_MAX_STEPS_SECONDS=600 \
    PILSNER_SEED=$SEED \
    PILSNER_REASONING=off \
    PILSNER_ENGINE=llama.cpp \
    PILSNER_ENGINE_VERSION=$(cd /root/llama.cpp && git rev-parse --short HEAD 2>/dev/null || echo unknown) \
    PILSNER_MODEL_SHA256=$(sha256sum "$gguf" 2>/dev/null | cut -d' ' -f1) \
    PILSNER_GPU_CLOCK=$(nvidia-smi --query-gpu=clocks.gr --format=csv,noheader 2>/dev/null | head -1) \
    PILSNER_PARALLEL=$npar \
    PILSNER_CTX=$((ctx / npar)) \
    PILSNER_OUT=/root/receipts \
    python3 -m arena.run_tau2 || echo "BATTERY $name FAILED"
  fi
  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true
  sleep 3
}

# n_ctx_slot = ctx / parallel (no unified KV in this build). Every rung
# gets 16k per conversation slot; the Q8 floor (28.5GB) can only afford
# 16k total -> parallel 1.
SEED=2; run_battery bonsai-1bit    /root/models/bonsai-1bit/Bonsai-27B-Q1_0.gguf 32768 2
SEED=3; run_battery bonsai-ternary /root/models/bonsai-ternary/Ternary-Bonsai-27B-Q2_0.gguf 32768 2
SEED=4; run_battery qwen36-iq2xxs /root/models/qwen36-iq2xxs/Qwen3.6-27B-UD-IQ2_XXS.gguf 32768 2
SEED=6; run_battery qwen36-q2kxl   /root/models/qwen36-q2kxl/Qwen3.6-27B-UD-Q2_K_XL.gguf 32768 2
SEED=5; run_battery qwen3-4b       /root/models/qwen3-4b/Qwen3-4B-Q8_0.gguf 32768 2
SEED=1; run_battery qwen36-q8      /root/models/qwen36-q8/Qwen3.6-27B-Revised-q8_0.gguf 16384 1

echo "BATTERIES_DONE"
ls -la /root/receipts/
