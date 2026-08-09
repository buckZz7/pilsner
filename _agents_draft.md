# AGENTS.md — Instructions for AI Contributors (draft for Pilsner)

If you are an AI agent reading this, follow it. If you are a human using
an AI tool, paste this into the tool's context before starting.

## What Pilsner is

A Gittensor (SN74) competition repo: a fixed-king arena where challengers
submit compressed 27B-class models (model.gguf + serving.json) that are
scored by an execution-verified agent battery (tau2-bench, external, MIT)
on one RTX 5090. The judge is the task environment, not an LLM and not a
human. Beat the king by >2% on the scored battery to become king.

Read first: REVIEW.md (the contract), EVAL-TRUST.md (the trust model),
CONTRIBUTING.md (how to submit).

## Repo layout

```
arena/             scored-instrument glue: run_tau2, challenge, board, ladder_report
eval/              FC dev harness (iteration tool, not the gate)
baselines/         reference serving script
kings/             published king artifacts (maintainer-owned)
submissions/       entry PRs (miners)
tests/             unit tests (GPU-free)
outputs/           receipts + leaderboard (gitignored)
```

## Rules for AI agents

- Do not touch maintainer-owned paths unless the task explicitly asks and
  you are operating as the maintainer: `arena/`, `eval/`, `.gittensor/`,
  `.github/`, `kings/`, `REVIEW.md`, `EVAL-TRUST.md`, `RULESET.md`.
- No AI-attribution trailers in commits or PR bodies. CI rejects them.
- Reference an issue (`Fixes #N` / `Refs #N`). Max 2 open PRs.
- Ship tests with harness changes (`arena/`, `eval/` changes need a test).
- No emojis. UTC timestamps, ISO-8601 with Z suffix.
- Do not fake results: never fabricate receipts, scores, or test outcomes.
- The scored battery and operating point (reasoning=off) are fixed. Do not
  propose changing them in a PR; that is a maintainer decision.

## Local checks

```bash
python3 -m unittest discover -s tests -v
python3 -m arena.board outputs
```
