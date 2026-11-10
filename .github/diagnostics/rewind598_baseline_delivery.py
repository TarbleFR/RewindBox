"""Bind the retained RPCS3 Core and new verified MeloNX core to delivered597.

Historical validation functions are not replayed. Artifact downloads are
hashed before extraction; unchanged components keep the established byte pins.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

import rewind598_baseline as tree
import rewind598_engine as engine
import rpcs3runtime597_delivery_core as core

ROOT = Path(__file__).resolve().parents[2]


def download_engine():
    engine.engine_run()
    cache = ROOT / 'build/components598'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / 'melonx-engine.zip'
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != engine.MELONX_ARTIFACT_SHA256:
        with archive.open('wb') as stream:
            subprocess.run(['gh', 'api', f'repos/TarbleFR/RewindBox/actions/artifacts/{engine.MELONX_ARTIFACT_ID}/zip'],
                           stdout=stream, cwd=ROOT, check=True, timeout=600)
    assert archive.stat().st_size == engine.MELONX_ARTIFACT_BYTES
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == engine.MELONX_ARTIFACT_SHA256
    target = ROOT / 'dist/melonx'
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts, name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        z.extractall(target)
    return dict(artifact=engine.MELONX_ARTIFACT_ID, archiveSHA256=engine.MELONX_ARTIFACT_SHA256,
                bytes=archive.stat().st_size, target='dist/melonx', rebuilt=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('core_paths', nargs='*')
    for flag in ('--contract', '--retain-checks', '--wait-for-components', '--component-runs',
                 '--download-components', '--engine-evidence', '--download-core'):
        parser.add_argument(flag, action='store_true')
    parser.add_argument('--output', default='build/delivery/baseline598.json')
    args = parser.parse_args()
    if args.rpc_core_inputs:
        core.validate_rpc_core_pin(args.rpc_core_inputs, args.core_paths)
        return
    report = dict(build=598, baseline=597)
    if args.contract:
        report['contract'] = tree.verify()
    if args.retain_checks:
        report['contract'] = tree.verify()
        report['engine'] = engine.engine_run()
        report['rpcCore'] = core.core_receipt()
    if args.wait_for_components:
        report['rpcCoreRun'] = core.core_run()
    if args.component_runs:
        report['engine'] = engine.engine_run()
        report['rpcCoreRun'] = core.core_run()
    if args.download_components:
        report['downloads'] = [download_engine()]
    if args.download_core:
        report['rpcCoreDownload'] = core.download_core()
    if args.engine_evidence:
        report['engineEvidence'] = engine.engine_evidence()
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
