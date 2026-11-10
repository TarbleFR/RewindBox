#!/usr/bin/env python3
"""Private 587 from the 586 baseline: the delivery checks of what 587 changes.

The baseline (the delivered 586, rewind587_baseline.py) is not proved again:
no earlier recipe, engine, Core or host run, no receipt of a feature unchanged
since 586 (maintainer rule of 28 October 2026). What this module checks:

* --contract: the checkout is the pinned 587 tree, each delta file the blob of
  the commit that validated it;
* --retain-checks: the 587 engine run and the 591 Core receipt with its run;
* --wait-for-components: the 591 Core run completed with every Core step;
* --component-runs: the 587 engine run and the iPhone host run whose proofs
  the build packages (the one 586 packaged);
* --download-components: the 587 engine and the iPhone host proofs, by
  artifact ID and digest;
* --engine-evidence: the downloaded engine against the pinned engine inputs
  (rewind587_engine.engine_evidence(): the 586 engine checks, then the 587
  adaptations);
* --rpc-core-inputs SOURCE -- PATHS: the Core pin guard of the 591 Core inputs
  (rpcs3cell591_delivery_core.validate_rpc_core_pin), before any contract.

The engine and host modules load the 586 recipe's checks; the Core guard and
the contract do not need them.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for path in ('.github/diagnostics', 'build-utils', 'build-utils/melonx', 'packages/dolphin_internal_bridge/ci'):
    sys.path.insert(0, str(ROOT / path))
import rewind587_baseline as tree
import rpcs3cell591_delivery_core as core591

BUILD = tree.BUILD


def engine():
    import rewind587_engine
    return rewind587_engine


def contract():
    return tree.verify()


def host_run():
    """The iPhone host run whose checks the build packages (dist/melonx-host), as for 586."""
    d586 = engine().d586
    return d586.previous.completed(d586.HOST_RUN, d586.HOST_SOURCE, d586.HOST_STEPS558)


def retain_checks():
    out = ROOT / 'build/delivery'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'rewind587-engine-run.json').write_text(json.dumps(engine().engine_run(), indent=2) + '\n')
    (out / 'rpcs3-cell591-core.json').write_text(json.dumps(dict(core591.core_receipt(), run=core591.core_run()), indent=2) + '\n')
    print('Bound the 587 engine run and the 591 Core receipt to the pinned tree.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('core_paths', nargs='*')
    for flag in ('--contract', '--retain-checks', '--wait-for-components', '--component-runs',
                 '--download-components', '--engine-evidence'):
        parser.add_argument(flag, action='store_true')
    parser.add_argument('--output', default='build/delivery/baseline587.json')
    args = parser.parse_args()
    if args.rpc_core_inputs:
        core591.validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths)
        return
    report = dict(build=int(BUILD), contract=contract())
    if args.retain_checks:
        retain_checks()
    if args.wait_for_components:
        report['rpcCore'] = core591.core_run()
    if args.component_runs:
        report['engine'] = engine().engine_run()
        report['host'] = host_run()
    if args.download_components:
        d586 = engine().d586
        report['downloads'] = [d586.d549.download(engine().MELONX_ARTIFACT, 'dist/melonx'),
                               d586.d549.download(d586.HOST_ARTIFACT, 'dist/melonx-host')]
    if args.engine_evidence:
        report['engineEvidence'] = engine().engine_evidence()
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
