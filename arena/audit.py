"""Receipt audit: schema validity + cross-receipt comparability.

The arena's trust promise is that every published number can be
re-run and compared. This verifies: (1) each receipt has the required
provenance fields, (2) receipts that appear on the same board are from
comparable batteries (same domain set, tasks, trials, caps, operating
point, engine, context, user sim).

Usage: python3 -m arena.audit <receipt.json>...
Exit 0 = all comparable, 1 = problems found.
"""
from __future__ import annotations

import json
import sys

REQUIRED = [
    "model", "base_url", "reasoning", "engine", "parallel", "context",
    "max_steps", "user_llm", "success_rate", "n_success", "n_scored",
    "wall_clock_s", "results_sha256", "tau2_git_commit",
]
# Fields that MUST match for two receipts to be on the same board.
COMPARABLE = [
    "domain", "num_tasks", "num_trials", "max_steps", "reasoning",
    "engine", "parallel", "context", "user_llm",
]


def audit(path: str) -> tuple[list[str], dict]:
    r = json.load(open(path))
    model = r.get("model", path)
    problems = []
    for f in REQUIRED:
        if f not in r or r.get(f) in (None, "", "unspecified"):
            problems.append(f"missing field: {f}")
    return problems, {k: r.get(k) for k in COMPARABLE}


def main() -> int:
    paths = [p for p in sys.argv[1:] if p.endswith(".json")]
    if not paths:
        print("usage: audit <receipt.json>..."); return 1
    problems = []
    rows = []
    for p in paths:
        probs, row = audit(p)
        model = json.load(open(p)).get("model", p)
        rows.append((model, row))
        if probs:
            problems.append((model, probs))
        print(f"{model:<16} ok" if not probs else
              f"{model:<16} PROBLEMS: {probs}")
    # cross-receipt comparability
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            m1, r1 = rows[i]; m2, r2 = rows[j]
            diffs = [k for k in COMPARABLE if r1.get(k) != r2.get(k)]
            if diffs:
                problems.append((f"{m1} vs {m2}",
                                 [f"{k}: {r1.get(k)} != {r2.get(k)}" for k in diffs]))
                print(f"  INCOMPARABLE: {m1} vs {m2} -> {diffs}")
    print()
    if problems:
        print(f"audit FAILED: {len(problems)} issue(s)")
        return 1
    print("audit PASSED: all receipts valid and comparable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
