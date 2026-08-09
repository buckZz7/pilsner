# Pilsner submission contract (draft for review)

The fixed-king arena needs one thing defined before REVIEW.md can exist:
what a challenge PR actually contains, and how it gets served and scored.

## The core decision (settled by the trust model)

The arena must score every entry on the SAME box. That rules out:

- **Remote endpoints** (miner runs their own box) — breaks same-box
  measurement; a fast remote box could win on hardware, not quality.
- **Arbitrary containers** (miner submits a docker image) — untrusted code
  on the eval box; a security nightmare and a gaming surface.

So the submission is **artifacts, not services**: model files + a serving
recipe, evaluated on the arena's box by the arena's runner. The receipt
records the served configuration (engine, quant, reasoning, flags), so the
served config IS part of the submission — you can't claim a config you
didn't ship.

## What a challenge PR contains

```
submissions/<github_handle>/<entry>/          # one entry = one challenge
  model.gguf                                  # the weights (or a pin:
  serving.json                                #   { "hf_id": ..., "sha256": ... })
                                              # engine, quant, context, flags,
                                              # reasoning on|off|auto
  notes.md                                    # optional, non-scored
```

Minimal and honest: the arena does NOT require training scripts, method
descriptions, or provenance beyond the model hash (only require what you
verify — unverified fields create gaming surfaces). Secret sauce stays
secret; the eval verifies the result, not the story.

## The flow

1. PR opens -> CI integrity checks (lint, linked issue, no AI trailers,
   sensitive-paths guard, max 2 open PRs). Same gates as the skill's
   pr-integrity.yml.
2. Merge to a staging area -> the eval box picks it up, serves it per
   serving.json, runs the scored battery (airline+retail, 2 trials x 50
   tasks each = 200 sims), measures wall clock.
3. arena.challenge decides: WIN (beat king by >2% on the same battery,
   same operating point) or LOSS. WIN -> the entry becomes the king and
   the receipt + leaderboard update.
4. King re-verified on a schedule against the full field.

## Serving-layer allowlist (the miner's game, inside the engine)

The ENGINE is pinned (llama.cpp — the trust anchor: one box, one engine,
receipts reproducible). Everything inside it is the miner's declared
game — serving.json must declare it, the receipt records what actually
ran, and the battery key includes the serving config. Allowed (v1):

- **Grammar / schema-constrained decoding** (GBNF or JSON-schema). The
  known fix for precision loss: guarantees well-formed tool calls. It
  fixes FORMAT, not semantics — the task still fails on wrong args or
  wrong policy, so the score still measures the agent.
- **KV cache quant choice** (e.g., q4 KV — Bonsai's "near-lossless"
  claim is a serving decision, declared and measured).
- **LoRA adapters** — the artifact may be base GGUF + adapter
  (llama.cpp serves them); a real fine-tune lane.
- **Speculative decoding with a declared draft model** (the drafter is
  part of the artifact; outputs must be identical to non-spec by
  construction, so it only speeds up).
- **Memory adapters** (added 2026-08-09) — a thin local OpenAI-compatible
  proxy between the runner and the served model that RE-PRESENTS
  information already available in the conversation (e.g. an entity ID
  returned by a tool response). Same class as grammar decoding: a
  serving-layer intervention, disclosed in serving.json, recorded in the
  receipt, part of the battery key. Bounds (referee-enforced):
  1. **Re-presentation only.** May re-surface state already in the
     conversation; may NOT compute answers, call tools on the agent's
     behalf, inject knowledge not derivable from the conversation, or
     rewrite agent messages.
  2. **Reproducible.** The adapter source ships with the entry; the
     receipt records its sha256. A different adapter = a different
     battery (challenge.py refuses).
  3. **User sim bypass.** The fixed user sim NEVER traverses the
     challenger's adapter — receipt records the user endpoint; a
     challenge whose user sim was adapter-mediated is refused.
  4. **Same-box, no network.** Local process on the eval box only.
  Status: the entity-inject adapter (`arena/adapter_entity_inject.py`)
  is this class's first challenger — it measures whether re-surfacing
  the derived ID lifts the 1-bit off 0.16. Either answer is measured;
  if it works, the king gets stronger and the next challenger must beat
  the stronger king (the ratchet).

NOT allowed: engine swaps (vLLM, custom forks), remote endpoints,
containers. Anything else the pinned engine supports can be added to the
allowlist by a maintainer decision with an EVAL-TRUST note.

**Engine-loadability is part of validation (2026-08-09):** a submission
must LOAD on the pinned engine as-is. Vendor artifacts can be
fork-locked — PrismML's own ternary Q2_0 GGUF uses a tensor layout their
custom llama.cpp fork defines; mainline (even latest) reads type 42
(Q2_0) with a different layout and refuses the file ("failed to read
tensor data"). The arena measures what its pinned engine can serve —
disclosed, same boundary for everyone — and the size gate checks load
before scoring (a file that won't load fails validation, no score).

## Gaming mitigations (adversarial review 2026-08-08)

The arena is transparent by design — "study and improve" against public
receipts is the intended dynamic. The lines that hold:

1. **Memorizing the public task set** (policy-pattern fine-tuning) is the
   biggest realistic vector. Defense-in-depth: tau2 statefulness (DB
   states randomize — trajectories can't be memorized), multi-domain
   breadth (airline+retail), and RANDOM TASK SAMPLING — the scored
   battery samples N tasks from the domain's full set (retail: 50 of
   114) with the sampling seed recorded in the receipt. Still public and
   reproducible; memorizing the whole pool costs ~2.3x.
2. **Exploiting the fixed user sim** — it's public with learnable quirks.
   The fixed user is part of the battery identity; rotate it (or add a
   second) when exploitation is suspected. Reactive by design.
3. **Specializing against the incumbent's public failures** — legitimate
   (that's the ratchet); the multi-domain battery keeps it from becoming
   single-domain chaser dynamics.
4. **Griefing the eval box / luck-farming the >2% rule** — operational,
   fixed with economics: a per-handle eval budget (or stake) so the
   arena never pays for spam evals, and challenges cost the challenger
   something. Max 2 open PRs bounds luck-farming.
5. **Breaking the measurement** (fake configs, hidden flags, claimed
   configs not served) — blocked by the receipt chain: the receipt
   records what actually ran, and anyone can re-run.

## Open questions for the maintainer

RESOLVED 2026-08-08 (maintainer decision, Buck delegated):

1. **Operating point policy: reasoning-off ONLY.** One number, one rule,
   one operating point. Entries cannot declare reasoning on/auto —
   thinking-on measurements are research (the companion battery), not
   competition tracks. The receipt records reasoning=off; a submission
   that requires thinking to score well is a submission that doesn't
   meet the arena's bar.
2. **Size gate: yes, hard pass/fail.** Measured on the eval box (VRAM +
   KV at scored context) before scoring. Fails fast, no score.
3. **Format: GGUF via the pinned engine (llama.cpp).** Default and only
   format for v1. Other engines/formats require the engine pin to allow
   them (receipt records the engine); not before v1 ships.
