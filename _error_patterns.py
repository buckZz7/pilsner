"""Tool-error pattern analysis: WHAT does a model fumble?

Clusters the tool error messages from raw results.json into patterns
(e.g. invalid date, unknown flight, bad passenger name) — the precise
mechanism of precision loss, and the target list for the
constrained-decoding fix path.

Usage: python3 _error_patterns.py <raw_results.json>...
"""
import json
import re
import sys
from collections import Counter


def error_messages(path: str) -> list[str]:
    d = json.load(open(path))
    out = []
    for s in d.get("simulations", []):
        for m in s.get("messages", []):
            if isinstance(m, dict) and m.get("role") == "tool":
                err = str(m.get("error", "False")).lower() in ("true", "1")
                if err:
                    out.append(str(m.get("content", ""))[:100])
    return out


PATTERNS = [
    ("date", r"date|day|invalid (departure|arrival)|format"),
    ("flight not found", r"flight.*not found|no flight|not exist"),
    ("unknown action", r"unknown action|not a valid action|no such tool"),
    ("reservation", r"reservation|booking|pnr|confirmation"),
    ("passenger", r"passenger|name"),
    ("policy/refund", r"refund|policy|fare|cancel"),
    ("missing arg", r"required|missing"),
    ("unparsable", r"json|parse|format"),
    ("other", r"."),
]


def main() -> int:
    for p in [a for a in sys.argv[1:] if a.endswith(".json")]:
        msgs = error_messages(p)
        c = Counter()
        samples = {}
        for m in msgs:
            low = m.lower()
            for label, rx in PATTERNS:
                if re.search(rx, low):
                    c[label] += 1
                    samples.setdefault(label, m)
                    break
        tot = sum(c.values())
        print(f"== {p} ({tot} tool errors) ==")
        for label, n in c.most_common():
            print(f"  {label:<18} {n:>4} ({n/tot:>5.0%})  e.g. {samples[label][:60]!r}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
