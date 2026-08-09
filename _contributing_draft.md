# CONTRIBUTING (draft for Pilsner)

## What this repo is

A fixed-king arena. Miners submit entries (model + serving config); the
eval box serves each entry and runs the scored battery; the label is a
pure function of the measured result. See REVIEW.md for the gates and
EVAL-TRUST.md for how the numbers are trustworthy.

## Branch model

- `main` is the live competition state. Direct pushes only by maintainers.
- Work in branches; open a PR referencing an issue (`Fixes #N` / `Refs #N`).
- Max 2 open PRs per contributor.

## What belongs where

- `submissions/<handle>/<entry>/` — entry PRs: `model.gguf` (or pinned
  HF id + sha256) + `serving.json` (engine, quant, context, flags,
  reasoning=off) + optional `notes.md` (never scored).
- `arena/` and `eval/` — maintainer-owned harness. Changes ship a test
  under `tests/`.
- `kings/` — published king artifacts. Maintainer-owned.
- `outputs/` — receipts and reports (gitignored, never committed).

## Local checks before opening a PR

```bash
python3 -m unittest discover -s tests -v
python3 -m arena.ladder_report outputs   # if receipts exist
```

CI runs the same checks plus the gates in REVIEW.md. A single red check
closes the PR.

## Out of scope

- Changing the scored battery, operating point, or the >2% rule without a
  maintainer decision and an updated EVAL-TRUST section.
- Remote endpoints or containers as submissions (breaks same-box).
- Judge models, hidden sets, or sealed subsets (rejected design).
