#!/usr/bin/env bash
# MTP / thinking-on probe: can we run Qwen3.6-family with thinking enabled?
#
# The scored arena runs --reasoning off (uniform operating point). The
# thinking-ON companion battery (Bonsai's methodology) needs to know:
# does thinking terminate, or does the runaway (never-closed <think>)
# reproduce at our serving stack? MTP spec-decoding is OFF by default in
# this llama.cpp build, so the root cause from issue #20837 is not active
# here — the probe measures reality.
#
# Usage (on the eval box): bash probe_mtp.sh <gguf> <run_name>
#   K=6 prompts; reports finish reason, reasoning tokens, content chars,
#   wall time per prompt. Runaway = timeout/context-exceeded/empty content.
set -euo pipefail
SERV=/root/llama.cpp/build/bin/llama-server
GGUF=${1:?gguf path}
NAME=${2:?run name}
PORT=8000
K=${K:-6}

probe() {
  local label=$1; shift
  echo "=== probe: $label ==="
  "$SERV" --host 0.0.0.0 --port $PORT -m "$GGUF" -c 16384 --parallel 1 "$@" --no-webui > /root/probe_${NAME}_${label// /_}.log 2>&1 &
  local pid=$!
  local ok=""
  for i in $(seq 1 90); do
    if curl -s http://127.0.0.1:$PORT/v1/models >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  if [ -z "$ok" ]; then echo "server failed to start"; return 1; fi
  python3 - "$K" "$PORT" <<'PYEOF'
import json, sys, time, urllib.request
k = int(sys.argv[1]); port = int(sys.argv[2])
prompts = [
    "A farmer has 17 sheep, 9 goats and 5 chickens. A wolf eats 3 sheep and 2 goats. How many legs do the remaining animals have in total?",
    "If it takes 5 machines 5 minutes to make 5 widgets, how long would it take 100 machines to make 100 widgets?",
    "Three switches control three bulbs in another room. You may enter the room once. How do you determine which switch controls which bulb?",
    "I have a 3L jug and a 5L jug. Exactly how do I measure 4 liters?",
    "What is the 47th digit of the decimal expansion of 1/7? Explain.",
]
runaways = 0
for i in range(k):
    p = prompts[i % len(prompts)]
    body = json.dumps({"model": "x", "messages": [{"role": "user", "content": p}],
                       "max_tokens": 1024}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            d = json.loads(r.read())
        m = d["choices"][0]["message"]
        fr = d["choices"][0].get("finish_reason")
        rt = len(m.get("reasoning_content") or "")
        ct = len(m.get("content") or "")
        dt = time.time() - t0
        bad = "RUNAWAY" if (ct == 0 and rt > 0) or fr == "length" and ct == 0 else ""
        if bad: runaways += 1
        print(f"  prompt {i+1}: finish={fr} reasoning_tok={rt} content_chars={ct} "
              f"wall={dt:.0f}s {bad}")
    except Exception as e:
        runaways += 1
        print(f"  prompt {i+1}: ERROR {type(e).__name__}: {str(e)[:70]} "
              f"wall={time.time()-t0:.0f}s RUNAWAY")
print(f"  => runaways: {runaways}/{k}")
PYEOF
  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true
  sleep 3
}

probe "reasoning-off" --reasoning off
probe "reasoning-on" --reasoning on
probe "reasoning-auto" --reasoning auto
echo "PROBE_DONE"
