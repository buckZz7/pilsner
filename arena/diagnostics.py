"""Tool diagnostics per receipt: the mechanism behind the score.

Surfaces WHY a model scored what it did: tool-call volume, tool-error
rate (bad args / exec failures — the precision signal), and termination
reasons (too_many_errors = error compounding; max_steps = grind).

Usage: python3 -m arena.diagnostics <receipt.json>...
"""
from __future__ import annotations

import json
import sys


def diagnostics(receipt: dict) -> dict:
    pt = receipt.get("per_task") or []
    calls = sum(p.get("tool_calls", 0) for p in pt)
    errors = sum(p.get("tool_errors", 0) for p in pt)
    terms: dict[str, int] = {}
    for p in pt:
        t = p.get("termination") or "?"
        terms[t] = terms.get(t, 0) + 1
    return {
        "model": receipt.get("model"),
        "n_scored": receipt.get("n_scored"),
        "success_rate": receipt.get("success_rate"),
        "tool_calls": calls,
        "tool_errors": errors,
        "tool_error_rate": (errors / calls) if calls else 0.0,
        "calls_per_task": calls / len(pt) if pt else 0.0,
        "terminations": terms,
    }


def main() -> int:
    for path in sys.argv[1:]:
        if not path.endswith(".json"):
            continue
        r = json.load(open(path))
        d = diagnostics(r)
        print(f"== {d['model']} ==")
        print(f"  score: {d['success_rate']:.3f} ({d['n_scored']} sims)")
        print(f"  tool calls: {d['tool_calls']} "
              f"({d['calls_per_task']:.1f}/task) | errors: {d['tool_errors']} "
              f"(rate {d['tool_error_rate']:.0%})")
        top = sorted(d["terminations"].items(), key=lambda kv: -kv[1])[:4]
        print("  terminations: " + ", ".join(f"{k}={v}" for k, v in top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
