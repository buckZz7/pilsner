"""Validate the difficulty map against Sierra's published reference finals.

The tau2 repo ships gpt-4.1 results on the airline battery (50 tasks x 4
trials). If the difficulty map predicts the REFERENCE model's failures,
the battery discriminates on difficulty — validated against frontier
data, before our own receipts even land.
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arena.run_tau2 import parse_results  # noqa: E402

T2 = Path("/opt/data/tau2-bench")
REF = T2 / "data/tau2/results/final/gpt-4.1-2025-04-14_airline_default_gpt-4.1-2025-04-14_4trials.json"

tasks = json.load(open(T2 / "data/tau2/domains/airline/tasks.json"))
dm = {str(t.get("id")): (len((t.get("evaluation_criteria") or {}).get("actions") or [])
                          + len((t.get("evaluation_criteria") or {}).get("env_assertions") or [])
                          + len((t.get("evaluation_criteria") or {}).get("nl_assertions") or []))
      for t in tasks}

score = parse_results(REF)
by_task = {}
for pt in score["per_task"]:
    by_task.setdefault(pt["task_id"], []).append(pt["reward"])

# task-level: pass if MAJORITY of 4 trials reward >= 1.0
failed, passed = [], []
for tid, rewards in by_task.items():
    cx = dm.get(str(tid))
    if cx is None:
        continue
    (passed if sum(1 for r in rewards if r >= 1.0) >= len(rewards) / 2 else failed).append(cx)

print(f"gpt-4.1 airline reference (4 trials/task): {len(passed)} passed, {len(failed)} failed")
if failed and passed:
    print(f"mean difficulty — passed: {statistics.mean(passed):.1f} "
          f"failed: {statistics.mean(failed):.1f}")
    print(f"median difficulty — passed: {statistics.median(passed):.1f} "
          f"failed: {statistics.median(failed):.1f}")
    for lo, hi in ((0, 4), (5, 9), (10, 99)):
        bucket = [cx for cx in passed + failed if lo <= cx <= hi]
        if bucket:
            pr = sum(1 for cx in passed if lo <= cx <= hi) / len(bucket)
            print(f"  difficulty {lo}-{hi}: pass rate {pr:.0%} (n={len(bucket)})")
elif not failed:
    print("gpt-4.1 passes everything on this battery — no discrimination signal")
else:
    print("gpt-4.1 fails everything — battery too hard for the reference")
