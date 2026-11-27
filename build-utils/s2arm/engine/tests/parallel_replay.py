#!/usr/bin/env python3
"""Targeted candidate matrix on the host Metal fixture. Run from the prepared engine tree."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from replay_sync_oracle import canonical_trace, check_events, sync_rows, verify_negative_controls


FLAGS = ("S2A_RB_REC_EARLY", "S2A_RB_REPLAY_WORKER", "S2A_RB_REPLAY_SCALAR_QUERIES", "S2A_RB_PARALLEL_TRACE")
ARMS = {"baseline": (0, 0, 0, 0), "early": (1, 0, 0, 0), "worker": (0, 1, 0, 0),
        "worker_scalar": (0, 1, 1, 0), "combined": (1, 1, 1, 0), "combined_trace": (1, 1, 1, 1),
        "baseline_trace": (0, 0, 0, 1)}
FRAMES = 3
ROUNDS = 4


def validate(out, fixed, rounds):
    baseline_trace = baseline_ops = baseline_sync = None
    results = {}
    diag = json.loads((out / "diagnostic-metrics.json").read_text())
    measured = json.loads((out / "metrics.json").read_text())
    for name, (_, worker, _, tracing) in ARMS.items():
        metrics = diag[name]
        cb_counts, pass_cuts = [], []
        for run in ("diagnostic", *range(rounds)):
            log = (out / f"{name}.{run}.log").read_text(errors="replace")
            wait, update, rows = sync_rows(log, FRAMES)
            run_metrics = metrics if run == "diagnostic" else measured[name][run]
            counts = [len(events) for _, events in rows]
            cuts = [cut for cut, _ in rows]
            if (round(sum(counts)/FRAMES, 1) != run_metrics["barriers_fences"] or
                    round(sum(cuts)/FRAMES, 1) != run_metrics["pass_cuts"]):
                raise ValueError(f"{name}.{run}: observed events differ from production totals")
            extras = [check_events(events, cut, wait, update, metrics["backend"], fixed) for cut, events in rows]
            sync = [[e for i,e in enumerate(events) if i not in extra and i-1 not in extra]
                    for (_, events), extra in zip(rows, extras)]
            ops = [s for s in log.splitlines() if s.startswith("OPSEQ ")]
            if len(ops) != FRAMES or any(not re.fullmatch(rf"OPSEQ {i} [1-9][0-9]* [0-9a-f]{{16}}", line)
                                         for i, line in enumerate(ops, 1)):
                raise ValueError(f"{name}.{run}: invalid opcode counts/digests")
            if baseline_sync is None:
                baseline_sync, baseline_ops = sync, ops
            if sync != baseline_sync or (fixed and ops != baseline_ops):
                raise ValueError(f"{name}.{run}: core sync sequence or fixed opcode stream differs")
            if run == "diagnostic":
                trace_hash = canonical_trace(out / f"{name}.diagnostic.trace", rows, extras)
                if baseline_trace is None:
                    baseline_trace = trace_hash
                if trace_hash != baseline_trace:
                    raise ValueError(f"{name}: ordered diagnostic stream differs")
            pass_cuts.append(cuts)
            if f"CANDIDATE worker_seen={worker} scalar_checks={FRAMES+1}" not in log.splitlines():
                raise ValueError(f"{name}.{run}: expected worker/scalar observation missing")
            events = [s for s in log.splitlines() if "[rb-parallel] v=1 " in s]
            begins = sum(" event=begin " in s for s in events)
            cbs = sum(" event=cb " in s for s in events)
            if (tracing and (begins != 1 or not cbs)) or (not tracing and events):
                raise ValueError(f"{name}.{run}: trace enable state differs; begins={begins}, cbs={cbs}")
            if tracing:
                frames = {int(re.search(r" frame=([0-9]+) ", s).group(1)) for s in events if " event=cb " in s}
                if not set(range(1, FRAMES + 1)).issubset(frames):
                    raise ValueError(f"{name}.{run}: missing measured frame IDs in callbacks: {frames}")
            if any(" status=error" in s for s in events):
                raise ValueError(f"{name}.{run}: GPU feedback error")
            cb_counts.append(cbs)
        results[name] = dict(backend=metrics["backend"], barriers_per_frame=metrics["barriers_fences"],
                             canonical_order_sha256=trace_hash, pass_cuts_by_run=pass_cuts,
                             draw_state_digest=metrics["draw_state_digest"], pixel_digest=metrics["pixel_digest"],
                             worker_seen=worker, scalar_checks_per_process=FRAMES+1, trace_cb_callbacks=cb_counts)
    (out / "parallel-validation.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    verify_negative_controls()
    failures = []
    for fixed in (False, True):
        target = out / "fixed-cuts" if fixed else out
        target.mkdir(parents=True, exist_ok=True)
        plan = target / "candidate-variants.txt"
        plan.write_text("".join(name+" "+" ".join(f"{k}={v}" for k, v in zip(FLAGS, values))+"\n"
                                for name, values in ARMS.items()))
        env = {**os.environ, "RBM_PARALLEL_REPLAY": "1", "S2A_RB_PARALLEL_FROM": "0"}
        env.pop("DM_NVN_CUT", None)
        if fixed:
            env["DM_NVN_CUT"] = "0"   # Test-only attribution control; normal matrix retains adaptive cuts.
        rounds = 3 if fixed else ROUNDS
        try:
            subprocess.run([sys.executable, here / "replay_compare.py", args.binary.resolve(), plan, target,
                            str(FRAMES), str(rounds), "--timeout", "90"], env=env, check=True)
            validate(target, fixed, rounds)
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            failures.append(f"{'fixed' if fixed else 'default'}: {error}")
            print(failures[-1], file=sys.stderr, flush=True)
    # Complement the single-queue replay with the existing signal/wait fixture, compiled once.
    xqueue = Path("build/tests/t_nvn_xqueue")
    subprocess.run(["make", "-j4", "-f", "Makefile", "-f", here / "host-tests.mk", xqueue], check=True)
    for mode in (0, 1):
        run = subprocess.run([xqueue.resolve()], env={**os.environ, "DM_NVN_ENC_THREAD": "1", "S2A_RB_XQ_RESUME": str(mode)},
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
        (out / f"xqueue-encode1-resume{mode}.log").write_bytes(run.stdout)
        run.check_returncode()
        summary = re.search(r"✓ t_nvn_xqueue：\d+ 项全过[^\n]*", run.stdout.decode(errors="replace"))
        if not summary:
            raise ValueError(f"xqueue {mode}: missing executed assertion summary")
        print(f"resume={mode} {summary.group()}", flush=True)
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
