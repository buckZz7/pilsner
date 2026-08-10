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
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .ladder_report import wilson_ci

REPO_ROOT = Path(__file__).resolve().parent.parent


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def build_board(receipts: list[dict]) -> dict:
    """Pool receipts per (model, domain) and rank. One entry per model+domain
    aggregates ALL its verified receipts — cherry-picking a lucky battery
    cannot beat the pool. The king is the top pooled score."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in receipts:
        groups.setdefault((r.get("model", "?"), r.get("domain", "?")), []).append(r)
    entries = []
    for (model, domain), rs in groups.items():
        n_success = sum(r.get("n_success", 0) for r in rs)
        n_scored = sum(r.get("n_scored", 0) for r in rs)
        rate = n_success / n_scored if n_scored else 0.0
        lo, hi = wilson_ci(rate, n_scored)
        weighted = sum(r.get("mean_reward", 0.0) * r.get("n_scored", 0)
                       for r in rs) / n_scored if n_scored else 0.0
        entries.append({
            "model": model,
            "success_rate": round(rate, 4),
            "n_success": n_success,
            "n_scored": n_scored,
            "ci95": [round(lo, 4), round(hi, 4)],
            "mean_reward": round(weighted, 4),
            "wall_clock_s": round(sum(r.get("wall_clock_s", 0.0) for r in rs), 1),
            "reasoning": rs[0].get("reasoning", "unspecified"),
            "engine": rs[0].get("engine", "unspecified"),
            "domain": domain,
            "num_trials": max((r.get("num_trials") for r in rs), default=None),
            "n_receipts": len(rs),
            "receipts": [r.get("seed") for r in rs],
            "tau2_commit": (rs[0].get("tau2_git_commit") or "?")[:10],
            "results_sha256": (rs[0].get("results_sha256") or "")[:16],
            "timestamp": rs[-1].get("timestamp", ""),
        })
    entries.sort(key=lambda e: (-e["success_rate"], -e["n_scored"]))
    for i, e in enumerate(entries):
        e["rank"] = i + 1
    king = entries[0] if entries else None
    return {
        "board_version": 2,
        "updated": datetime.now(timezone.utc).isoformat(),
        "king": f"{king['model']} [{king['domain']}]" if king else None,
        "entries": entries,
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out_dir = Path(args[0]) if args else REPO_ROOT / "outputs"
    write = "--write" in sys.argv
    t2_dir = Path(_env("PILSNER_T2_DIR", str(REPO_ROOT.parent / "tau2-bench")))
    bb_dir = Path(_env("PILSNER_BENCHBREW_DIR",
                       str(REPO_ROOT.parent / "benchbrew")))
    verify_py = t2_dir / ".venv" / "bin" / "python"
    verify_script = REPO_ROOT / "arena" / "verify_trajectory.py"
    paths = sorted(out_dir.glob("report_tau2_seed*.json"))
    if not paths:
        print(f"no receipts in {out_dir}")
        return 1
    admitted, refused = [], []
    for p in paths:
        r = json.load(open(p))
        # admission-time re-verification: the board never trusts a stamp —
        # a receipt whose evidence can't replay against the CURRENT domain
        # code (emitter epochs, spec drift, overwritten packages) is stale,
        # and the stamp is kept honest so drift can't linger unseen
        if verify_py.exists() and verify_script.exists():
            proc = subprocess.run(
                [str(verify_py), str(verify_script), str(p), str(t2_dir),
                 str(bb_dir)],
                capture_output=True, text=True)
            try:
                verdict = json.loads(proc.stdout)
            except ValueError:
                verdict = {"verified": False, "failures": [
                    f"verifier output unparseable: {proc.stdout[-120:]}{proc.stderr[-120:]}"]}
            r["verified"] = bool(verdict.get("verified"))
            r["verification"] = {
                "checks": verdict.get("checks", {}),
                "failures": verdict.get("failures", []),
            }
            p.write_text(json.dumps(r, indent=2))
        if r.get("verified") is True:
            admitted.append(r)
        else:
            refused.append(r)
    if not admitted:
        print("no VERIFIED receipts in the board pool; nothing to crown")
        print(f"({len(refused)} receipts refused: unverified or stale)")
        for r in refused:
            print(f"  - {r.get('model', '?')} [{r.get('domain', '?')}]: "
                  f"{(r.get('verification', {}).get('failures') or ['not verified'])[0][:80]}")
        return 1
    board = build_board(admitted)
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
