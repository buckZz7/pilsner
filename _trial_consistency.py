"""Trial consistency of the gpt-4.1 reference finals.

The scored battery is 4 trials x 50 tasks; the king rule needs a stable
per-task decision. If a frontier model FLIPS tasks between trials, the
majority rule needs the right threshold. Analyzes Sierra's published
gpt-4.1 airline finals (4 trials/task).
"""
import json
from pathlib import Path

REF = Path("/opt/data/tau2-bench/data/tau2/results/final/gpt-4.1-2025-04-14_airline_default_gpt-4.1-2025-04-14_4trials.json")
d = json.load(open(REF))
sims = d.get("simulations") or []
by_task: dict[str, list[float]] = {}
for s in sims:
    ri = s.get("reward_info") or {}
    r = ri.get("reward")
    if r is None:
        continue
    by_task.setdefault(s.get("task_id"), []).append(float(r))

counts = {k: 0 for k in range(5)}
for tid, rewards in by_task.items():
    wins = sum(1 for r in rewards if r >= 1.0)
    counts[wins] += 1

print(f"tasks: {len(by_task)} | avg trials/task: "
      f"{sum(len(v) for v in by_task.values())/len(by_task):.1f}")
print("per-task win pattern (out of 4 trials):")
for wins in range(4, -1, -1):
    print(f"  {wins}/4: {counts[wins]} tasks ({counts[wins]/len(by_task):.0%})")
flip = counts[1] + counts[2] + counts[3]
print(f"\nflip-prone tasks (1-3/4): {flip} ({flip/len(by_task):.0%})")
print("majority rule (>=2/4 = pass):", counts[2] + counts[3] + counts[4],
      f"tasks vs strict (4/4): {counts[4]}")
