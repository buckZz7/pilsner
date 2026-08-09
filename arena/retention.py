"""Retention analysis: rung score vs the Q8 floor, vs the vendor's claims.

The ladder's load-bearing numbers: how much capability survives each
compression level. Retention = rung_success_rate / floor_success_rate,
compared against the whitepaper's claimed retention on tau2 (their
numbers are vs FP16 on their stack; ours vs Q8 on ours — the disclosure
line says it).

Usage: python3 -m arena.retention <floor_receipt.json> <rung_receipt.json>...
"""
from __future__ import annotations

import json
import sys

from .ladder_report import wilson_ci

# PrismML whitepaper Appendix C, tau2-Bench row (thinking on, H100).
THEIR_TAU2 = {
    "bonsai-1bit": ("Bonsai 1-bit", 61.34, 82.90),
    "bonsai-ternary": ("Bonsai Ternary", 73.61, 82.90),
    "qwen36-iq2xxs": ("Qwen IQ2_XXS", 74.58, 82.90),
    "qwen36-q2kxl": ("Qwen Q2_K_XL", None, 82.90),
    "qwen3-4b": ("Qwen3-4B (dense)", None, None),
    "qwen36-q8": ("Qwen3.6 Q8 (floor)", 82.27, 82.90),
}


def main() -> int:
    paths = [p for p in sys.argv[1:] if p.endswith(".json")]
    if len(paths) < 2:
        print("usage: retention <floor> <rung>...")
        return 1
    floor = json.load(open(paths[0]))
    fsr = floor.get("success_rate", 0.0)
    print(f"floor: {floor.get('model')} = {fsr:.3f} "
          f"({floor.get('n_success')}/{floor.get('n_scored')})\n")
    print(f"{'entry':<16} {'ours':>7} {'CI95':>12} {'retention':>10} "
          f"{'their tau2':>11} {'their ret.':>10}")
    for p in paths[1:]:
        r = json.load(open(p))
        model = r.get("model", "?")
        ours = r.get("success_rate", 0.0)
        lo, hi = wilson_ci(ours, r.get("n_scored", 0))
        name, theirs, base = THEIR_TAU2.get(model, (model, None, None))
        ret = ours / fsr if fsr else 0.0
        their_ret = (theirs / base) if (theirs and base) else None
        theirs_s = f"{theirs:.2f}" if theirs is not None else "-"
        their_ret_s = f"{their_ret:.0%}" if their_ret is not None else "-"
        print(f"{model:<16} {ours:>7.3f} [{lo:>5.3f}-{hi:>5.3f}] "
              f"{ret:>9.0%} {theirs_s:>11} {their_ret_s:>10}")
    print("\ndisclosure: ours = thinking off / 5090 / llama.cpp / 16k ctx, "
          "retention vs Q8; theirs = thinking on / H100 / vLLM, retention vs FP16.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
