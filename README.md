# Pilsner

Execution-verified tool-calling eval for 27B-class models on one RTX 5090.
The harness is base-agnostic: it talks to any OpenAI-compatible endpoint
and never touches weights, so any model (or any new base release) can be
plugged in with a config change — no code changes.

## The three gates (the spec)

1. **Size gate** — must run on one RTX 5090 within 32GB (weights + KV cache), measured on the rented eval box.
2. **Quality floor** — execution-verified FC accuracy must beat the reference model AND the current frontier by >2% (ratchet). Includes a no-call / hallucination guard and a generalization slice (the model must not be brain-damaged outside tool calling).
3. **Speed tier** — tok/s at the scored context, above the quality floor.

## Reference ladder

The quality floor is measured against a fixed reference set, all run through the same harness on the same eval box:

- **FP16 base of the same model family** — retention vs full precision
- **a small unquantized dense model (4B-class)** — the no-compression dollar competitor; 1-bit 27B must be worth its memory
- **a conventional 2-bit quant of the 27B base** — 1-bit must beat 2-bit on agent tasks, not just itself

The harness is base-agnostic: every reference is just another served model. References are pinned (HF id + weights hash) before the first submission round.

## Why the eval is ungameable

- **Synthetic, seeded, rotating:** eval items are *generated* from invented tool catalogs with deterministic expected results. Seeds rotate per round, so there is nothing to memorize — ever.
- **Execution-verified:** a call scores only if it actually *runs against a real function and returns the expected result*. No "looks right" credit. No judge anywhere.
- **Result-equality, not text-equality:** the model's call is executed and its output compared to the expected output.
- **Hallucination guard:** queries that no tool can answer must produce *no call*. Wrong-tool and invented-parameter calls are scored as failures.
- **Generalization guardrail:** a mechanical arithmetic slice the model must clear, so submissions can't be tool-calling-only zombies.

## Run

```bash
# 1. Serve any model (vLLM / llama.cpp / SGLang — any OpenAI-compatible endpoint)
./baselines/run_baseline.sh <hf_model_id> <served_name> [seed] [port]

# 2. Or point the harness at an already-running server
PILSNER_MODEL=<served_name> \
PILSNER_BASE_URL=http://localhost:8000/v1 \
PILSNER_SEED=1 \
python -m eval.runner
```

Outputs: `outputs/report_seed<N>.json` (scores) and `outputs/receipts_seed<N>.jsonl` (raw responses, auditable).

## Plugging in a new base

The harness has no knowledge of any specific base model. Serve the new
base and point `PILSNER_MODEL` at its served name:

```bash
./baselines/run_baseline.sh Qwen/Qwen3.8-27B qwen3.8-27b 1
```

No code changes. The eval set is generated independently of the model, so
scores from different bases are directly comparable.

## Layout

```
eval/          the harness (spec in code)
  generator.py   synthetic FC eval generator (invented tool catalogs)
  tools.py       deterministic mock APIs for execution verification
  gen_slice.py   generalization slice (arithmetic word problems, computed answers)
  runner.py      OpenAI-compatible client: runs a model, scores, writes receipts
baselines/     run scripts for stock models
tests/         scorer verification (no GPU needed)
```

## Verify (no GPU, no server)

```bash
python -m unittest discover -s tests -v
```
