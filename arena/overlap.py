"""Task-overlap comparator: which tasks does each rung pass/fail that
others don't?

Usage: python3 -m arena.overlap <receiptA.json> <receiptB.json> [more...]
Prints the pass/fail overlap matrix and the task ids in each cell.
"""
from __future__ import annotations

import json
import sys


def load(path: str) -> dict:
    r = json.load(open(path))
    pt = r.get("per_task") or []
    return {
        "model": r.get("model", path),
        "n_scored": r.get("n_scored", len(pt)),
        "success": {p["task_id"]: bool(p.get("reward", 0)) for p in pt},
    }


def main() -> int:
    paths = [p for p in sys.argv[1:] if p.endswith(".json")]
    if len(paths) < 2:
        print("usage: overlap <receiptA.json> <receiptB.json> ...")
        return 1
    rs = [load(p) for p in paths]
    for a, b in ((rs[i], rs[j]) for i in range(len(rs)) for j in range(i + 1, len(rs))):
        a_only, b_only, both, neither = [], [], [], []
        ids = set(a["success"]) | set(b["success"])
        for t in sorted(ids, key=int):
            pa, pb = a["success"].get(t), b["success"].get(t)
            if pa and pb:
                both.append(t)
            elif pa:
                a_only.append(t)
            elif pb:
                b_only.append(t)
            else:
                neither.append(t)
        print(f"== {a['model']} vs {b['model']} ==")
        print(f"  both pass : {len(both):>3}  {both[:12]}")
        print(f"  both fail : {len(neither):>3}  {neither[:12]}")
        print(f"  {a['model']:<14} only: {len(a_only):>3}  {a_only[:12]}")
        print(f"  {b['model']:<14} only: {len(b_only):>3}  {b_only[:12]}")
        print(f"  unique value: {b['model']} rescues {len(b_only)} tasks "
              f"{a['model']} fails; reverse rescues {len(a_only)}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
