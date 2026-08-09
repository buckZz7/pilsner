# REVIEW (draft for Pilsner, 2026-08-08)

The contribution contract. Three gates; a single red check closes the PR.
No human override skips a red gate. The label is a pure function of the
measured eval result, not a read of the diff.

## Gate 1 — Automated (CI, no human)

- ruff lint, pytest (harness + referee + report tests)
- linked issue in PR body (`Fixes #N` / `Refs #N`)
- no AI-attribution trailers (reject `Co-authored-by:` naming AI tools)
- max 2 open PRs per contributor
- sensitive-paths guard: non-maintainers cannot touch
  `arena/`, `eval/`, `.gittensor/`, `.github/`, `kings/`, `REVIEW.md`,
  `EVAL-TRUST.md`, `RULESET.md`
- submission validation: `serving.json` parses, model file present with
  pinned sha256, declared engine is the pinned engine, reasoning=off

## Gate 2 — Scope (maintainer)

- Entry PRs: `submissions/<handle>/<entry>/` — weights + serving.json.
  The eval verifies the result, not the story; no training scripts,
  no method descriptions required.
- Harness PRs: `arena/` and `eval/` are maintainer-owned; changes ship a
  test under `tests/`.

## Gate 3 — Deterministic label (function of the eval result)

The eval box serves the submitted artifact per its serving.json, runs the
scored battery (200 sims: 4 trials x 50 tasks, airline base split,
reasoning off, pinned engine), and emits the receipt. arena.challenge
applies the rule. The label:

| Label                | Mult  | Assigned when                                  |
|----------------------|-------|------------------------------------------------|
| `pilsner:winner`     | x4.0  | beats current king by >2% on the scored battery|
| `pilsner:loss`       | x0.0  | fails to beat the king by >2%                  |
| `pilsner:invalid`    | x0.0  | fails size gate / validation / refused matchup |
| `pilsner:tooling`    | x0.05 | harness/eval/docs/tests PR (deliberately low)   |

Unlabeled PRs score zero (`default_label_multiplier: 0.0`).

## Anti-cheating pass (closes the PR regardless of outcome)

- serving.json must describe what the box actually runs; the receipt
  records the served config, so a config that lies about the artifact is
  detectable on re-run.
- benchmark-overfit: tau2 is stateful (evolving DB state decides
  success); hardcoded-answer submissions fail the execution-verified
  scorer by construction.
- luck-by-volume: max 2 open PRs per contributor bounds shotgunning;
  the >2% bar at 200 sims keeps single-run luck out.
- reward hacking the instrument is out of scope by design: the instrument
  is external (Sierra's tau2), we never modify it for scoring.

## Authority clause

`.gittensor/config.json` (mirrored in the SN74 `master_repositories.json`)
is the source of truth for multipliers and eligibility. If a page and the
registry disagree, the registry wins.

## Out of scope (will not merge)

- Changing the scored battery, the operating point, or the >2% rule
  without a maintainer decision and a new EVAL-TRUST section.
- Adding judge models, hidden sets, or sealed subsets (rejected design:
  not trustless, not transparent).
- Submitting remote endpoints or containers (breaks same-box).
