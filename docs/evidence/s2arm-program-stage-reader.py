"""Count shader changes between consecutive direct draws in complete passes of one frames.txt."""

import argparse
from collections import Counter, defaultdict
from itertools import pairwise
import json
from pathlib import Path


def summarize(capture):
    pass_sizes = {}
    draws = defaultdict(list)
    with capture.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.startswith(("P ", "D ")):
                continue
            record = line.split()
            key = int(record[1]), int(record[2])
            if record[0] == "P":
                if key in pass_sizes:
                    raise ValueError(f"Repeated frame/pass {key} within capture")
                pass_sizes[key] = int(record[5])
            else:
                draws[key].append((int(record[3]), int(record[4], 16), int(record[5], 16)))

    counts = Counter()
    for key, sequence in draws.items():
        if len(sequence) != pass_sizes.get(key):
            continue
        for (kind_a, vs_a, fs_a), (kind_b, vs_b, fs_b) in pairwise(sequence):
            if kind_a or kind_b or not all((vs_a, vs_b, fs_a, fs_b)):
                continue
            counts[vs_a == vs_b, fs_a == fs_b] += 1

    return {
        "direct_pairs": counts.total(),
        "both_same": counts[True, True],
        "vertex_same_only": counts[True, False],
        "fragment_same_only": counts[False, True],
        "both_changed": counts[False, False],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="one private frames.txt")
    print(json.dumps(summarize(parser.parse_args().capture), indent=2))
