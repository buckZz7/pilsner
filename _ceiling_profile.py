"""What IS the frontier ceiling? Difficulty profile of the frontier-only
tasks (both 2-bit flavors fail, gpt-4.1 passes). If they're just the
hardest tasks, the ceiling = difficulty. If not, it's a task TYPE.

Usage: python3 _ceiling_profile.py
"""
import json
from collections import Counter

from arena.run_tau2 import parse_results

REF = "/opt/data/tau2-bench/data/tau2/results/final/gpt-4.1-2025-04-14_airline_default_gpt-4.1-2025-04-14_4trials.json"
TASKS = "/opt/data/tau2-bench/data/tau2/domains/airline/tasks.json"
RECEIPTS = ["outputs/report_tau2_seed4.json", "outputs/report_tau2_seed6.json"]

ref = parse_results(REF)
from collections import defaultdict
wins = defaultdict(int)
for pt in ref["per_task"]:
    wins[pt["task_id"]] += 1 if pt.get("reward", 0) else 0
ref_pass = {t for t, w in wins.items() if w >= 2}

fail_both = set()
for p in RECEIPTS:
    r = json.load(open(p))
    fails = {x["task_id"] for x in r["per_task"] if not x.get("reward", 0)}
    fail_both = fail_both | fails if not fail_both else fail_both & fails

ceiling = sorted(ref_pass & fail_both, key=int)

tasks = json.load(open(TASKS))
by_id = {}
for t in tasks:
    ec = t.get("evaluation_criteria") or {}
    by_id[t.get("id", t.get("task_id"))] = t

print(f"frontier-only ceiling tasks: {len(ceiling)} {ceiling}\n")
print(f"{'task':>5} {'actions':>7} {'nl_asrt':>7} {'sum':>4}  purpose")
for tid in ceiling:
    t = by_id.get(tid, {})
    ec = t.get("evaluation_criteria") or {}
    na = len(ec.get("actions") or [])
    nla = len(ec.get("nl_assertions") or [])
    purpose = ((t.get("description") or {}).get("purpose") or "")[:55]
    print(f"{tid:>5} {na:>7} {nla:>7} {na+nla:>4}  {purpose}")

print()
passing = sorted(ref_pass - fail_both, key=int)
print(f"tasks BOTH 2-bit pass AND frontier passes: {len(passing)}")
for tid in passing[:10]:
    t = by_id.get(tid, {})
    ec = t.get("evaluation_criteria") or {}
    na = len(ec.get("actions") or [])
    nla = len(ec.get("nl_assertions") or [])
    purpose = ((t.get("description") or {}).get("purpose") or "")[:45]
    print(f"{tid:>5} actions={na:>2} nl={nla:>2} sum={na+nla:>3}  {purpose}")
