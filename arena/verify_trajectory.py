"""Receipt verification for the arena: replay the recorded trajectory through
the CURRENT domain code, re-run the spec-derived assertions, and compare the
re-derived score with the receipt's claims. The board only accepts receipts
that verify.

Usage (run with the tau2-bench venv python, cwd=t2_dir):
    python3 <this> <receipt.json> <t2_dir> [benchbrew_dir]

Checks:
  1. results_sha256 — recompute the hash of the listed results files.
  2. bundle regeneration — if the receipt has a benchbrew block, regenerate
     (spec, seed) and compare bundle_sha256; sampled ids must be in-bundle.
  3. trajectory replay — for every sim, replay the recorded messages into a
     fresh environment, re-run the recorded env assertions on the replayed
     final state, and compare the aggregate score with the receipt.

Prints a JSON verdict to stdout; exit 0 iff verified.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from pydantic import TypeAdapter

from tau2.data_model.message import Message
from tau2.data_model.tasks import EnvAssertion, InitialState


def _results_sha(receipt: dict, t2_dir: Path) -> tuple[str, list[str]]:
    files = [str(p) for p in (receipt.get("results_file") or "").split(",") if p]
    h = hashlib.sha256()
    for rel in files:
        p = t2_dir / rel
        if not p.exists():
            return "", [f"missing results file: {rel}"]
        h.update(p.read_bytes())
    return h.hexdigest(), files


def _regenerate_bundle(receipt: dict, benchbrew_dir: Path) -> tuple[bool, list[str]]:
    bb = receipt.get("benchbrew") or {}
    if not bb:
        return True, ["no benchbrew block; bundle check skipped"]
    seed, n = bb.get("seed"), bb.get("n_tasks")
    if not seed or not n:
        return False, ["benchbrew block missing seed/n_tasks"]
    cmd = [sys.executable, "-m", "benchbrew", "--seed", str(seed),
           "--tasks", str(n), "--quiet"]
    if bb.get("domain"):
        cmd += ["--domain", str(bb["domain"])]
    proc = subprocess.run(cmd, cwd=benchbrew_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        return False, [f"benchbrew regenerate failed: {proc.stderr[-200:]}"]
    kv = {}
    for line in proc.stdout.strip().splitlines():
        if line.startswith("benchbrew "):
            kv = dict(p.split("=", 1) for p in line.split()[1:])
    if kv.get("bundle_sha256") != bb.get("bundle_sha256"):
        return False, ["bundle_sha256 mismatch: receipt claims "
                       f"{bb.get('bundle_sha256')}, regenerated {kv.get('bundle_sha256')}"]
    # sampled ids must be within the regenerated bundle's range
    ids = []
    for dom, raw in (receipt.get("sampled_task_ids") or {}).items():
        try:
            ids += json.loads(raw)
        except (TypeError, ValueError):
            ids += []
    try:
        ok_ids = all(0 <= int(i) < int(n) for i in ids)
    except ValueError:
        ok_ids = False
    if not ok_ids:
        return False, [f"sampled ids {ids} outside regenerated bundle (0..{int(n)-1})"]
    return True, [f"bundle regenerated: sha matches {bb.get('bundle_sha256')[:12]}…"]


def _replay_results(receipt: dict, t2_dir: Path) -> tuple[list[dict], list[str]]:
    """Replay every recorded sim; return per-task re-derived rewards."""
    files = [str(p) for p in (receipt.get("results_file") or "").split(",") if p]
    failures: list[str] = []
    per_task: list[dict] = []
    adapter = TypeAdapter(Message)

    def _env_for(domain: str):
        """Resolve the environment of the domain that produced the sim —
        the arena must replay through the CURRENT domain code, whatever it is."""
        import importlib
        mod = importlib.import_module(f"tau2.domains.{domain}.environment")
        return mod.get_environment()

    domain = (receipt.get("domain") or "marketplace").split("+")[0]
    env = _env_for(domain)
    for rel in files:
        p = t2_dir / rel
        if not p.exists():
            failures.append(f"missing results file: {rel}")
            continue
        data = json.loads(p.read_text())
        tasks = {t["id"]: t for t in data.get("tasks", [])}
        for sim in data.get("simulations", []):
            task = tasks.get(str(sim.get("task_id")))
            if task is None:
                failures.append(f"sim task {sim.get('task_id')} not in results")
                continue
            try:
                init = InitialState.model_validate(task["initial_state"])
            except Exception as e:  # noqa: BLE001
                failures.append(f"task {sim.get('task_id')}: bad initial_state: {e}")
                continue
            msgs = [adapter.validate_python(m) for m in (sim.get("messages") or [])]
            try:
                env.set_state(init.initialization_data, [], msgs, strict=False)
            except Exception as e:  # noqa: BLE001
                failures.append(f"task {sim.get('task_id')}: replay failed: {e}")
                continue
            asserts = (sim.get("reward_info") or {}).get("env_assertions") or []
            if sim.get("reward_info") is None:
                # no result = fail (arena rule, mirrors reconcile_missing):
                # the sim never produced a reward, count it as a scored 0
                per_task.append({"task_id": sim.get("task_id"),
                                 "replay": 0.0, "claimed": None,
                                 "no_result": True})
                continue
            if not asserts:
                per_task.append({"task_id": sim.get("task_id"),
                                 "replay": None, "claimed": None})
                continue
            try:
                results = [
                    env.run_env_assertion(
                        EnvAssertion.model_validate(a["env_assertion"]),
                        raise_assertion_error=False)
                    for a in asserts
                ]
            except Exception as e:  # noqa: BLE001
                failures.append(f"task {sim.get('task_id')}: assertion failed: {e}")
                continue
            per_task.append({
                "task_id": sim.get("task_id"),
                "replay": 1.0 if all(results) else 0.0,
                "claimed": (sim.get("reward_info") or {}).get("reward"),
            })
    return per_task, failures


def verify(receipt_path: Path, t2_dir: Path, benchbrew_dir: Path) -> dict:
    receipt = json.loads(receipt_path.read_text())
    failures: list[str] = []

    sha, files = _results_sha(receipt, t2_dir)
    if not files:
        # a receipt with no evidence has nothing to verify — refuse it
        failures.append("no results files recorded; nothing to verify")
    elif receipt.get("results_sha256") and sha != receipt.get("results_sha256"):
        failures.append("results_sha256 mismatch: receipt claims "
                        f"{receipt.get('results_sha256')}, computed {sha}")

    ok_bundle, bundle_msgs = _regenerate_bundle(receipt, benchbrew_dir)
    if not ok_bundle:
        failures.extend(bundle_msgs)

    # spec-version drift: a benchbrew receipt from another spec epoch is
    # stale, not forged — its tasks no longer exist as scored
    bb = receipt.get("benchbrew") or {}
    if bb.get("spec_version"):
        proc = subprocess.run(
            [sys.executable, "-m", "benchbrew", "--quiet"],
            cwd=benchbrew_dir, capture_output=True, text=True)
        cur = None
        for line in proc.stdout.strip().splitlines():
            if line.startswith("benchbrew "):
                cur = dict(p.split("=", 1) for p in line.split()[1:]).get("version")
        if cur and bb.get("spec_version") != cur:
            failures.append(
                f"stale spec epoch: receipt from marketplace v{bb.get('spec_version')}, "
                f"current spec is v{cur} — re-run the battery on the current lane")

    per_task, replay_failures = _replay_results(receipt, t2_dir)
    failures.extend(replay_failures)

    scored = [pt for pt in per_task if pt["replay"] is not None]
    re_n = len(scored)
    if files and re_n == 0:
        failures.append("no sims carried assertion rewards; nothing re-scored")
    re_ok = sum(1 for pt in scored if pt["replay"] == 1.0)
    re_rate = re_ok / re_n if re_n else None
    claimed_rate = receipt.get("success_rate")
    if re_n and claimed_rate is not None and abs(re_rate - claimed_rate) > 1e-9:
        failures.append(
            f"score mismatch: replay {re_ok}/{re_n} ({re_rate:.3f}) vs "
            f"receipt {receipt.get('n_success')}/{receipt.get('n_scored')} "
            f"({claimed_rate:.3f})")
    mism = [pt for pt in scored if pt["claimed"] is not None
            and pt["replay"] != pt["claimed"]]
    for pt in mism[:5]:
        failures.append(f"task {pt['task_id']}: claimed {pt['claimed']} "
                        f"but replay scores {pt['replay']}")

    return {
        "verified": not failures,
        "failures": failures,
        "checks": {
            "results_sha256": sha,
            "bundle": bundle_msgs,
            "replay": {"n": re_n, "ok": re_ok, "rate": re_rate},
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 2:
        print(json.dumps({"verified": False,
                          "failures": ["usage: verify.py <receipt.json> <t2_dir>"]}))
        return 2
    receipt_path = Path(args[0]).resolve()
    t2_dir = Path(args[1]).resolve()
    benchbrew_dir = Path(args[2]).resolve() if len(args) > 2 else t2_dir.parent / "benchbrew"
    verdict = verify(receipt_path, t2_dir, benchbrew_dir)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
