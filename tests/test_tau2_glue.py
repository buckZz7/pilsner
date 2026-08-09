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

    def test_fixed_user_simulator(self):
        cmd = build_command("mock", "http://a/v1", "airline", 5, 1, None, "base",
                            user_model="user4b", user_base_url="http://b/v1")
        i = cmd.index("--user-llm")
        self.assertEqual(cmd[i + 1], "openai/user4b")
        j = cmd.index("--user-llm-args")
        self.assertIn("http://b/v1", cmd[j + 1])
        self.assertNotIn("http://b/v1", cmd[cmd.index("--agent-llm-args") + 1])

    def test_default_user_is_agent(self):
        cmd = build_command("mock", "http://a/v1", "airline", 5, 1, None, "base")
        self.assertEqual(cmd[cmd.index("--user-llm") + 1], "openai/mock")

    def test_reconcile_missing_counts_no_result_as_fail(self):
        from arena.run_tau2 import reconcile_missing
        score = {
            "per_task": [{"task_id": "0", "reward": 1.0},
                         {"task_id": "1", "reward": 0.0}],
            "n_success": 1, "n_scored": 2,
            "success_rate": 0.5, "mean_reward": 0.5,
        }
        out = reconcile_missing(score, ["0", "1", "2", "3"])
        self.assertEqual(out["n_scored"], 4)
        self.assertEqual(out["n_success"], 1)
        self.assertEqual(out["success_rate"], 0.25)
        self.assertEqual(out["per_task"][2], {"task_id": "2", "reward": 0.0,
                                              "no_result": True})
        # no missing -> unchanged (fresh score; reconcile mutates in place)
        fresh = {"per_task": [{"task_id": "0", "reward": 1.0},
                              {"task_id": "1", "reward": 0.0}],
                 "n_success": 1, "n_scored": 2,
                 "success_rate": 0.5, "mean_reward": 0.5}
        out2 = reconcile_missing(fresh, ["0", "1"])
        self.assertEqual(out2["n_scored"], 2)
        self.assertEqual(out2["success_rate"], 0.5)

    def test_reconcile_missing_fills_trials(self):
        from arena.run_tau2 import reconcile_missing
        # 2 tasks x 2 trials; task "1" only appears once (one trial errored)
        score = {"per_task": [{"task_id": "0", "reward": 1.0},
                              {"task_id": "0", "reward": 1.0},
                              {"task_id": "1", "reward": 0.0}],
                 "n_success": 2, "n_scored": 3,
                 "success_rate": 2 / 3, "mean_reward": 2 / 3}
        out = reconcile_missing(score, ["0", "1"], num_trials=2)
        self.assertEqual(out["n_scored"], 4)          # 4 rows, not 3
        self.assertEqual(out["n_success"], 2)
        self.assertEqual(out["success_rate"], 0.5)    # 2/4, not 2/3
        self.assertEqual(out["per_task"][3], {"task_id": "1", "reward": 0.0,
                                              "no_result": True})

    def test_merge_scores_aggregates_domains(self):
        from arena.run_tau2 import merge_scores
        scores = [
            {"per_task": [{"task_id": "0", "reward": 1.0, "domain": "airline"},
                          {"task_id": "1", "reward": 0.0, "domain": "airline"}],
             "n_scored": 2, "n_success": 1, "tau2_git_commit": "a",
             "agent_llm": "m", "user_llm": "u"},
            {"per_task": [{"task_id": "0", "reward": 0.0, "domain": "retail"},
                          {"task_id": "1", "reward": 1.0, "domain": "retail"}],
             "n_scored": 2, "n_success": 1, "tau2_git_commit": "a",
             "agent_llm": "m", "user_llm": "u"},
        ]
        m = merge_scores(scores)
        self.assertEqual(m["n_scored"], 4)
        self.assertEqual(m["n_success"], 2)
        self.assertEqual(m["success_rate"], 0.5)
        self.assertEqual(len(m["per_task"]), 4)
        self.assertEqual({pt["domain"] for pt in m["per_task"]},
                         {"airline", "retail"})

    def test_tool_error_parsing(self):
        from arena.run_tau2 import _tool_call_count, _tool_error_count
        sim = {"messages": [
            {"role": "assistant", "content": "None",
             "tool_calls": "[{'name': 'search_flights'}, {'name': 'book_flight'}]"},
            {"role": "tool", "content": "ok", "error": "False"},
            {"role": "tool", "content": "bad args", "error": "True"},
            {"role": "assistant", "content": "hi", "tool_calls": "None"},
            {"role": "tool", "content": "err", "error": True},
        ]}
        self.assertEqual(_tool_call_count(sim), 2)
        self.assertEqual(_tool_error_count(sim), 2)

    def test_reconcile_missing_ignores_extra_ids(self):
        from arena.run_tau2 import reconcile_missing
        score = {"per_task": [{"task_id": "0", "reward": 1.0},
                              {"task_id": "7", "reward": 1.0}],
                 "n_success": 2, "n_scored": 2,
                 "success_rate": 1.0, "mean_reward": 1.0}
        out = reconcile_missing(score, ["0", "1", "2"])
        self.assertEqual(out["n_scored"], 4)  # 0,7 scored + 1,2 missing
        self.assertEqual(out["success_rate"], 0.5)


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
