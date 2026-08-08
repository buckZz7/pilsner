"""Ladder report: read all tau2 arena receipts and print the leaderboard.

Usage: python3 -m arena.ladder_report [output_dir]
Reads outputs/report_tau2_seed*.json and prints a comparison table:
model, score, timing, operating point. Miners can run it to see the board.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def wilson_ci(success_rate: float, n: int, z: float = 1.96) -> tuple:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return (0.0, 0.0)
    p = success_rate
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / denom
    return (max(0.0, center - half), min(1.0, center + half))


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "outputs"
    receipts = sorted(glob.glob(str(out_dir / "report_tau2_seed*.json")))
    if not receipts:
        print(f"no receipts found in {out_dir} (run arena.run_tau2 first)")
        return 1

    rows = []
    for path in receipts:
        with open(path) as f:
            r = json.load(f)
        lo, hi = wilson_ci(r.get("success_rate", 0.0), r.get("n_scored", 0))
        rows.append({
            "model": r.get("model", "?"),
            "success_rate": r.get("success_rate", 0.0),
            "n": f"{r.get('n_success', 0)}/{r.get('n_scored', 0)}",
            "ci": f"{lo:.3f}-{hi:.3f}",
            "mean_reward": r.get("mean_reward", 0.0),
            "wall_clock_s": r.get("wall_clock_s", 0.0),
            "reasoning": r.get("reasoning", "unspecified"),
            "engine": r.get("engine", "unspecified"),
            "domain": r.get("domain", "?"),
            "tau2_commit": (r.get("tau2_git_commit") or "?")[:10],
            "file": Path(path).name,
        })

    rows.sort(key=lambda r: r["success_rate"], reverse=True)
    hdr = (f"{'model':<16} {'score':>6} {'n':>6} {'ci95':>13} {'reward':>7} "
           f"{'wall_s':>8} {'reasoning':>10} {'engine':>10}  file")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['model']:<16} {r['success_rate']:>6.3f} {r['n']:>6} "
              f"{r['ci']:>13} {r['mean_reward']:>7.3f} {r['wall_clock_s']:>8.1f} "
              f"{r['reasoning']:>10} {r['engine']:>10}  {r['file']}")
    print()
    print("operating point: reasoning=%s engine=%s domain=%s tau2=%s"
          % (rows[0]["reasoning"] if rows else "-",
             rows[0]["engine"] if rows else "-",
             rows[0]["domain"] if rows else "-",
             rows[0]["tau2_commit"] if rows else "-"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
