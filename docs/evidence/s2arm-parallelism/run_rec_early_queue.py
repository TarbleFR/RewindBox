#!/usr/bin/env python3
"""Build the actual nvn_rec.h queue as C and compare synthetic pthread workloads."""
import argparse
import csv
import itertools
import math
import os
from pathlib import Path
import statistics
import subprocess
import tempfile


def section(source, start, end):
    first = source.index(start)
    return source[first:source.index(end, first)]


def build(root, dest, sanitize):
    folder = root / "graphics/nvn/gfx/nvn"
    header = (folder / "nvn_rec.h").read_text()
    types = section(header, "typedef struct { uint32_t op, nobj;", "// On by default")
    state = section(header, "static pthread_mutex_t g_rb_mu", "static inline uint64_t rec_obj")
    queue = section(header, "static void *rec_thread(", "static __attribute__((noreturn)) void rec_missing")
    session = section((folder / "nvn_session.inc").read_text(), "    while (g_rb_free)", "    g_rx_cb =")
    driver = Path(__file__).with_name("rec_early_queue.c").read_text()
    driver = driver.replace("/* INSERT_TYPES */", types + state)
    driver = driver.replace("/* INSERT_QUEUE */", queue.replace("@autoreleasepool", ""))
    driver = driver.replace("// INSERT_SESSION", "pthread_mutex_lock(&g_rb_mu);\n" + session + "    pthread_mutex_unlock(&g_rb_mu);")
    dest.with_suffix(".c").write_text(driver)
    flags = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g"] if sanitize else []
    subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-Wno-misleading-indentation", "-pthread", *flags, str(dest.with_suffix(".c")), "-o", str(dest)], check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("baseline", type=Path, help="baseline engine tree")
    p.add_argument("candidate", type=Path, help="patched engine tree")
    p.add_argument("--pairs", type=int, default=12)
    p.add_argument("--frames", type=int, default=36)
    p.add_argument("--csv", type=Path)
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    if a.sanitize and not a.check_only: p.error("use --sanitize with --check-only")
    if a.pairs < 1 or a.frames < 1: p.error("positive pairs and frames required")
    with tempfile.TemporaryDirectory() as scratch:
        phases = [("original", Path(scratch)/"original", False, False), ("off", Path(scratch)/"candidate", False, True),
                  ("early", Path(scratch)/"candidate", True, True)]
        build(a.baseline, phases[0][1], a.sanitize)
        build(a.candidate, phases[1][1], a.sanitize)
        def run(case, args, *, default=False):
            name, binary, enabled, patched = case
            env = {**os.environ, "S2A_RB_REC_EARLY": "1" if enabled else "0"}
            if default:
                del env["S2A_RB_REC_EARLY"]
            result = subprocess.run([str(binary), *map(str, args)], env=env, text=True,
                                    timeout=30, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise RuntimeError(f"{name} {args} failed ({result.returncode}): {result.stderr}")
            return result
        for case in phases:
            print(case[0], run(case, ["test", int(case[2]), int(case[3])]).stdout.strip(), flush=True)
        print("default", run(phases[1], ["test", 0, 1], default=True).stdout.strip(), flush=True)
        if a.check_only: return
        loads = {"short": (32,240,240), "balanced": (240,240,240), "long": (1024,240,240),
                 "producer": (480,480,48), "encoder": (480,48,480)}
        table = []
        digests = {}
        for round_id in range(a.pairs):
            # Rotate workloads and permute the three settings, so neither always goes first.
            load_names = list(loads)
            start = round_id % len(loads)
            order = list(itertools.permutations(phases))[round_id % 6]
            for name in load_names[start:] + load_names[:start]:
                for case in order:
                    res = run(case, ["bench", a.frames, *loads[name]])
                    assert digests.setdefault(name, res.stderr) == res.stderr
                    rows = list(csv.reader(res.stdout.splitlines()))
                    assert len(rows) == a.frames
                    for row in rows:
                        table.append((round_id, name, case[0], *map(int,row)))
        if a.csv:
            with a.csv.open("w", newline="") as handle:
                out = csv.writer(handle)
                out.writerow(["round","load","variant","frame","wall_ns","drain_ns","first_exec_ns"])
                out.writerows(table)
        for name in loads:
            print(name, "median/p95 us (wall, drain, start of first encode)")
            for case in phases:
                group = [r for r in table if r[1:3] == (name,case[0])]
                def median_p95(column):
                    values = sorted(r[column] / 1000 for r in group)
                    position = (len(values) - 1) * .95
                    fraction = position % 1
                    tail = values[int(position)] * (1 - fraction) + values[math.ceil(position)] * fraction
                    return f"{statistics.median(values):.1f}/{tail:.1f}"
                print(case[0], *(median_p95(col) for col in (4, 5, 6)))
            for base in ("original","off"):
                deltas = []
                for k in range(a.pairs):
                    def median(mode):
                        return statistics.median(r[4] for r in table if r[:3] == (k,name,mode))
                    deltas.append(100*(median("early")/median(base)-1))
                print("early vs", base, "paired round median wall delta %.1f%%; %d/%d faster"
                      % (statistics.median(deltas), sum(d<0 for d in deltas),len(deltas)))

if __name__ == "__main__":
    main()
