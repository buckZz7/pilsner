"""Arena runner: serve model -> run tau2-bench -> time it -> receipt.

The scored instrument of the Pilsner arena. Talks to any OpenAI-compatible
endpoint (vLLM / llama.cpp server / SGLang) and drives the external tau2-bench
evaluation (sierra-research/tau2-bench, MIT) against it. Base-agnostic by
construction: swapping the served model is a config change, not a code change.

Env contract (mirrors the FC harness):
  PILSNER_MODEL         served model name (default: "model")
  PILSNER_BASE_URL      OpenAI-compatible base URL (default: http://localhost:8000/v1)
  PILSNER_T2_DIR        tau2-bench checkout (default: ../tau2-bench next to this repo)
  PILSNER_T2_DOMAIN     tau2 domain (default: airline)
  PILSNER_T2_TASKS      number of tasks to run (default: 10)
  PILSNER_T2_TRIALS     trials per task (default: 1)
  PILSNER_T2_MAX_STEPS  cap on conversation steps per trial (default:
                        tau2's 200 — too generous for an arena; the
                        scored battery uses 50. Pathological tasks grind
                        2h at 200.)
  PILSNER_T2_MAX_STEPS_SECONDS  per-attempt wall cap in seconds
                        (default: tau2's 1200; scored battery uses 600)
  PILSNER_T2_TASK_SPLIT task split (default: base)
  PILSNER_SEED          seed slot (default: 1; recorded in the receipt)
  PILSNER_OUT           output dir (default: outputs)
  PILSNER_REASONING     thinking operating point served by the engine:
                        on|off|auto (default: unspecified; the scored
                        operating point of the arena is off)
  PILSNER_ENGINE        serving engine (e.g. llama.cpp, vllm; default unspecified)
  PILSNER_PARALLEL      server concurrency slots (default: unspecified;
                        speed comparisons require same parallel)
  PILSNER_ENGINE_VERSION  serving engine build (e.g. llama.cpp git commit;
                        default unspecified). Recorded in the receipt —
                        engine builds change measurements (a too-old
                        build can't load newer quant types).
  PILSNER_MODEL_SHA256  sha256 of the served model file (default
                        unspecified). Recorded in the receipt — binds
                        the receipt to the exact artifact, so a tampered
                        file is visible (sparkinfer baseline-verify
                        pattern).
  PILSNER_GPU_CLOCK     observed GPU graphics clock at serve time
                        (default unspecified). Recorded so the
                        wall-clock tie-break is clock-checkable.
  PILSNER_CTX           server context per slot (n_ctx_slot; default
                        unspecified). Recorded in the receipt — context
                        changes measurements, so it is part of the
                        battery key. NOTE: `-c N --parallel P` with a
                        non-unified KV cache gives each slot N/P, not N.
  PILSNER_USER_MODEL    fixed user-simulator model (default: same as agent).
                        The scored battery uses a FIXED user sim across all
                        entries so the customer is constant — otherwise a
                        weak model plays a pushover customer and inflates
                        its own agent score (the ladder confound).
  PILSNER_USER_BASE_URL user-sim endpoint (default: same as PILSNER_BASE_URL)

Outputs:
  outputs/report_tau2_seed<N>.json  the receipt: score + timing + provenance

The receipt is the arena's evidence unit. Nothing in it is a judgment: it
records what was served, what tau2 ran, what the environment said, and how
long the battery took on this box. Reproduce = serve the same model, same
endpoint, same tau2 commit, same seed, same box.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def build_command(
    model: str,
    base_url: str,
    domain: str,
    num_tasks: int,
    num_trials: int,
    max_steps: int | None,
    task_split: str,
    user_model: str | None = None,
    user_base_url: str | None = None,
) -> list[str]:
    """Build the tau2 CLI arguments (after the executable) for a served model.

    user_model/user_base_url override the user simulator (the fixed-user
    design for the scored battery); defaults to the agent model/endpoint.
    """
    litellm_model = model if "/" in model else f"openai/{model}"
    umodel = user_model or model
    litellm_user = umodel if "/" in umodel else f"openai/{umodel}"
    ubase = user_base_url or base_url
    llm_args = json.dumps({"api_base": base_url, "temperature": 0.0})
    user_args = json.dumps({"api_base": ubase, "temperature": 0.0})
    cmd = [
        "run",
        "--domain", domain,
        "--agent-llm", litellm_model,
        "--agent-llm-args", llm_args,
        "--user-llm", litellm_user,
        "--user-llm-args", user_args,
        "--num-trials", str(num_trials),
        "--num-tasks", str(num_tasks),
        "--task-split-name", task_split,
    ]
    if max_steps is not None:
        cmd += ["--max-steps", str(max_steps)]
    return cmd


def parse_results(results_path: Path) -> dict:
    """Extract score + provenance from a tau2 results.json."""
    with open(results_path) as f:
        data = json.load(f)
    sims = data.get("simulations", [])
    rewards = []
    per_task = []
    for s in sims:
        ri = s.get("reward_info") or {}
        reward = ri.get("reward")
        if reward is None:
            continue
        rewards.append(float(reward))
        per_task.append({
            "task_id": s.get("task_id", "?"),
            "reward": reward,
            "tool_calls": _tool_call_count(s),
            "tool_errors": _tool_error_count(s),
            "termination": str(s.get("termination_reason") or ""),
        })
    n_success = sum(1 for r in rewards if r >= 1.0)
    total = len(rewards)
    info = data.get("info", {})
    return {
        "n_success": n_success,
        "n_scored": total,
        "success_rate": (n_success / total) if total else 0.0,
        "mean_reward": (sum(rewards) / total) if total else 0.0,
        "per_task": per_task,
        "seed": info.get("seed"),
        "tau2_git_commit": info.get("git_commit"),
        "agent_llm": info.get("agent_info", {}).get("llm"),
        "user_llm": info.get("user_info", {}).get("llm"),
    }


def reconcile_missing(score: dict, expected_ids: list[str],
                      num_trials: int = 1) -> dict:
    """Count no-result tasks AND trials as failures (arena rule: no
    result = fail).

    tau2 skips tasks that error out (server kills, retry exhaustion,
    context caps). The arena must not let a model dodge the hard tail by
    failing to finish: missing tasks are scored 0 and marked no_result.
    With num_trials > 1, missing TRIALS are filled too — a task that
    errored in 2 of its 4 trials must show 4 rows, not 2.
    """
    counts: dict[str, int] = {}
    for pt in score["per_task"]:
        counts[str(pt.get("task_id"))] = counts.get(str(pt.get("task_id")), 0) + 1
    added = 0
    for tid in expected_ids:
        have = counts.get(str(tid), 0)
        need = num_trials - have
        if need > 0:
            for _ in range(need):
                score["per_task"].append(
                    {"task_id": str(tid), "reward": 0.0, "no_result": True})
            added += need
    if added:
        score["n_scored"] = len(score["per_task"])
        score["n_success"] = sum(1 for pt in score["per_task"]
                                 if pt["reward"] >= 1.0)
        score["success_rate"] = score["n_success"] / score["n_scored"]
        score["mean_reward"] = (sum(pt["reward"] for pt in score["per_task"])
                                / score["n_scored"])
    return score


def expected_task_ids(t2_dir: Path, domain: str, num_tasks: int,
                      sample: str = "first", seed: int = 1) -> tuple[list[str], str]:
    """The task ids of the domain's base split for a battery.

    sample="first"  -> first num_tasks (current behavior).
    sample="random" -> seeded deterministic shuffle, take num_tasks; the
                       seed is recorded in the receipt so the exact
                       battery is reproducible. Random sampling raises
                       the cost of memorizing the public task pool (an
                       adversarial-review mitigation): a miner must
                       overfit the whole pool, not just the first N.
    Returns (ids, sampled_json) — the sampled ids as a JSON string for
    the receipt (provenance: the exact task list is part of the battery
    identity, like context and caps).
    """
    p = t2_dir / "data" / "tau2" / "domains" / domain / "tasks.json"
    if p.exists():
        tasks = json.load(open(p))
        ids = [str(t.get("id")) for t in tasks]
    else:
        ids = [str(i) for i in range(num_tasks)]
    if sample == "random" and len(ids) > num_tasks:
        import random
        rng = random.Random(seed)
        ids = rng.sample(ids, num_tasks)
    else:
        ids = ids[:num_tasks]
    return ids, json.dumps(sorted(ids, key=int))


def merge_scores(scores: list[dict]) -> dict:
    """Merge per-domain scores into one aggregate (multi-domain battery).

    per_task entries carry their domain tag; counts sum across domains.
    """
    merged = {
        "per_task": [pt for s in scores for pt in s["per_task"]],
        "n_scored": sum(s["n_scored"] for s in scores),
        "n_success": sum(s["n_success"] for s in scores),
        "tau2_git_commit": scores[0]["tau2_git_commit"],
        "agent_llm": scores[0]["agent_llm"],
        "user_llm": scores[0].get("user_llm"),
    }
    merged["success_rate"] = merged["n_success"] / merged["n_scored"]
    merged["mean_reward"] = (sum(pt["reward"] for pt in merged["per_task"])
                             / merged["n_scored"])
    return merged


def _msg_tool_calls(msg) -> int:
    """Count tool calls in a message.

    tau2's results.json serializes the field as a Python repr (single
    quotes) OR JSON — try both.
    """
    tc = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
    if not tc or tc == "None":
        return 0
    if isinstance(tc, str):
        try:
            tc = json.loads(tc)
        except (ValueError, TypeError):
            try:
                import ast
                tc = ast.literal_eval(tc)
            except (ValueError, SyntaxError, TypeError):
                return 0
    return len(tc) if isinstance(tc, (list, tuple)) else 0


def _tool_call_count(sim: dict) -> int:
    return sum(_msg_tool_calls(m) for m in (sim.get("messages") or []))


def _tool_error_count(sim: dict) -> int:
    n = 0
    for m in sim.get("messages") or []:
        if not isinstance(m, dict):
            continue
        if m.get("role") != "tool":
            continue
        err = m.get("error")
        if isinstance(err, str) and err.lower() in ("true", "1"):
            n += 1
        elif err is True:
            n += 1
    return n


def latest_results(t2_dir: Path) -> Path | None:
    """Newest results.json under data/simulations/ (live tau2 run output)."""
    matches = sorted(
        glob.glob(str(t2_dir / "data" / "simulations" / "*" / "results.json")),
        key=os.path.getmtime,
    )
    return Path(matches[-1]) if matches else None


def tau2_binary(t2_dir: Path) -> str:
    """Prefer the checkout's own venv; fall back to PATH."""
    venv_bin = t2_dir / ".venv" / "bin" / "tau2"
    return str(venv_bin) if venv_bin.is_file() else "tau2"


