"""Tests for the board (leaderboard ranking + king designation)."""
import unittest

from arena.board import build_board
from arena.ladder_report import wilson_ci


def receipt(model, score, wall=100.0, n=200):
    return {
        "model": model, "success_rate": score, "n_success": int(score * n),
        "n_scored": n, "mean_reward": score, "wall_clock_s": wall,
        "reasoning": "off", "engine": "llama.cpp", "domain": "airline",
        "num_trials": 1, "results_file": f"{model}.json",
        "tau2_git_commit": "abc", "results_sha256": "x", "timestamp": "t",
    }


class TestBoard(unittest.TestCase):
    def test_ranks_by_score(self):
        b = build_board([receipt("slow", 0.80, wall=500),
                         receipt("fast", 0.85, wall=100)])
        self.assertEqual([e["model"] for e in b["entries"]], ["fast", "slow"])
        self.assertEqual(b["king"], "fast")

    def test_tiebreak_speed(self):
        b = build_board([receipt("slow", 0.80, wall=500),
                         receipt("fast", 0.80, wall=100)])
        self.assertEqual(b["king"], "fast")

    def test_empty_board(self):
        b = build_board([])
        self.assertIsNone(b["king"])
        self.assertEqual(b["entries"], [])

    def test_ci_attached(self):
        b = build_board([receipt("m", 0.80, n=200)])
        lo, hi = wilson_ci(0.80, 200)
        self.assertAlmostEqual(b["entries"][0]["ci95"][0], lo, places=4)
        self.assertAlmostEqual(b["entries"][0]["ci95"][1], hi, places=4)


if __name__ == "__main__":
    unittest.main()
