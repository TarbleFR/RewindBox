#!/usr/bin/env python3
"""Private 586 from the 585 baseline: the delivery checks of what 586 changes.

The baseline (the delivered 585, rewind586_baseline.py) is not proved again:
no nested recipe views, no earlier engine, Core or host run, no receipt of a
feature unchanged since 585 (maintainer rule of 28 October 2026). What this
module checks:

* --contract: the checkout is the pinned 586 tree, each delta file the blob of
  the commit that validated it;
* --retain-checks: the 586 engine run and the 587 Core receipt with its run;
* --wait-for-components: the 587 Core run completed with every Core step;
* --component-runs: the 586 engine run and the iPhone host run whose proofs
  the build packages;
* --download-components: the 586 engine and the iPhone host proofs, by
  artifact ID and digest;
* --engine-evidence: the downloaded engine against the pinned engine inputs
  (rewind586_delivery.engine_evidence(), which reads only the 586 engine);
* --rpc-core-inputs SOURCE -- PATHS: the Core pin guard of the 587 Core
  inputs (rewind586_delivery.validate_rpc_core_pin), before any contract.

The engine, Core and host constants and functions are those of the 586 recipe
(rewind586_delivery.py), whose source contract and nested views are not run.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for path in ('.github/diagnostics', 'build-utils', 'build-utils/melonx', 'packages/dolphin_internal_bridge/ci'):
    sys.path.insert(0, str(ROOT / path))
import rewind586_baseline as tree
import rewind586_fast  # noqa: F401  (batched existence checks for the modules below)
import rewind586_delivery as d586

BUILD = tree.BUILD
MELONX_SOURCE, MELONX_RUN, MELONX_ARTIFACT = d586.MELONX_SOURCE, d586.MELONX_RUN, d586.MELONX_ARTIFACT
CORE_SOURCE, CORE_RUN = d586.CORE_SOURCE, d586.CORE_RUN


def contract():
    return tree.verify()


def host_run():
    """The iPhone host run whose checks the build packages (dist/melonx-host)."""
    return d586.previous.completed(d586.HOST_RUN, d586.HOST_SOURCE, d586.HOST_STEPS558)


def retain_checks():
    out = ROOT / 'build/delivery'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'rewind586-engine-run.json').write_text(json.dumps(d586.engine_run(), indent=2) + '\n')
    (out / 'rpcs3-cell587-core.json').write_text(json.dumps(dict(d586.core_receipt(), run=d586.core_run()), indent=2) + '\n')
    print('Bound the 586 engine run and the 587 Core receipt to the pinned tree.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('core_paths', nargs='*')
    for flag in ('--contract', '--retain-checks', '--wait-for-components', '--component-runs',
                 '--download-components', '--engine-evidence'):
        parser.add_argument(flag, action='store_true')
    parser.add_argument('--output', default='build/delivery/baseline586.json')
    args = parser.parse_args()
    if args.rpc_core_inputs:
        d586.validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths)
        return
    report = dict(build=int(BUILD), contract=contract())
    if args.retain_checks:
        retain_checks()
    if args.wait_for_components:
        report['rpcCore'] = d586.core_run()
    if args.component_runs:
        report['engine'] = d586.engine_run()
        report['host'] = host_run()
    if args.download_components:
        report['downloads'] = [d586.d549.download(MELONX_ARTIFACT, 'dist/melonx'),
                               d586.d549.download(d586.HOST_ARTIFACT, 'dist/melonx-host')]
    if args.engine_evidence:
        report['engineEvidence'] = d586.engine_evidence()
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
