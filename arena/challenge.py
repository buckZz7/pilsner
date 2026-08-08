"""Challenge referee: applies the Pilsner king rule to two receipts.

The rule (fixed-king arena):
  - A challenger wins iff its scored-battery success rate beats the king's
    by MORE than 2 percentage points.
  - The king is re-verified against the field on a schedule.
  - Speed (time-to-task, wall clock) is the tie-break among challengers
    that both clear the quality bar; it does not override the quality gate.

Sanity: both receipts must come from the same battery (domain, task count,
trials, operating point) or the comparison is refused — comparing apples to
oranges is how trust dies.

Usage: python3 -m arena.challenge <king_receipt.json> <challenger_receipt.json>
Exit 0 = WIN, 1 = LOSS, 2 = refuse (config mismatch / missing fields).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BEAT_BY = 0.02  # the ratchet: >2 percentage points


def load(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def battery_key(r: dict) -> tuple:
    """Identity of the battery a receipt was measured on."""
    return (
        r.get("domain"),
        r.get("num_tasks"),
        r.get("num_trials"),
        r.get("task_split"),
        r.get("reasoning"),
        r.get("engine"),
        r.get("parallel"),
        r.get("user_llm"),
    )


def decide(king: dict, challenger: dict) -> dict:
    """Apply the rule. Returns a result dict, never raises on data shape."""
    if battery_key(king) != battery_key(challenger):
        return {"verdict": "refuse", "reason": "battery mismatch",
                "king_battery": battery_key(king),
                "challenger_battery": battery_key(challenger)}
    for r in (king, challenger):
        if "success_rate" not in r or "n_scored" not in r:
            return {"verdict": "refuse", "reason": "missing score fields",
                    "file": r.get("model")}
    if not king.get("n_scored"):
        return {"verdict": "refuse", "reason": "king has no scored tasks"}

    ks, cs = king["success_rate"], challenger["success_rate"]
    beats = cs >= ks + BEAT_BY
    # noise floor on the difference (normal approx, both batteries same N)
    n = challenger.get("n_scored") or 0
    se = 0.0
    if n:
        p = (ks + cs) / 2
        se = (2 * p * (1 - p) / n) ** 0.5
    return {
        "verdict": "win" if beats else "loss",
        "king": king.get("model"),
        "challenger": challenger.get("model"),
        "king_score": ks,
        "challenger_score": cs,
        "gap": cs - ks,
        "rule": f">{BEAT_BY:.0%}",
        "n_scored": n,
        "diff_se": round(se, 4),
        "king_wall_clock_s": king.get("wall_clock_s"),
        "challenger_wall_clock_s": challenger.get("wall_clock_s"),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python3 -m arena.challenge <king.json> <challenger.json>")
        return 2
    king = load(Path(sys.argv[1]))
    challenger = load(Path(sys.argv[2]))
    r = decide(king, challenger)
    print(json.dumps(r, indent=2))
    return {"win": 0, "loss": 1, "refuse": 2}[r["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
