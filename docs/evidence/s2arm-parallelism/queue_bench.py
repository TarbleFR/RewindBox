#!/usr/bin/env python3
"""Compile the worker, the queue submission entry and the NVN query bodies from a patched S2Arm engine tree."""
import argparse
import csv
import io
from pathlib import Path
import re
import os
import statistics
import subprocess
import tempfile

NAMES = (
    "GetImageHandle", "GetSeparateTextureHandle", "GetSeparateSamplerHandle", "GetTextureHandle",
    "GetTexelFetchHandle", "GetCommandHandleMemorySize", "GetUniformBufferHandle", "GetWindowOriginMode",
)


def extract(hle, name):
    match = re.search(r"^NVN(?:_NOPROTO)?\(nvnDevice" + name + r", [^\n]*?\) \{", hle, re.M)
    if not match:
        raise ValueError(name)
    level = 1
    for end in range(match.end(), len(hle)):
        level += (hle[end] == "{") - (hle[end] == "}")
        if not level:
            return hle[match.start():end + 1]
    raise ValueError(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Engine checkout after applying patches")
    parser.add_argument("--pairs", type=int, default=7)
    parser.add_argument("--out", type=Path, help="Optional paired observations CSV")
    args = parser.parse_args()
    if args.pairs < 2:
        parser.error("--pairs must be at least 2")
    engine = (args.source / "graphics/nvn/gfx/nvn").resolve()
    worker = (engine / "rb_replay_worker.inc").read_text()
    # Enable only the real enqueue backend on non-Darwin hosts. Use native
    # pthreads. Darwin-specific QoS/guest hints are outside this host experiment.
    apple = "#if defined(__APPLE__)"
    marker = worker.index("static int rb_replay_enqueue(")
    worker = worker[:marker] + worker[marker:].replace(apple, "#if 1", 1)
    worker = worker.replace(apple, "#if 0")
    hle = (engine / "hle_nvn.c").read_text()
    queries = "\n".join(extract(hle, name) for name in NAMES)
    # Fail closed if another entry starts bypassing the resource barrier.
    scalar = "RB_REPLAY_SCALAR_GUARD();"
    if hle.count(scalar) != 7 or any(
        scalar not in extract(hle, name) for name in NAMES[:-1]
    ) or scalar in extract(hle, NAMES[-1]):
        raise ValueError("unexpected scalar allowlist")
    guard_defs = [line for line in hle.splitlines() if line.startswith(("#define RB_REPLAY_GUARD(", "#define RB_REPLAY_SCALAR_GUARD("))]
    fixture = (Path(__file__).with_name("queue_bench.c")).read_text()
    generated = fixture.replace("/* SOURCE_WORKER */", worker).replace(
        "/* SOURCE_QUERIES */", "\n".join(guard_defs) + "\n" + queries)
    with tempfile.TemporaryDirectory() as tmp:
        src, exe = Path(tmp) / "queue.c", Path(tmp) / "bench"
        src.write_text(generated)
        subprocess.run([os.getenv("CC", "cc"), "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-pthread", "-I", str(engine / "include"), str(src), "-o", str(exe)], check=True)
        for mode in ("absent", "0", "invalid", "1", "off"):
            subprocess.run([str(exe), mode, "check"], check=True, timeout=20)
        observations = []
        for pair in range(args.pairs):
            for mode in (("0", "1") if pair % 2 == 0 else ("1", "0")):
                row = subprocess.check_output([str(exe), mode, "measure"], text=True, timeout=20).strip().split(",")
                observations.append([pair + 1, mode, *row])
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["pair", "scalar_enabled", "jobs", "elapsed_ns", "join_wait_ns", "p50_query_ns", "p95_query_ns", "p99_query_ns", "sequence_hash"])
    writer.writerows(observations)
    print(output.getvalue(), end="")
    if args.out:
        args.out.write_text(output.getvalue())
    by_mode = {m: [int(r[3]) / 1e6 for r in observations if r[1] == m] for m in ("0", "1")}
    assert len({r[-1] for r in observations}) == 1
    print("paired median elapsed ms, legacy / scalar", *(round(statistics.median(v), 3) for v in by_mode.values()))


if __name__ == "__main__":
    main()
