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
  PILSNER_T2_MAX_STEPS  cap on conversation steps per trial (default: tau2's own)
  PILSNER_T2_TASK_SPLIT task split (default: base)
  PILSNER_SEED          seed slot (default: 1; recorded in the receipt)
  PILSNER_OUT           output dir (default: outputs)
  PILSNER_REASONING     thinking operating point served by the engine:
                        on|off|auto (default: unspecified; the scored
                        operating point of the arena is off)
  PILSNER_ENGINE        serving engine (e.g. llama.cpp, vllm; default unspecified)
  PILSNER_PARALLEL      server concurrency slots (default: unspecified;
                        speed comparisons require same parallel)
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


def expected_task_ids(t2_dir: Path, domain: str, num_tasks: int) -> list[str]:
    """The first num_tasks task ids of the domain's base split."""
    p = t2_dir / "data" / "tau2" / "domains" / domain / "tasks.json"
    if p.exists():
        tasks = json.load(open(p))
        return [str(t.get("id")) for t in tasks[:num_tasks]]
    return [str(i) for i in range(num_tasks)]


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
    num_tasks = int(_env("PILSNER_T2_TASKS", "10"))
    num_trials = int(_env("PILSNER_T2_TRIALS", "1"))
    max_steps_env = _env("PILSNER_T2_MAX_STEPS", "")
    max_steps = int(max_steps_env) if max_steps_env else None
    task_split = _env("PILSNER_T2_TASK_SPLIT", "base")
    seed = int(_env("PILSNER_SEED", "1"))
    out_dir = Path(_env("PILSNER_OUT", "outputs"))
    reasoning = _env("PILSNER_REASONING", "unspecified")
    engine = _env("PILSNER_ENGINE", "unspecified")
    parallel = _env("PILSNER_PARALLEL", "unspecified")
    ctx = _env("PILSNER_CTX", "unspecified")
    user_model = _env("PILSNER_USER_MODEL", "")
    user_base_url = _env("PILSNER_USER_BASE_URL", "")

    if not (t2_dir / "data" / "tau2").is_dir():
        print(f"error: tau2-bench not found at {t2_dir} (set PILSNER_T2_DIR)", file=__import__("sys").stderr)
        return 2

    cmd = [tau2_binary(t2_dir)] + build_command(
        model, base_url, domain, num_tasks, num_trials, max_steps, task_split,
        user_model or None, user_base_url or None)
    print("run:", " ".join(cmd))
    env = dict(os.environ)
    env.setdefault("OPENAI_API_KEY", "pilsner-dummy-key")

    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=t2_dir, env=env)
    wall_clock_s = time.monotonic() - started
    if proc.returncode != 0:
        print(f"error: tau2 exited {proc.returncode}", file=__import__("sys").stderr)
        return 3

    results_path = latest_results(t2_dir)
    if results_path is None:
        print("error: no results.json found under data/tau2/simulations/", file=__import__("sys").stderr)
        return 4

    score = parse_results(results_path)
    score = reconcile_missing(score, expected_task_ids(t2_dir, domain, num_tasks),
                              num_trials)
    results_sha = hashlib.sha256(results_path.read_bytes()).hexdigest()
    receipt = {
        "schema": "pilsner-tau2-receipt/v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "arena": "pilsner",
        "instrument": "tau2-bench",
        "domain": domain,
        "task_split": task_split,
        "num_tasks": num_tasks,
        "num_trials": num_trials,
        "max_steps": max_steps,
        "seed_slot": seed,
        "model": model,
        "base_url": base_url,
        "reasoning": reasoning,
        "engine": engine,
        "parallel": parallel,
        "context": ctx,
        "wall_clock_s": round(wall_clock_s, 3),
        "success_rate": score["success_rate"],
        "mean_reward": score["mean_reward"],
        "n_success": score["n_success"],
        "n_scored": score["n_scored"],
        "per_task": score["per_task"],
        "tau2_git_commit": score["tau2_git_commit"],
        "agent_llm": score["agent_llm"],
        "user_llm": score.get("user_llm"),
        "results_file": str(results_path.relative_to(t2_dir)),
        "results_sha256": results_sha,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = out_dir / f"report_tau2_seed{seed}.json"
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"receipt: {receipt_path}")
    print(f"success_rate={score['success_rate']:.3f} "
          f"({score['n_success']}/{score['n_scored']}) wall_clock={wall_clock_s:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
