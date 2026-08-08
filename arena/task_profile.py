"""Profile tau2 tasks for difficulty features.

Goal: characterize what makes a task expensive (long conversation, many
tool calls, many assertions) so the scored battery is understood:
the hard tail is where models separate, and it predicts eval wall time.
Usage: python3 -m arena.task_profile [tau2-bench-dir]
"""
import json
import statistics
import sys
from pathlib import Path

T2 = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/data/tau2-bench")
DOMAINS = ("airline", "retail", "telecom")
for domain in DOMAINS:
    p = T2 / "data" / "tau2" / "domains" / domain / "tasks.json"
    if not p.exists():
        continue
    tasks = json.load(open(p))
    rows = []
    for t in tasks:
        ec = t.get("evaluation_criteria") or {}
        actions = ec.get("actions") or []
        env = ec.get("env_assertions") or []
        nl = ec.get("nl_assertions") or []
        rows.append({
            "id": t.get("id"),
            "purpose": ((t.get("description") or {}).get("purpose") or "")[:70],
            "n_actions": len(actions),
            "n_env_asserts": len(env),
            "n_nl_asserts": len(nl),
            "complexity": len(actions) + len(env) + len(nl),
        })
    rows.sort(key=lambda r: r["complexity"], reverse=True)
    cxs = [r["complexity"] for r in rows]
    print(f"== {domain}: {len(rows)} tasks | complexity med={statistics.median(cxs)} "
          f"max={max(cxs)} | >=5 actions: {sum(1 for r in rows if r['n_actions'] >= 5)}")
    for r in rows[:6]:
        print(f"   {r['id']:>4} act={r['n_actions']:>2} env={r['n_env_asserts']:>2} "
              f"nl={r['n_nl_asserts']:>2} cx={r['complexity']:>2}  {r['purpose']}")
