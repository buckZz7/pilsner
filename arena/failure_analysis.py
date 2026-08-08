"""Failure analysis: does the difficulty map predict task failures?

Merges a receipt's per-task rewards with the task difficulty profile and
answers: do failed tasks concentrate in the hard tail? If yes, the
battery separates models on difficulty (good). If failures are uniform,
the score is closer to noise (bad — a battery design problem).

Usage: python3 -m arena.failure_analysis <receipt.json> [tau2-bench-dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

T2 = Path(sys.argv[2] if len(sys.argv) > 2 else "/opt/data/tau2-bench")


def difficulty_map(domain: str) -> dict:
    p = T2 / "data" / "tau2" / "domains" / domain / "tasks.json"
    tasks = json.load(open(p))
    out = {}
    for t in tasks:
        ec = t.get("evaluation_criteria") or {}
        out[str(t.get("id"))] = (len(ec.get("actions") or [])
                                 + len(ec.get("env_assertions") or [])
                                 + len(ec.get("nl_assertions") or []))
    return out


def main() -> int:
    receipt = json.load(open(sys.argv[1]))
    domain = receipt.get("domain", "airline")
    dm = difficulty_map(domain)
    per_task = receipt.get("per_task", [])
    if not per_task:
        print("receipt has no per_task data")
        return 1
    failed, passed = [], []
    for pt in per_task:
        cx = dm.get(str(pt.get("task_id")))
        if cx is None:
            continue
        (passed if pt.get("reward", 0) >= 1.0 else failed).append(cx)
    if not failed or not passed:
        print(f"all-{'passed' if passed else 'failed'} — no separation yet "
              f"({len(passed)} pass / {len(failed)} fail)")
        return 0
    import statistics
    print(f"domain {domain}: {len(passed)} passed, {len(failed)} failed")
    print(f"mean difficulty — passed: {statistics.mean(passed):.1f} "
          f"failed: {statistics.mean(failed):.1f}")
    print(f"median difficulty — passed: {statistics.median(passed):.1f} "
          f"failed: {statistics.median(failed):.1f}")
    # pass rate by difficulty bucket
    for lo, hi in ((0, 4), (5, 9), (10, 99)):
        bucket = [cx for cx in passed + failed if lo <= cx <= hi]
        if bucket:
            pr = sum(1 for cx in passed if lo <= cx <= hi) / len(bucket)
            print(f"  difficulty {lo}-{hi}: pass rate {pr:.0%} (n={len(bucket)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
