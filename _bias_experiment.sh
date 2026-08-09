#!/usr/bin/env bash
# Bias quantification: IQ2_XXS agent x 3 user simulators.
#
# The user-sim confound: same-model-both means a weak model plays a
# pushover customer, inflating its own agent score. This measures the
# size of the effect: same agent, three customers.
#   Leg A: IQ2 agent + IQ2 user   (ladder pattern = the confounded baseline)
#   Leg B: IQ2 agent + 1-bit user (weak customer — how much inflation?)
#   Leg C: IQ2 agent + 4B user    (the fixed-user candidate)
# Spread A->B = confound size; A->C = what the fixed user costs/changes.
# The Q8 leg of the confound is already covered by the ladder's Q8 floor
# receipt (Q8 agent + Q8 user, seed 1).
#
# Usage (on the eval box, AFTER the ladder finishes): bash bias_experiment.sh
set -euo pipefail
SERV=/root/llama.cpp/build/bin/llama-server
T2=/root/tau2-bench
cd /root/pilsner
mkdir -p /root/receipts

AGENT_IQ2=/root/models/qwen36-iq2xxs/Qwen3.6-27B-UD-IQ2_XXS.gguf
USER_1BIT=/root/models/bonsai-1bit/Bonsai-27B-Q1_0.gguf
USER_4B=/root/models/qwen3-4b-user/Qwen3-4B-Q4_K_M.gguf

run_leg() {
  local label=$1 user_gguf=$2 user_model=$3 seed=$4
  if [ -f "/root/receipts/report_tau2_seed$seed.json" ]; then
    echo "=== LEG $label SKIPPED (receipt exists) ==="; return 0
  fi
  echo "=== LEG $label (agent=iq2xxs user=$user_model) ==="
  "$SERV" --host 0.0.0.0 --port 8000 -m "$AGENT_IQ2" -c 32768 --parallel 2 \
    --cache-type-k q8_0 --cache-type-v q8_0 --reasoning off --no-webui \
    > /root/bias_${label}_agent.log 2>&1 &
  local apid=$!
  "$SERV" --host 0.0.0.0 --port 8001 -m "$user_gguf" -c 16384 --parallel 1 \
    --cache-type-k q8_0 --cache-type-v q8_0 --reasoning off --no-webui \
    > /root/bias_${label}_user.log 2>&1 &
  local upid=$!
  local ok=""
  for i in $(seq 1 90); do
    if curl -s http://127.0.0.1:8000/v1/models >/dev/null 2>&1 && \
       curl -s http://127.0.0.1:8001/v1/models >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  if [ -z "$ok" ]; then echo "LEG $label server failed"; kill $apid $upid 2>/dev/null || true; return 1; fi
  PILSNER_MODEL=qwen36-iq2xxs \
  PILSNER_BASE_URL=http://127.0.0.1:8000/v1 \
  PILSNER_USER_MODEL=$user_model \
  PILSNER_USER_BASE_URL=http://127.0.0.1:8001/v1 \
  PILSNER_T2_DIR=$T2 \
  PILSNER_T2_TASKS=50 \
  PILSNER_T2_TRIALS=1 \
  PILSNER_SEED=$seed \
  PILSNER_REASONING=off \
  PILSNER_ENGINE=llama.cpp \
  PILSNER_ENGINE_VERSION=$("$SERV" --version 2>/dev/null | grep -aoE "[0-9a-f]{7,}" | head -1 || echo unknown) \
  PILSNER_PARALLEL=2 \
  PILSNER_CTX=16384 \
  PILSNER_OUT=/root/receipts \
  python3 -m arena.run_tau2 || echo "LEG $label FAILED"
  kill $apid $upid 2>/dev/null || true
  wait $apid $upid 2>/dev/null || true
  sleep 3
}

# same-model-both (IQ2 user) is the ladder pattern; receipt seeds 21-23
run_leg a_iq2user    "$AGENT_IQ2" qwen36-iq2xxs 21
run_leg b_1bituser   "$USER_1BIT" bonsai-1bit   22
run_leg c_4buser     "$USER_4B"   qwen3-4b-q4km 23
echo "BIAS_DONE"
echo "confound size = legA - legB; fixed-user effect = legA - legC"
