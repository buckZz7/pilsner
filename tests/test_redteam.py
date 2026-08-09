"""Red-team exercise: simulated attacks against the live tooling.

Each test builds an adversarial artifact and asserts the defense
holds. If a test fails, the arena has a real hole — fix the tooling,
not the test. Run: python3 -m unittest tests.test_redteam -v
"""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from arena.audit import audit
from arena.challenge import battery_key, decide

# a legitimate receipt shape (from the real schema)
BASE = {
    "model": "qwen36-q2kxl", "base_url": "http://127.0.0.1:8000/v1",
    "reasoning": "off", "engine": "llama.cpp",
    "engine_version": "dd2c7c447", "model_sha256": "abc123",
    "gpu_clock": "2520", "parallel": 2, "context": 16384,
    "user_llm": "openai/qwen3-4b-q4km",
    "domain": ["airline", "retail"], "num_tasks": 50, "num_trials": 2,
    "max_steps": 50, "max_steps_seconds": 600,
    "success_rate": 0.62, "n_success": 31, "n_scored": 50,
    "wall_clock_s": 2380.0, "results_sha256": "deadbeef",
    "tau2_git_commit": "abc", "results_file": "data/sims/x/results.json",
    "per_task": [{"task_id": str(i), "reward": 1.0 if i < 31 else 0.0,
                  "domain": "airline"} for i in range(50)],
}


def _write(tmp: Path, name: str, d: dict) -> str:
    p = tmp / name
    p.write_text(json.dumps(d))
    return str(p)


class RedTeam(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_forged_score_inflation_caught(self):
        # attacker bumps success_rate + n_success but leaves per_task
        forged = copy.deepcopy(BASE)
        forged["success_rate"] = 0.95
        forged["n_success"] = 48
        problems, _ = audit(_write(self.dir, "forged.json", forged))
        self.assertTrue(any("success_rate" in p and "per_task" in p
                            for p in problems),
                        f"forged score not caught: {problems}")

    def test_inconsistent_receipt_caught(self):
        bad = copy.deepcopy(BASE)
        bad["per_task"] = [{"task_id": str(i), "reward": 1.0} for i in range(50)]
        bad["success_rate"] = 0.1  # says 0.1 but per_task is all wins
        problems, _ = audit(_write(self.dir, "inconsistent.json", bad))
        self.assertTrue(any("success_rate" in p for p in problems))

    def test_sha256_mismatch_caught(self):
        raw = self.dir / "results.json"
        raw.write_bytes(b"the real raw results")
        r = copy.deepcopy(BASE)
        r["results_sha256"] = hashlib.sha256(b"different data").hexdigest()
        r["results_file"] = str(raw)
        problems, _ = audit(_write(self.dir, "sha.json", r))
        self.assertTrue(any("sha256" in p for p in problems))

    def test_battery_mismatch_refused(self):
        king = copy.deepcopy(BASE)
        # challenger silently uses a weaker user sim
        cheat = copy.deepcopy(BASE)
        cheat["user_llm"] = "openai/bonsai-1bit"
        out = decide(king, cheat)
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("battery mismatch", out["reason"])

    def test_context_shrink_refused(self):
        king = copy.deepcopy(BASE)
        cheat = copy.deepcopy(BASE)
        cheat["context"] = 8192  # half the context, same claimed score
        self.assertNotEqual(battery_key(king), battery_key(cheat))
        self.assertEqual(decide(king, cheat)["verdict"], "refuse")

    def test_engine_build_swap_refused(self):
        king = copy.deepcopy(BASE)
        cheat = copy.deepcopy(BASE)
        cheat["engine_version"] = "7ba604f1c"  # different build
        self.assertEqual(decide(king, cheat)["verdict"], "refuse")

    def test_missing_provenance_caught(self):
        stripped = {k: v for k, v in BASE.items()
                    if k not in ("results_sha256", "tau2_git_commit",
                                 "engine_version")}
        problems, _ = audit(_write(self.dir, "stripped.json", stripped))
        self.assertTrue(any("missing field" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
