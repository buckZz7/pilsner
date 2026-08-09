"""Board: the arena's published leaderboard.

Reads all tau2 receipts, ranks them, designates the king, and writes
leaderboard.json — the single source of truth for the board behind the
bar. Every entry carries its score, Wilson CI, wall clock, and operating
point, so the board never shows a naked number.

Usage: python3 -m arena.board [output_dir] [--write]
Without --write: prints the board. With --write: also writes/updates
leaderboard.json in the output dir.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .ladder_report import wilson_ci

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_board(receipts: list[dict]) -> dict:
    """Rank receipts; the top score is the king. Returns board dict."""
    entries = []
    for r in receipts:
        lo, hi = wilson_ci(r.get("success_rate", 0.0), r.get("n_scored", 0))
        entries.append({
            "model": r.get("model", "?"),
            "success_rate": r.get("success_rate", 0.0),
            "n_success": r.get("n_success", 0),
            "n_scored": r.get("n_scored", 0),
            "ci95": [round(lo, 4), round(hi, 4)],
            "mean_reward": r.get("mean_reward", 0.0),
            "wall_clock_s": r.get("wall_clock_s", 0.0),
            "reasoning": r.get("reasoning", "unspecified"),
            "engine": r.get("engine", "unspecified"),
            "domain": r.get("domain", "?"),
            "num_trials": r.get("num_trials"),
            "receipt": r.get("results_file", ""),
            "tau2_commit": (r.get("tau2_git_commit") or "?")[:10],
            "results_sha256": (r.get("results_sha256") or "")[:16],
            "timestamp": r.get("timestamp", ""),
        })
    entries.sort(key=lambda e: (e["success_rate"], -e["wall_clock_s"]),
                 reverse=True)
    for i, e in enumerate(entries):
        e["rank"] = i + 1
    king = entries[0] if entries else None
    return {
        "board_version": 1,
        "updated": datetime.now(timezone.utc).isoformat(),
        "king": king["model"] if king else None,
        "entries": entries,
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out_dir = Path(args[0]) if args else REPO_ROOT / "outputs"
    write = "--write" in sys.argv
    paths = sorted(out_dir.glob("report_tau2_seed*.json"))
    if not paths:
        print(f"no receipts in {out_dir}")
        return 1
    receipts = [json.load(open(p)) for p in paths]
    board = build_board(receipts)
    print(f"king: {board['king']}  (kings are per-lane; compare within a domain)")
    for e in board["entries"]:
        print(f"  #{e['rank']} {e['model']:<16} {e['success_rate']:.3f} "
              f"[{e['ci95'][0]:.3f}-{e['ci95'][1]:.3f}] wall={e['wall_clock_s']:.0f}s "
              f"({e['n_success']}/{e['n_scored']}) {e['reasoning']} "
              f"[{e.get('domain', '?')}]")
    if write:
        target = out_dir / "leaderboard.json"
        target.write_text(json.dumps(board, indent=2))
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