def main() -> int:
    model = _env("PILSNER_MODEL", "model")
    base_url = _env("PILSNER_BASE_URL", "http://localhost:8000/v1")
    t2_dir = Path(_env("PILSNER_T2_DIR", str(REPO_ROOT.parent / "tau2-bench")))
    domain = _env("PILSNER_T2_DOMAIN", "airline")
    domains = [d.strip() for d in
               _env("PILSNER_T2_DOMAINS", domain).split(",") if d.strip()]
    num_tasks = int(_env("PILSNER_T2_TASKS", "10"))
    num_trials = int(_env("PILSNER_T2_TRIALS", "1"))
    max_steps_env = _env("PILSNER_T2_MAX_STEPS", "")
    max_steps = int(max_steps_env) if max_steps_env else None
    max_steps_s_env = _env("PILSNER_T2_MAX_STEPS_SECONDS", "")
    max_steps_s = int(max_steps_s_env) if max_steps_s_env else None
    task_split = _env("PILSNER_T2_TASK_SPLIT", "base")
    sample_mode = _env("PILSNER_T2_TASK_SAMPLE", "first")
    seed = int(_env("PILSNER_SEED", "1"))
    seed_slot = int(_env("PILSNER_SEED_SLOT", str(seed)))
    benchbrew_seed = _env("PILSNER_BENCHBREW_SEED", "")
    benchbrew_dir = Path(_env("PILSNER_BENCHBREW_DIR",
                               str(REPO_ROOT.parent / "benchbrew")))
    out_dir = Path(_env("PILSNER_OUT", "outputs"))
    seed_source = "operator"
    if not benchbrew_seed and (benchbrew_dir / "domains" / "marketplace.py").exists():
        # chain rule: derive the eval seed from the previous verified
        # receipt's results hash — unknowable until that receipt exists,
        # not pickable post-hoc by anyone
        prev = None
        for p in sorted(out_dir.glob("report_tau2_*.json"), reverse=True):
            try:
                r = json.loads(p.read_text())
                if r.get("benchbrew") and r.get("verified") is True:
                    prev = r
                    break
            except (json.JSONDecodeError, OSError):
                continue
        if prev and prev.get("results_sha256"):
            benchbrew_seed = str(int(prev["results_sha256"][:8], 16) % 100000)
            seed_source = "chain"
            print(f"chain rule: eval seed {benchbrew_seed} derived from "
                  f"previous receipt {prev.get('seed')}")
        else:
            print("chain rule: no prior verified benchbrew receipt; "
                  "set PILSNER_BENCHBREW_SEED explicitly")
    reasoning = _env("PILSNER_REASONING", "unspecified")
    engine = _env("PILSNER_ENGINE", "unspecified")
    parallel = _env("PILSNER_PARALLEL", "unspecified")
    ctx = _env("PILSNER_CTX", "unspecified")
    engine_version = _env("PILSNER_ENGINE_VERSION", "unspecified")
    model_sha256 = _env("PILSNER_MODEL_SHA256", "unspecified")
    gpu_clock = _env("PILSNER_GPU_CLOCK", "unspecified")
    user_model = _env("PILSNER_USER_MODEL", "")
    user_base_url = _env("PILSNER_USER_BASE_URL", "")

    if not (t2_dir / "data" / "tau2").is_dir():
        print(f"error: tau2-bench not found at {t2_dir} (set PILSNER_T2_DIR)", file=__import__("sys").stderr)
        return 2

    env = dict(os.environ)
    env.setdefault("OPENAI_API_KEY", "pilsner-dummy-key")

    # Fresh-lane protocol: when PILSNER_BENCHBREW_SEED is set, regenerate +
    # re-emit the domain bundle from that PUBLIC seed before the battery, so
    # every eval runs a fresh task pool. The bundle hash lands in the receipt
    # and anyone can regenerate it (spec + seed) to verify the tasks.
    bb_prov = None
    if benchbrew_seed:
        # collusion guard: the user sim must be a FIXED model, not the
        # model being evaluated (otherwise the eval frames its own test)
        if not user_model or user_model.strip().lower() == model.strip().lower():
            print("error: benchbrew lanes require a FIXED user simulator "
                  "different from the agent model (set PILSNER_USER_MODEL / "
                  "PILSNER_USER_BASE_URL)", file=sys.stderr)
            return 7
        cmd = [sys.executable, "-m", "benchbrew", "--seed", benchbrew_seed,
               "--tasks", str(num_tasks), "--emit", str(t2_dir), "--quiet"]
        print("benchbrew:", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=benchbrew_dir, capture_output=True,
                              text=True)
        if proc.returncode != 0:
            print(f"error: benchbrew emit failed: {proc.stderr[-500:]}",
                  file=sys.stderr)
            return 5
        for line in proc.stdout.strip().splitlines():
            if line.startswith("benchbrew "):
                kv = dict(p.split("=", 1) for p in line.split()[1:])
                bb_prov = {
                    "spec_version": kv.get("version"),
                    "spec_sha256": kv.get("spec_sha256"),
                    "seed": kv.get("seed"),
                    "seed_source": seed_source,
                    "n_tasks": kv.get("tasks"),
                    "bundle_sha256": kv.get("bundle_sha256"),
                }
        print("benchbrew provenance:", bb_prov)

    started = time.monotonic()
    scores = []
    results_files = []
    sampled = {}
    for d in domains:
        cmd = [tau2_binary(t2_dir)] + build_command(
            model, base_url, d, num_tasks, num_trials, max_steps, task_split,
            user_model or None, user_base_url or None)
        if max_steps_s is not None:
            cmd += ["--max-steps-seconds", str(max_steps_s)]
        print(f"run ({d}):", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=t2_dir, env=env)
        if proc.returncode != 0:
            print(f"error: tau2 exited {proc.returncode} for domain {d}",
                  file=__import__("sys").stderr)
            return 3
        results_path = latest_results(t2_dir)
        if results_path is None:
            print(f"error: no results.json after domain {d}",
                  file=__import__("sys").stderr)
            return 4
        score = parse_results(results_path)
        ids, sampled_json = expected_task_ids(
            t2_dir, d, num_tasks, sample=sample_mode, seed=seed_slot)
        score = reconcile_missing(score, ids, num_trials)
        for pt in score["per_task"]:
            pt["domain"] = d
        scores.append(score)
        results_files.append(results_path)
        sampled[d] = sampled_json
    wall_clock_s = time.monotonic() - started

    # merge across domains: aggregate counts, per-task tagged by domain
    merged = merge_scores(scores)
    results_sha = hashlib.sha256(b"".join(p.read_bytes() for p in results_files)).hexdigest()
    receipt = {
        "schema": "pilsner-tau2-receipt/v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "arena": "pilsner",
        "instrument": "tau2-bench",
        "benchbrew": bb_prov,
        "domain": "+".join(domains),
        "task_split": task_split,
        "task_sample": sample_mode,
        "sampled_task_ids": sampled,
        "num_tasks": num_tasks,
        "num_trials": num_trials,
        "max_steps": max_steps,
        "max_steps_seconds": max_steps_s,
        "seed_slot": seed,
        "model": model,
        "base_url": base_url,
        "reasoning": reasoning,
        "engine": engine,
        "engine_version": engine_version,
        "model_sha256": model_sha256,
        "gpu_clock": gpu_clock,
        "parallel": parallel,
        "context": ctx,
        "wall_clock_s": round(wall_clock_s, 3),
        "success_rate": merged["success_rate"],
        "mean_reward": merged["mean_reward"],
        "n_success": merged["n_success"],
        "n_scored": merged["n_scored"],
        "per_task": merged["per_task"],
        "tau2_git_commit": merged["tau2_git_commit"],
        "agent_llm": merged["agent_llm"],
        "user_llm": merged.get("user_llm"),
        "results_file": ",".join(str(p.relative_to(t2_dir)) for p in results_files),
        "results_sha256": results_sha,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = out_dir / f"report_tau2_seed{seed}.json"
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"receipt: {receipt_path}")
    print(f"success_rate={merged['success_rate']:.3f} "
          f"({merged['n_success']}/{merged['n_scored']}) wall_clock={wall_clock_s:.1f}s")

    # verify the receipt against the recorded evidence before it can reach
    # the board: replay trajectories, regenerate the bundle, re-derive scores
    verify_py = t2_dir / ".venv" / "bin" / "python"
    verify_script = REPO_ROOT / "arena" / "verify_trajectory.py"
    if verify_py.exists() and verify_script.exists():
        proc = subprocess.run(
            [str(verify_py), str(verify_script), str(receipt_path),
             str(t2_dir), str(benchbrew_dir)],
            capture_output=True, text=True)
        try:
            verdict = json.loads(proc.stdout)
        except ValueError:
            verdict = {"verified": False, "failures": [
                f"verifier output unparseable: {proc.stdout[-200:]}{proc.stderr[-200:]}"]}
        receipt["verified"] = bool(verdict.get("verified"))
        receipt["verification"] = {
            "checks": verdict.get("checks", {}),
            "failures": verdict.get("failures", []),
        }
        with open(receipt_path, "w") as f:
            json.dump(receipt, f, indent=2)
        if not receipt["verified"]:
            print(f"verification FAILED — receipt not board-eligible:")
            for fl in receipt["verification"]["failures"][:5]:
                print(f"  - {fl}")
            return 6
        print(f"verified: trajectory replay re-derived the score "
              f"({verdict['checks']['replay']['ok']}/"
              f"{verdict['checks']['replay']['n']})")
    else:
        print("warning: verifier not found; receipt left unverified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
