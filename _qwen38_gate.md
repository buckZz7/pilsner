# Qwen3.8-27B gate runbook (2026-08-08)

Trigger: the `qwen38-watch` cron alerts (HF repo `Qwen/Qwen3.8-27B` live).
Goal: decide whether Pilsner re-bases from Qwen3.6-27B to Qwen3.8-27B,
using the same battery and operating point as the 3.6 ladder.

## Step 0 — License (the hard gate, before ANY download)

1. Open the HF model card: license field must be Apache-2.0 (Qwen3.6
   precedent; QwenLM GitHub states all open-weight releases are Apache 2.0).
2. Read the LICENSE file in the repo (never trust the card alone).
3. If NOT permissive (custom/non-commercial): stay on 3.6, close the gate.
   Log the decision. Do not proceed.

## Step 1 — Download + quantize (on the eval box)

```bash
# weights in HF safetensors -> convert or grab a community Q8_0 GGUF
hf download Qwen/Qwen3.8-27B --local-dir /root/models/qwen38-fp16
# prefer an official/trusted Q8_0 GGUF (Smoffyy/unsloth pattern); else
# convert: python llama.cpp/convert_hf_to_gguf.py + llama-quantize Q8_0
hf download <vendor>/Qwen3.8-27B-*-GGUF <...>-Q8_0.gguf --local-dir /root/models/qwen38-q8
```

## Step 2 — Battery (identical to the 3.6 ladder receipt)

```bash
# serve: same engine, same flags as the ladder
llama-server --host 0.0.0.0 --port 8000 -m /root/models/qwen38-q8/*.gguf \
  -c 16384 --parallel 2 --cache-type-k q8_0 --cache-type-v q8_0 \
  --reasoning off --no-webui

# run: same battery as ladder battery 1 (seed slot 6 to avoid collision)
PILSNER_MODEL=qwen38-q8 PILSNER_BASE_URL=http://127.0.0.1:8000/v1 \
PILSNER_T2_DIR=/root/tau2-bench PILSNER_T2_TASKS=50 PILSNER_T2_TRIALS=1 \
PILSNER_SEED=6 PILSNER_REASONING=off PILSNER_ENGINE=llama.cpp \
PILSNER_OUT=/root/receipts python3 -m arena.run_tau2
```

Survey = 1 trial (comparable to the ladder's qwen36-q8 row). If the survey
is close (<3 points), the base decision gets the full scored battery
(4 trials x 50) before any re-basing commit.

## Step 3 — Compare (the challenge tool does the math)

```bash
python3 -m arena.challenge outputs/report_tau2_seed1.json outputs/report_tau2_seed6.json
# seed1 = qwen36-q8 survey, seed6 = qwen38-q8 survey
```

- WIN by >2%: 3.8 becomes the base candidate -> run the 4-trial scored
  battery to confirm -> re-base (README pins, reference ladder, king
  entry if the arena is live).
- LOSS / within noise: stay 3.6. Log the receipt pair.

## Step 4 — Record

- Both receipts committed to outputs/ (or the board).
- Gate outcome appended to the skill reference (pilsner-fc-eval.md) with
  the license verdict and the score delta.

Notes: the FC harness (eval/) is the quick sanity check first (cheap,
minutes) — run it before burning the 5090 battery: `PILSNER_MODEL=qwen38-q8
python3 -m eval.runner`. If FC retention vs 3.6 looks catastrophic, skip
the battery.
