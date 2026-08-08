"""Bonsai comparison: our independent number vs their published claims.

Takes our receipt for a Bonsai rung (or any rung) and lays it next to
PrismML's whitepaper tau2 numbers (primary source, Appendix C), with the
operating-point disclosure baked in so nobody overclaims comparability.

Usage:
  python3 -m arena.bonsai_compare outputs/report_tau2_seed2.json \
      [outputs/report_tau2_seed4.json ...]  # extra receipts = retention refs

Outputs the table + an honest verdict. The number is NEVER "Bonsai scores
X" without the three disclosures.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .ladder_report import wilson_ci

# Primary source: PrismML whitepaper Appendix C, tau2-Bench row (8 models),
# thinking mode ON, H100, EvalScope + vLLM. Extracted 2026-08-08.
THEIR_TAU2 = {
    "Qwen3.6-27B FP16": 82.90,
    "Qwen3.6-27B Q8-class": 82.27,
    "Qwen3.6-27B IQ2_XXS": 74.58,
    "Qwen3.6-27B (mid)": 72.80,
    "Qwen3.6-27B (mid2)": 68.20,
    "Gemma-4-31B Q2_K_XL": 53.20,
    "Bonsai Ternary 27B": 73.61,
    "Bonsai 1-bit 27B": 61.34,
}

DISCLOSURES = (
    "theirs: thinking ON | H100 | EvalScope+vLLM | gpt-4.1 user sim | ~100k+ ctx",
    "ours:  thinking OFF | 5090 | llama.cpp | same-model user sim (ladder) | 16k ctx",
)

BONSAI_MODELS = {"bonsai-1bit": "Bonsai 1-bit 27B",
                 "bonsai-ternary": "Bonsai Ternary 27B",
                 "qwen36-iq2xxs": "Qwen3.6-27B IQ2_XXS",
                 "qwen36-q2kxl": "Qwen3.6-27B Q2_K_XL",
                 "qwen36-q8": "Qwen3.6-27B Q8-class"}


def main() -> int:
    paths = [p for p in sys.argv[1:] if p.endswith(".json")]
    if not paths:
        print("usage: bonsai_compare <our receipt> [more receipts]")
        return 1
    receipts = [json.load(open(p)) for p in paths]
    print("== Bonsai tau2 comparison (independent vs primary source) ==\n")
    print(f"disclosure — {DISCLOSURES[0]}")
    print(f"disclosure — {DISCLOSURES[1]}\n")
    print(f"{'entry':<18} {'ours':>7} {'CI95':>12} {'theirs':>8} {'delta':>8}")
    for r in receipts:
        model = r.get("model") or "?"
        ours = r.get("success_rate", 0.0)
        lo, hi = wilson_ci(ours, r.get("n_scored", 0))
        theirs = THEIR_TAU2.get(BONSAI_MODELS.get(model, ""))
        delta = (ours - theirs / 100) if theirs is not None else None
        delta_s = f"{delta:+.3f}" if delta is not None else "n/a"
        theirs_s = f"{theirs:.2f}" if theirs is not None else "n/a"
        print(f"{model:<18} {ours:>7.3f} [{lo:>5.3f}-{hi:>5.3f}] "
              f"{theirs_s:>8} {delta_s:>8}")
        if r.get("user_llm"):
            print(f"  user sim: {r['user_llm']} | reasoning: {r.get('reasoning')} "
                  f"| engine: {r.get('engine')} | n_scored: {r.get('n_scored')}")

    # Thesis test: does our 1-bit beat our 2-bit? (the whitepaper's own
    # table says no: 61.34 < 74.58). Only when both receipts are present.
    by_model = {r.get("model"): r for r in receipts}
    one = by_model.get("bonsai-1bit")
    two = by_model.get("qwen36-iq2xxs") or by_model.get("qwen36-q2kxl")
    if one and two:
        o, t = one["success_rate"], two["success_rate"]
        print(f"\nthesis test (ours): 1-bit {o:.3f} vs 2-bit {t:.3f} "
              f"-> {'2-bit WINS' if t > o else '1-bit WINS'}")
        print("caveat: ladder survey (1 trial, same-model user sim) — "
              "directional; scored battery confirms.")
    elif one:
        print("\nthesis test: waiting for the 2-bit rung receipt.")
    print("\nhonest read: deltas mix operating point (thinking on/off), "
          "hardware, engine, and user sim. Direction is informative; "
          "magnitude is not a claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
