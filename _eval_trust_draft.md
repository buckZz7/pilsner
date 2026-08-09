# EVAL-TRUST (draft for Pilsner, 2026-08-08)

How the arena's numbers are trustworthy, stated plainly — and where they
are NOT yet trustless. No overclaiming; the honest boundary is part of the
design (sparkinfer's pattern).

## What is deterministic

- The scored instrument is tau2-bench (MIT, Sierra Research) — an external
  agent environment where task success is decided by the final environment
  state (database assertions, executed tool effects), not by a judge model
  and not by us. We run it; we did not write it.
- The scorer is mechanical: reward 1.0 iff the task's assertions hold.

## What is reproducible

Everything needed to re-run a scored entry is in the receipt
(`outputs/report_tau2_seed<N>.json`):

- served model (name + GGUF source), engine pin, quant, context, flags
- operating point (reasoning: off — the only allowed operating point)
- battery identity: domain, task split, num_tasks, num_trials
- tau2 git commit, results.json path + sha256, seed slot, timestamp
- wall-clock over the battery (the speed tie-break), same box, same config

Anyone can serve the same artifact, run the same battery on the same
hardware, and compare their receipt to the published one.

## Why the score is hard to game

- External, stateful instrument: tau2 outcomes depend on conversation
  history and evolving environment state, not a static answer key.
- Same-box, same-config measurement: quality and speed are measured on
  the eval box with the arena's pinned engine; the receipt records what
  was actually run (the served config IS the submission).
- One operating point: thinking is off for every entry, so nobody hides
  behind thinking time or thinking quality.
- Statistical teeth: 200 sims (2 trials x 50 tasks x 2 domains:
  airline + retail) make the >2% rule meaningful (CI ~+/-8%); every
  score publishes its Wilson 95% CI. Task caps (50 steps / 600s per
  attempt) bound pathological grind; the caps are part of the battery
  identity, recorded in the receipt.
- Artifacts, not services: no remote endpoints, no arbitrary containers.

## The honest boundary (what is NOT yet trustless)

- Single eval box, operator-trusted hardware. No TEE/attestation yet —
  the box operator could in principle fabricate receipts. The mitigation
  is the public receipt chain + anyone-can-re-run, not hardware proof.
- LLM sampling is stochastic: per-task outcomes vary across trials. The
  multi-trial battery + CI is the answer; single-run numbers are not
  claims.
- The >2% rule is calibrated for 200 sims; at smaller N it is noise and
  the arena refuses to decide (challenge tool returns refuse on battery
  mismatch or tiny N).
- tau2's task set is public. Its statefulness is the anti-memorization
  defense; if empirical evidence of contamination ever appears, the
  freshness layer (new domain authored by us on the tau2 framework) is
  added then — not pre-built.

## Red-team exercise (2026-08-09) — what holds, what cannot

Simulated attacks against the LIVE tooling (tests/test_redteam.py), all
repelled: forged score inflation (audit checks success_rate vs per_task
consistency), inconsistent receipts, results_sha256 mismatch vs raw
(verified when the raw is present), weaker-user-sim battery mismatch,
context shrink, engine-build swap (all refused by the challenge
referee), stripped provenance. Audit is now the arena's tripwire: it
runs before every board and refuses to present an internally
inconsistent or incomparable result.

KNOWN BOUNDARIES (not code-catchable, documented honestly):
- Operator trust: receipts are self-issued, no attestation (TDX on
  roadmap). An operator who wanted to fabricate could; the defense is
  the public chain + anyone-can-re-run, not hardware.
- Sockpuppet eligibility: min_valid_merged_prs=1 is gameable with fake
  accounts; governance/identity, not code.
- User-sim forgery: a FORGED receipt claiming the fixed user but using
  a weaker one is undetectable without attestation.
- Memorization: bounded (statefulness, multi-domain, sampling), not
  solved; freshness layer is reactive.

Design principle: every attack must be expensive, visible, reversible
— gaming should cost more than winning legitimately, and every game
should be visible so trust can be restored.

## Roadmap (in order, when evidence demands)

1. Sealed receipts (Ed25519 signatures over the receipt JSON).
2. Attested eval box (TDX + GPU CC, the SparkProof pattern).
3. Multi-box spot re-runs with mismatch contestation.
