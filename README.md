# Pilsner

Execution-verified agent eval for ultra-compressed 27B-class models on one
RTX 5090. A fixed-king arena: challengers serve their stack, the arena runs
the same external task battery against every entry on the same box, and the
label is a pure function of the measured result.

The repo is base-agnostic: it talks to any OpenAI-compatible endpoint
(vLLM / llama.cpp server / SGLang) and never touches weights. Any model —
or any new base release — plugs in with a config change, not a code change.

## The arena

- **The king.** The current champion entry (model + serving stack), served
  on the eval box. The bar is a live opponent, not a static list.
- **The challenge.** A submission is a head-to-head match against the king
  on the same box, same battery, same seed discipline. Sequential per-PR —
  one challenger at a time.
- **One number.** Success rate on the scored battery.
- **One rule.** Beat the king by more than 2% on the scored battery. Equal
  or worse is a loss.
- **One tie-break.** Time-to-task completion, measured same-box as wall
  clock over the battery. Both better and faster wins; quality gates first.
- **Ratchet.** The winner becomes the king, and the next challenger must
  beat them. The king is re-verified on a schedule against the full field.

## The gates

1. **Size gate** — runs on one RTX 5090 within 32GB (weights + KV cache),
   measured on the eval box.
2. **Quality floor** — scored battery success rate beats the king by >2%
   (ratchet). The scored instrument is external (τ2-bench, MIT, Sierra
   Research): execution-verified agent tasks where the final environment
   state decides success. No judge anywhere.
3. **Speed tier** — time-to-task completion above the quality floor.

## Why the score is trustworthy

- **External instrument, not ours.** The scored battery is τ2-bench — the
  respected agent eval authored outside this repo. We run it; we don't
  write it.
- **Execution-verified.** Tasks succeed only if the work is actually done
  in the simulated world (flight booked, refund issued, database state
  correct at the end). There is no LLM judge to charm.
- **Stateful = hard to memorize.** τ2 outcomes depend on the conversation
  and the evolving database state, not a static answer key.
- **Same-box measurement.** Quality and speed are measured on the same
  hardware for every entry. Reproducible from the receipt: model, endpoint,
  seed, task set, tau2 commit, wall clock.
- **Nothing hidden.** The battery is public and re-runnable. If real gaming
  ever appears, the freshness layer is added then — not pre-built.

## Dev tools

The repo also ships a synthetic function-calling harness (`eval/`) as the
miners' iteration loop. It generates invented tool catalogs, executes calls
against deterministic mock APIs, and scores result-equality. It is the dev
tool — fast, free, GPU-free — but it is **not** the scored instrument. The
arena gate is the τ2 battery above.

## Run

```bash
# 1. Serve any model (vLLM / llama.cpp / SGLang — any OpenAI-compatible endpoint)
./baselines/run_baseline.sh <hf_model_id> <served_name> [seed] [port]

# 2. Run the scored battery against the served model -> receipt
PILSNER_MODEL=<served_name> \
PILSNER_BASE_URL=http://localhost:8000/v1 \
PILSNER_T2_DIR=/path/to/tau2-bench \
python3 -m arena.run_tau2
```

Outputs: `outputs/report_tau2_seed<N>.json` — the receipt (score, timing,
provenance) and `outputs/report_seed<N>.json` + `outputs/receipts_seed<N>.jsonl`
from the FC dev harness (raw responses, auditable).

GPU-free verification of the plumbing (no model, no GPU):

```bash
./arena/e2e_mock.sh        # mock OpenAI server -> tau2 -> receipt
python3 -m unittest discover -s tests -v
```

## Reference ladder

The quality floor is anchored by a fixed reference set, all run through the
same τ2 battery on the same eval box:

- **Near-full-precision base of the same model family** — retention vs full precision. Served as FP8 (~27GB, vLLM) or Q8_0 GGUF (~28.5GB): 27B at FP16 is ~54GB and cannot fit one 32GB 5090
- **a small unquantized dense model (4B-class)** — the no-compression
  dollar competitor; a compressed 27B must be worth its memory
- **a conventional 2-bit quant of the 27B base** — 1-bit must beat 2-bit
  on agent tasks, not just itself

References are pinned (HF id + weights hash) before the first submission
round. First ladder pins (all served via llama.cpp, thinking off):

- near-full-precision: `Smoffyy/Qwen3.6-27B-Instruct-Revised-GGUF` q8_0
- 1-bit incumbent: `prism-ml/Bonsai-27B-gguf` Q1_0 (3.8GB)
- ternary incumbent: `prism-ml/Ternary-Bonsai-27B-gguf` Q2_0 (5.9GB)
- 2-bit quant: `unsloth/Qwen3.6-27B-GGUF` UD-IQ2_XXS (9.4GB)
- small dense: `unsloth/Qwen3-4B-GGUF` Q8_0 (4.3GB)

The scored battery runs 4 trials x 50 tasks (200 sims) — at 1 trial the
>2% rule is noise (CI ~+/-16%); at 200 sims the CI is ~+/-8%. The king
is verified at the scored battery size, never the survey size.

## Plugging in a new base

The harness has no knowledge of any specific base model. Serve the new base
and point `PILSNER_MODEL` at its served name:

```bash
./baselines/run_baseline.sh Qwen/Qwen3.8-27B qwen3.8-27b 1
PILSNER_MODEL=qwen3.8-27b python3 -m arena.run_tau2
```

## Layout

```
arena/             the scored instrument glue: serve -> tau2 -> time -> receipt
eval/              FC dev harness (iteration tool, not the gate)
baselines/         reference entrypoint script
tests/             unit tests (FC scoring + arena glue), GPU-free
outputs/           receipts and reports (gitignored)
```

## Status

Phase 1 (arena plumbing wired, mock-verified) — in progress. Phase 2
(5090 baseline of the base model) and Phase 3 (first independent scores of
incumbent low-bit builds) follow when the eval box is up. Governance
scaffold (REVIEW/EVAL-TRUST/.gittensor/CI) lands before submissions open.
