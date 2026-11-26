"""Summarize the 64 within-pair CPU time ratios in each synthetic scenario."""
import math
from pathlib import Path
from statistics import median
import sys

MODES = ("UBOLEN", "SBSZ", "UBOLEN cache stable", "UBOLEN cache modifié", "cap seule", "restauration", "recyclage", "stable non nul")


def report(path):
    rows = {}
    for line in path.read_text().splitlines():
        pair, mode, variant, milliseconds = line.split()
        key = (int(pair), int(mode), int(variant))
        if key in rows:
            raise ValueError(f"Ligne en double {key}")
        rows[key] = float(milliseconds)
    # For n=64, [X_(24), X_(41)] covers the population median with 96.7%
    # probability for iid continuous paired differences under the sign test.
    n = 64
    coverage = 1 - 2 * sum(math.comb(n, i) for i in range(24)) / 2**n
    print(path.name, f"intervalle nominal {100*coverage:.2f}%")
    for mode, name in enumerate(MODES):
        pairs = [(rows[i, mode, 0], rows[i, mode, 1]) for i in range(1, n + 1)]
        changes = sorted(100 * (candidate / base - 1) for base, candidate in pairs)
        print(name, f"{median(a for a, _ in pairs):.3f} -> {median(b for _, b in pairs):.3f} ms",
              f"{median(changes):+.2f}% [{changes[23]:+.2f}%, {changes[40]:+.2f}%]")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        report(Path(arg))
