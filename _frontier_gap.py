"""Frontier gap map: which tasks does the frontier (gpt-4.1 reference)
solve that ALL our rungs fail?

The arena's discrimination ceiling, task by task: these are the tasks
that need frontier-level ability. Also prints the reverse (tasks our
rungs solve that the frontier fails) — the contamination/oddity check.

Usage: python3 _frontier_gap.py
"""
import json

from arena.run_tau2 import parse_results

REF = "/opt/data/tau2-bench/data/tau2/results/final/gpt-4.1-2025-04-14_airline_default_gpt-4.1-2025-04-14_4trials.json"
RECEIPTS = [
    "outputs/report_tau2_seed2.json",   # bonsai-1bit 0.16
    "outputs/report_tau2_seed4.json",   # qwen36-iq2xxs 0.54
    "outputs/report_tau2_seed6.json",   # qwen36-q2kxl 0.62
    "outputs/report_tau2_seed5.json",   # qwen3-4b (when it lands)
]

ref = parse_results(REF)
# gpt-4.1: 4 trials per task — task passes if majority (>=2) of trials win
from collections import Counter
ref_wins = Counter()
for pt in ref["per_task"]:
    tid = pt["task_id"]
    ref_wins[tid] = ref_wins.get(tid, 0) + (1 if pt.get("reward", 0) else 0)
ref_pass = {t: (w >= 2) for t, w in ref_wins.items()}
ref_maj = sum(1 for v in ref_pass.values() if v)

rungs = []
for p in RECEIPTS:
    try:
        r = json.load(open(p))
    except FileNotFoundError:
        continue
    pt = r.get("per_task") or []
    rungs.append((r.get("model", p), {x["task_id"]: bool(x.get("reward", 0)) for x in pt}))

print(f"gpt-4.1 reference: {ref_maj}/50 pass (majority of 4 trials)\n")
for name, res in rungs:
    both = sorted(t for t in ref_pass if ref_pass[t] and res.get(t))
    frontier_only = sorted(t for t in ref_pass if ref_pass[t] and not res.get(t))
    our_only = sorted(t for t in res if res[t] and not ref_pass.get(t))
    print(f"== {name} (n={len(res)}) ==")
    print(f"  frontier tasks solved by BOTH: {len(both)}  {both[:10]}")
    print(f"  FRONTIER-ONLY (frontier solves, {name} fails): {len(frontier_only)}  {frontier_only[:10]}")
    print(f"  reverse ({name} solves, frontier fails): {len(our_only)}  {our_only[:10]}")
    print()

print("frontier-only tasks = the arena's discrimination ceiling (need frontier-level ability)")
