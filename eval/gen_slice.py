"""Generalization guardrail slice.

Mechanical arithmetic word problems with computed answers. The point is
NOT to test math ability — it's to prove the submitted model is not a
brain-damaged tool-calling-only zombie (catastrophic forgetting guard).
Exact numeric answer matching, no judge.
"""
from __future__ import annotations

import json
import random

_NAMES = ["Ana", "Ben", "Cara", "Diego", "Elena", "Felix", "Gina", "Hugo"]


def _word_problem(rng: random.Random) -> dict:
    kind = rng.randint(0, 3)
    a, b, c = rng.randint(5, 99), rng.randint(5, 99), rng.randint(2, 9)
    if kind == 0:
        q = f"{rng.choice(_NAMES)} has {a} apples and gets {b} more. How many apples total?"
        ans = a + b
    elif kind == 1:
        q = f"{rng.choice(_NAMES)} has {a * c} candies and shares them equally among {c} friends. How many candies does each friend get?"
        ans = a
    elif kind == 2:
        q = f"A train travels at {a} km/h for {b} hours. How many kilometers does it travel?"
        ans = a * b
    else:
        q = f"{rng.choice(_NAMES)} buys {c} items at ${a} each and pays with ${a * c + b}. How much change in dollars?"
        ans = b
    return {"type": "gen", "query": q, "expected": str(ans)}


def generate_gen_slice(seed: int, n: int = 25) -> list[dict]:
    rng = random.Random(seed + 10_000)  # different stream from FC items
    items = []
    for i in range(n):
        p = _word_problem(rng)
        p["id"] = f"{seed}:gen:{i}"
        items.append(p)
    return items


def save_slice(items: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, indent=2)
