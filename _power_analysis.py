"""Power analysis for the Pilsner >2% king rule.

Question: with a fixed battery of N task-trials per model, how reliably can
the arena detect a challenger that is TRULY better than the king by some
margin, when the rule requires measured score > king score + 2%?

Model: binomial success rates (p ~ 0.8 on tau2 airline), normal approx.
King true p0 = 0.80. Challenger true p1 = p0 + true_margin.
Measured diff D ~ N(true_margin, SD), SD = sqrt(p0(1-p0)/N + p1(1-p1)/N).
Rule passes when D >= 0.02. Power = P(pass) for each N and true margin.
"""
import math

P0 = 0.80
THRESHOLD = 0.02

def sd(n, p1):
    return math.sqrt(P0 * (1 - P0) / n + p1 * (1 - p1) / n)

def power(n, true_margin):
    p1 = P0 + true_margin
    s = sd(n, p1)
    # P(D >= THRESHOLD) with D ~ N(true_margin, s)
    z = (THRESHOLD - true_margin) / s
    return 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))

print("N (task-trials) | 2% true | 3% true | 5% true | 8% true | 95% CI width")
print("-" * 78)
for n in (50, 100, 200, 400, 1000):
    ci = 1.96 * sd(n, P0)
    row = f"{n:>14} |"
    for m in (0.02, 0.03, 0.05, 0.08):
        row += f" {power(n, m):>6.0%} |"
    print(f"{row}   +/-{ci:.1%}")
print()
print("Rule passes if measured(challenger) >= measured(king) + 2%.")
print("Power = chance the rule correctly crowns a genuinely-better challenger.")
