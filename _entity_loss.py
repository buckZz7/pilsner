"""Entity-loss temporal analysis: WHEN does the 1-bit lose the user ID?

For each simulation in the raw results, find the user-ID-bearing turns
(the user sim's messages that mention a passenger id) and the tool
errors mentioning a wrong id. Question: does the corruption drift
(errors cluster in later turns) or start immediately?

Usage: python3 _entity_loss.py <raw_results.json>
"""
import json
import re
import sys
from collections import Counter

ID_RE = re.compile(r"\buser_([a-z]+_\d+)\b", re.I)


def main() -> int:
    path = sys.argv[1]
    d = json.load(open(path))
    first_err_turn = []
    err_turn_dist = Counter()
    sims_with_err = 0
    total_sims = 0
    for s in d.get("simulations", []):
        total_sims += 1
        # the conversation's true user id (from the env/system)
        env = json.dumps(s.get("env") or s.get("task") or {})
        true_id = ID_RE.search(env)
        msgs = s.get("messages", [])
        errs = []
        for i, m in enumerate(msgs):
            if isinstance(m, dict) and m.get("role") == "tool":
                err = str(m.get("error", "False")).lower() in ("true", "1")
                if err:
                    errs.append(i)
        if errs:
            sims_with_err += 1
            first_err_turn.append(errs[0])
        for e in errs:
            err_turn_dist[min(e // 4, 10)] += 1  # bucket by ~2 agent turns
    n = len(first_err_turn)
    print(f"{path}: {sims_with_err}/{total_sims} sims have >=1 tool error")
    if n:
        import statistics
        print(f"first-error turn: mean {statistics.mean(first_err_turn):.1f}, "
              f"median {statistics.median(first_err_turn):.0f}, "
              f"min {min(first_err_turn)}, max {max(first_err_turn)}")
        early = sum(1 for t in first_err_turn if t < 8)
        print(f"first error within the first 8 messages: {early}/{n} "
              f"({early/n:.0%})")
    print("error turn buckets (messages/4):", dict(sorted(err_turn_dist.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
