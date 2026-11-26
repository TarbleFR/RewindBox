"""Hold the last MKW session out and compare bounded rankings of previously slow render keys."""
import argparse
from collections import Counter
import re
from zipfile import ZipFile


ROOT = "engine/0400C3F00006E000/"
EVENT = re.compile(r"cup pipeline first draw frame=\d+ key=([0-9a-f]{40}) [^\n]*?kind=render [^\n]*?wait_ns=(\d+) source=demand")
RECIPE = re.compile(r"RewindBox reference recipe frame \d+ ([0-9a-f]{40}) R\t")
THRESHOLD_NS = 5_000_000


def measured(log):
    result = {}
    for key, duration in EVENT.findall(log):
        ns = int(duration)
        if ns >= THRESHOLD_NS:
            result[key] = max(ns, result.get(key, 0))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    args = parser.parse_args()
    sessions = Counter()
    cumulative = Counter()
    recency = {}
    serialized = set()
    with ZipFile(args.archive) as archive:
        prior = sorted(name for name in archive.namelist()
                       if name.startswith(ROOT + "host-") and name.endswith(".log"))
        for name in prior:
            history = archive.read(name).decode(errors="replace")
            serialized.update(RECIPE.findall(history))
            rows = measured(history)
            for key, ns in rows.items():
                sessions[key] += 1
                cumulative[key] += ns
                recency.pop(key, None)
                recency[key] = None
        latest = archive.read(ROOT + "host.log").decode(errors="replace")
    target = measured(latest)
    ranked = sorted(sessions, key=lambda k: (-sessions[k], -cumulative[k], k))
    by_cost = sorted(sessions, key=lambda k: (-cumulative[k], -sessions[k], k))
    print("prior logs / distinct prior keys", len(prior), len(sessions))
    print("held-out distinct slow keys / sum of maximum waits (ms)", len(target), round(sum(target.values()) / 1e6, 1))
    eligible = target.keys() & serialized
    print("held-out slow keys with any prior serialized recipe / associated waits (ms)",
          len(eligible), round(sum(target[k] for k in eligible) / 1e6, 1))
    for size in (32, 64, 256):
        for name, keys in (("recent", list(reversed(recency))), ("frequency", ranked), ("cost", by_cost)):
            hits = target.keys() & set(keys[:size])
            print(size, name, "overlap", len(hits), "associated waits (ms)",
                  round(sum(target[k] for k in hits) / 1e6, 1))


if __name__ == "__main__":
    main()
