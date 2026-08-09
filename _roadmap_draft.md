# ROADMAP (draft for Pilsner)

Honest done conditions — a phase is done when its condition is met, not
when it feels finished.

## Phase 1 — Arena plumbing (DONE 2026-08-08)

- tau2-bench wired as the scored instrument: serve -> run -> time ->
  receipt (`arena/run_tau2.py`), verified end-to-end against a mock
  OpenAI server, GPU-free.
- Receipt carries provenance: model, engine pin, operating point
  (reasoning=off), battery identity, tau2 commit, results sha256,
  wall clock, Wilson CI.
- Tooling: challenge referee (>2% rule), ladder report, board.

## Phase 2 — Reference floor (IN PROGRESS)

- Ladder survey on the 5090: Q8 floor, Bonsai 1-bit, Bonsai ternary,
  IQ2_XXS, 4B dense. Done when all five receipts are on the board.
- Base gate: Qwen3.8-27B (if released) compared on the same battery;
  license verified first.

## Phase 3 — First independent score (NEXT)

- Thinking-on companion battery for Bonsai 1-bit + Q8 (their methodology:
  thinking mode, matched config) -> the first independent, execution-
  verified reproduction of their tau2 claims.
- MTP test (`--reasoning on --mtp off`): if the runaway is fixed, the
  companion battery is cheap and reliable.

## Phase 4 — Go live (DRAFTED)

- Commit the governance stack (REVIEW, EVAL-TRUST, CONTRIBUTING, AGENTS,
  CODEOWNERS, pr-integrity CI, .gittensor/config.json) in one commit.
- King verified at the scored battery size (4 trials x 50), not the
  survey size. Submissions open.

## Phase 5 — Ratchet and refresh

- Sealed receipts (Ed25519), attested eval box (SparkProof pattern),
  multi-box spot re-runs. Freshness layer (new tau2 domain) only if
  evidence of contamination appears.
