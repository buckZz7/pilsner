"""Tests for the challenge referee (the >2% + battery-match rule)."""
import unittest

from arena.challenge import decide


def receipt(model, score, n=200, wall=100.0, domain="airline", tasks=50,
            trials=4, reasoning="off", engine="llama.cpp", split="base"):
    return {
        "model": model, "success_rate": score, "n_scored": n,
        "n_success": int(score * n), "mean_reward": score,
        "wall_clock_s": wall, "domain": domain, "num_tasks": tasks,
        "num_trials": trials, "task_split": split,
        "reasoning": reasoning, "engine": engine,
    }


class TestDecide(unittest.TestCase):
    def test_win_when_beat_by_more_than_2(self):
        r = decide(receipt("king", 0.80), receipt("chal", 0.85))
        self.assertEqual(r["verdict"], "win")

    def test_loss_within_2(self):
        r = decide(receipt("king", 0.80), receipt("chal", 0.81))
        self.assertEqual(r["verdict"], "loss")

    def test_loss_when_worse(self):
        r = decide(receipt("king", 0.80), receipt("chal", 0.70))
        self.assertEqual(r["verdict"], "loss")

    def test_exact_2_is_loss(self):
        # >2% means strictly more than 2 points
        r = decide(receipt("king", 0.80), receipt("chal", 0.82))
        self.assertEqual(r["verdict"], "loss")

    def test_refuse_on_battery_mismatch(self):
        r = decide(receipt("king", 0.80, trials=4), receipt("chal", 0.85, trials=1))
        self.assertEqual(r["verdict"], "refuse")
        self.assertIn("battery", r["reason"])

    def test_refuse_on_reasoning_mismatch(self):
        r = decide(receipt("king", 0.80, reasoning="off"),
                   receipt("chal", 0.85, reasoning="auto"))
        self.assertEqual(r["verdict"], "refuse")

    def test_refuse_on_engine_mismatch(self):
        r = decide(receipt("king", 0.80, engine="llama.cpp"),
                   receipt("chal", 0.85, engine="vllm"))
        self.assertEqual(r["verdict"], "refuse")

    def test_reports_gap_and_se(self):
        r = decide(receipt("king", 0.80, n=200), receipt("chal", 0.85, n=200))
        self.assertAlmostEqual(r["gap"], 0.05)
        self.assertGreater(r["diff_se"], 0.0)


if __name__ == "__main__":
    unittest.main()
