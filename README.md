# Pilsner

Execution-verified agent eval for ultra-compressed 27B-class models on one
RTX 5090. A fixed-king arena: challengers serve their stack, the arena runs
the same task battery against every entry on the same box, and the label is
a pure function of the measured result.

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
   (ratchet). The scored instrument is BenchBrew: execution-verified agent
   tasks where the final environment state decides success. No judge
   anywhere — the oracle is spec-derived DB-state predicates.
3. **Speed tier** — time-to-task completion above the quality floor.

## The instrument: BenchBrew, not a static battery

The scored battery is **regenerated per evaluation** from a public seed:
`(spec, seed)` → a fresh task bundle, emitted into τ² and run through its
orchestrator. Nothing is static, nothing is hidden:

- **Fresh-lane protocol.** Every battery re-emits the domain bundle from a
  fresh public seed (chain-rule seeds derive from the previous verified
  receipt). Memorizing one bundle buys nothing for the next.
- **Independence, proven.** Pilsner (this repo) consumes evals it never
  wrote: BenchBrew is the factory, τ²-bench is the runtime, Pilsner is the
  scorekeeper. Three separate repos.
- **Collusion guard.** The user simulator is a FIXED model, never the model
  being evaluated — the eval can't frame its own test.

## Why the score is trustworthy

- **Verified receipts.** A receipt is admitted to the board only if
  replaying the recorded trajectory through the CURRENT domain code
  re-derives the claimed score. The receipt carries provenance: spec
  version + sha, seed, bundle sha, results hash. Forged, stale, or
  evidence-less receipts are refused — every refusal so far has been a
  true refusal (seven real bugs caught by verification, all fixed).
- **Execution-verified.** Tasks succeed only if the work is actually done
  in the simulated world (booking canceled within the window, escrow
  released only after payment, Reg E report filed in time, itinerary
  within budget). There is no LLM judge to charm.
- **Stateful = hard to memorize.** Outcomes depend on the conversation and
  the evolving world state, not a static answer key — and the fresh-lane
  protocol replaces the questions each time anyway.
- **Same-box measurement.** Quality and speed are measured on the same
  hardware for every entry. Reproducible from the receipt: model, endpoint,
  seed, task set, τ² commit, wall clock.
- **Honest operating point.** Scores are measured at the τ² operating
  point — the agent must discover the world (inbox, listings, options)
  rather than being handed it. The standalone calibration numbers in
  BenchBrew remain the lane-design gate; the board crowns at the honest
  measurement.

## The board

Verified-only, per-(model, domain) pooled Wilson CI. Rebuild with
`uv run python -m arena.board outputs --write`. Current kings
(`outputs/leaderboard.json`, receipts in `outputs/report_tau2_seed*.json`):

| Lane | King | Score | CI | Receipt |
|---|---|---|---|---|
| local_services | qwen36-iq2xxs | 0.375 (15/40) | [0.242-0.530] | seed 61, verified |
| personal_finance | qwen36-iq2xxs | 0.375 (15/40) | [0.242-0.530] | seed 62, verified |
| marketplace | qwen36-iq2xxs | 0.250 (2/8) | [0.071-0.591] | seed 45, verified (thin — refresh queued) |
| travel | — | — | — | battery running |

## History: the 1-bit collapse (airline era)

Reference ladder on the eval box (50-task airline battery, receipts + raw
results public in `outputs/`):

| Rung | Score (50 tasks) | 95% CI | vs Q8 floor |
|---|---|---|---|
| Qwen3.6-27B Q2_K_XL (2-bit) | 0.62 (31) | [0.48, 0.74] | **100%** — 2-bit is free on agent work |
| Qwen3.6-27B Q8_0 (floor) | 0.62 (31) | [0.48, 0.74] | reference |
| Qwen3.6-27B IQ2_XXS (2-bit) | 0.54 (27) | [0.40, 0.67] | 87% |
| Qwen3-4B Q8_0 | 0.18 (9) | [0.10, 0.31] | 29% |
| Bonsai-27B Q1_0 (1-bit) | 0.16 (8) | [0.08, 0.29] | 26% |

Two conclusions, both independently measured and fully re-runnable:

1. **The 2-bit class retains the full-precision agent.** Q2_K_XL ties the
   Q8 floor exactly (31/50 each).
2. **The flagship 1-bit collapses on agent work.** Bonsai-27B at 1-bit
   scores 0.16 at our operating point — not the ~74% retention implied by
   their whitepaper table. The mechanism is not a JSON problem and not
   context drift: 93 of the 1-bit's 95 tool errors are `User <id> not
   found` — the agent must derive an entity id once and reuse it, and the
   1-bit regenerates a guessed variation from the first reuse onward.
   Grammar/schema-constrained decoding cannot fix it (the calls are
   well-formed; the values are wrong). The failure is entity derivation
   through ultra-low-precision weights.

The BenchBrew lanes now measure the same capability axes at the honest
operating point, with freshness and verification layered on top.

## Run

```bash
# a full battery: fresh seed -> emit -> tau2 run -> verify -> receipt
export OPENAI_API_KEY=<endpoint key>
PILSNER_T2_DOMAIN=local_services \
PILSNER_BENCHBREW_SEED=61 \
PILSNER_BENCHBREW_DIR=/opt/data/benchbrew \
PILSNER_MODEL=qwen36-iq2xxs \
PILSNER_BASE_URL=http://<agent-host>:41176/v1 \
PILSNER_USER_MODEL=qwen3-4b \
PILSNER_USER_BASE_URL=http://<user-sim-tunnel>:14177/v1 \
PILSNER_T2_TASKS=40 \
uv run python arena/run_tau2.py

# rebuild the board from verified receipts
uv run python -m arena.board outputs --write
```

Env contract: `PILSNER_T2_DOMAIN` (lane), `PILSNER_BENCHBREW_SEED` (public
seed; also names the receipt slot when `PILSNER_SEED` is unset),
`PILSNER_MODEL` / `PILSNER_BASE_URL` (the evaluated model),
`PILSNER_USER_MODEL` / `PILSNER_USER_BASE_URL` (fixed user sim — must
differ from the agent), `PILSNER_T2_TASKS` (battery size),
`PILSNER_T2_MAX_STEPS` (agent step cap).
