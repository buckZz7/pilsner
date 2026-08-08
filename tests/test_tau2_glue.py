"""Unit tests for the tau2 arena glue. No tau2 install, no GPU needed."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from arena.run_tau2 import build_command, parse_results, latest_results


class TestBuildCommand(unittest.TestCase):
    def test_prefixes_model_with_openai_provider(self):
        cmd = build_command("mock", "http://127.0.0.1:8999/v1", "airline", 5, 1, None, "base")
        self.assertIn("--agent-llm", cmd)
        self.assertEqual(cmd[cmd.index("--agent-llm") + 1], "openai/mock")

    def test_keeps_explicit_provider_prefix(self):
        cmd = build_command("sglang/foo", "http://x/v1", "retail", 5, 1, 4, "base")
        self.assertEqual(cmd[cmd.index("--agent-llm") + 1], "sglang/foo")

    def test_llm_args_carry_api_base(self):
        cmd = build_command("mock", "http://127.0.0.1:8999/v1", "airline", 5, 1, None, "base")
        i = cmd.index("--agent-llm-args")
        args = json.loads(cmd[i + 1])
        self.assertEqual(args["api_base"], "http://127.0.0.1:8999/v1")

    def test_max_steps_omitted_when_none(self):
        cmd = build_command("mock", "u", "airline", 5, 1, None, "base")
        self.assertNotIn("--max-steps", cmd)
        cmd2 = build_command("mock", "u", "airline", 5, 1, 4, "base")
        self.assertEqual(cmd2[cmd2.index("--max-steps") + 1], "4")


class TestParseResults(unittest.TestCase):
    def _results(self, rewards):
        sims = [{"task_id": str(i), "reward_info": {"reward": r}} for i, r in enumerate(rewards)]
        return {"info": {"seed": 300, "git_commit": "abc123",
                         "agent_info": {"llm": "openai/mock"}},
                "simulations": sims}

    def test_score_math(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "results.json"
            p.write_text(json.dumps(self._results([1.0, 1.0, 0.0, 0.5])))
            out = parse_results(p)
        self.assertEqual(out["n_success"], 2)
        self.assertEqual(out["n_scored"], 4)
        self.assertAlmostEqual(out["success_rate"], 0.5)
        self.assertAlmostEqual(out["mean_reward"], 0.625)
        self.assertEqual(out["seed"], 300)
        self.assertEqual(out["tau2_git_commit"], "abc123")

    def test_empty_simulations_do_not_crash(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "results.json"
            p.write_text(json.dumps({"info": {}, "simulations": []}))
            out = parse_results(p)
        self.assertEqual(out["success_rate"], 0.0)
        self.assertEqual(out["n_scored"], 0)

    def test_missing_reward_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "results.json"
            p.write_text(json.dumps({
                "info": {},
                "simulations": [{"task_id": "0", "reward_info": {"reward": 1.0}},
                                {"task_id": "1", "reward_info": {}}],
            }))
            out = parse_results(p)
        self.assertEqual(out["n_scored"], 1)


class TestLatestResults(unittest.TestCase):
    def test_picks_newest_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data/simulations/run1").mkdir(parents=True)
            (root / "data/simulations/run2").mkdir(parents=True)
            f1 = root / "data/simulations/run1/results.json"
            f2 = root / "data/simulations/run2/results.json"
            f1.write_text("{}")
            f2.write_text("{}")
            os.utime(f1, (1000, 1000))
            os.utime(f2, (2000, 2000))
            self.assertEqual(latest_results(root), f2)

    def test_none_when_no_runs(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(latest_results(Path(td)))


if __name__ == "__main__":
    unittest.main()
