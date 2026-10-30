#!/usr/bin/env python3
"""Run unchanged IPA604 payload validators with authenticated provider snapshots.

Only the transport for GitHub JSON is replaced. Original metadata, ZIP payload,
source, identity, fixture receipt and Mach-O assertions run unchanged. No native
fixture, simulator or compiler is executed by this verifier.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent / 'RewindBox'
SOURCE = '60add3d79b3e4d9d76b68ef154cb5d3f8772c323'
for part in ('.github/diagnostics', 'build-utils', 'packages/dolphin_internal_bridge/ci'):
    sys.path.insert(0, str(ROOT / part))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ipa', type=Path)
    parser.add_argument('--receipts', type=Path)
    args = parser.parse_args()
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == SOURCE
    assert not subprocess.check_output(['git', 'diff', '--name-only', SOURCE, '--'], cwd=ROOT, text=True).strip()
    provider = json.loads((BASE / 'provider-metadata.json').read_bytes())
    producer = json.loads((BASE / 'producer-metadata.json').read_bytes())
    full_jobs = json.loads((BASE / 'full-job-metadata.json').read_bytes())
    endpoints = {}
    for run, jobs, artifacts in (
        (provider['runtimeRun'], full_jobs['runtimeJobs'], provider['runtimeArtifacts']),
        (producer['compile_run'], full_jobs['compileJobs'], producer['compile_artifacts']),
        (producer['rpcs3_run'], full_jobs['rpcs3Jobs'], producer['rpcs3_artifacts']),
    ):
        endpoints[f"actions/runs/{run['id']}"] = run
        endpoints[f"actions/runs/{run['id']}/jobs?per_page=100"] = jobs
        for job in jobs['jobs']:
            endpoints[f"actions/jobs/{job['id']}"] = job
        for artifact in artifacts['artifacts']:
            endpoints[f"actions/artifacts/{artifact['id']}"] = artifact
    used = set()

    def actual_metadata(endpoint):
        if endpoint not in endpoints:
            raise ValueError('No observed provider metadata: ' + endpoint)
        used.add(endpoint)
        return json.loads(json.dumps(endpoints[endpoint]))

    engine = importlib.import_module('rewind604_engine')
    rpc = importlib.import_module('rpcs3runtime604_core')
    engine.api = actual_metadata
    rpc.api = actual_metadata
    # Explicitly authenticate fresh snapshots even when an unchanged-source
    # job-local memo is available from earlier preparation in this workspace.
    engine_run = engine._query_engine_run()
    rpc_run = rpc._query_core_run()
    print('Authenticated exact original/runtime/RPCS3 provider metadata', flush=True)
    engine_result = engine.engine_evidence()
    print('Full MeloNX original bytes, dependencies and retained proofs passed', flush=True)
    rpc_result = rpc.download_core()
    print('Full RPCS3 original bytes, exact sources and retained proofs passed', flush=True)
    write(BASE / 'preparation-result.json', dict(result='passed', source=SOURCE,
        providerMetadataSHA256=digest(BASE / 'provider-metadata.json'),
        producerMetadataSHA256=digest(BASE / 'producer-metadata.json'),
        fullJobMetadataSHA256=digest(BASE / 'full-job-metadata.json'),
        endpoints=sorted(used), engineRun=engine_run, rpcs3Run=rpc_run,
        engine=engine_result, rpcs3=rpc_result,
        checksReexecuted=False, physicalDeviceTested=False))
    if args.ipa is None:
        return
    assert args.ipa.is_file() and args.receipts and args.receipts.is_dir()
    receipts = ('hogwarts604-policy-checks.json', 'hogwarts604-flutter-checks.json',
                'melonx-jit-helper-init.json')
    for name in receipts:
        matches = list(args.receipts.rglob(name))
        assert len(matches) == 1, (name, matches)
        destination = ROOT / 'build/delivery' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(matches[0].read_bytes())
    output = BASE / 'final'
    output.mkdir(exist_ok=True)
    m = importlib.import_module('validate_melonx_engine604_ipa')
    melonx_report = m.validate(args.ipa)
    write(output / 'melonx-engine604.json', melonx_report)
    print('Actual downloaded IPA MeloNX payload passed', flush=True)
    r = importlib.import_module('validate_rpcs3_core604_ipa')
    rpcs3_report = r.validate(args.ipa, 604, ROOT / 'dist/rpcs3-native/identity.json')
    write(output / 'rpcs3-core604.json', rpcs3_report)
    print('Actual downloaded IPA RPCS3 payload passed', flush=True)
    subprocess.run([sys.executable, str(ROOT / 'build-utils/validate_hogwarts604_ipa.py'),
                    str(args.ipa), '--report', str(output / 'hogwarts604-host.json')],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    print('Actual downloaded IPA host/helper bindings passed', flush=True)
    report = dict(result='passed', source=SOURCE, ipa=str(args.ipa),
                  ipaBytes=args.ipa.stat().st_size, ipaSHA256=digest(args.ipa),
                  reports={p.name:digest(p) for p in sorted(output.glob('*.json'))
                           if p.name != 'strict-validator-summary.json'},
                  originalMetadataSnapshot=True, originalChecksUnchanged=True,
                  physicalDeviceTested=False, signatureCryptographicallyVerifiedHere=False)
    write(output / 'strict-validator-summary.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
