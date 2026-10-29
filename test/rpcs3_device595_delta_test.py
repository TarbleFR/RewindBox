#!/usr/bin/env python3
"""Authenticate the post-595 source delta and its six existing native results.

No compiler, native executable, historical gate, Core build or CMake invocation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import rpcs3_device595_test as targeted
import rpcs3_texture_address_index_test as address

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/rpcs3-device595-20261029'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_text())
    record = json.loads((EVIDENCE / 'source-record.json').read_text())
    assert record == manifest['device595_allocations_20261029']
    assert hashlib.sha256((ROOT / 'build-utils/rpcs3/embedded-core.patch').read_bytes()).hexdigest() == manifest['patch_sha256']
    old = json.loads(subprocess.check_output(
        ['git', 'show', record['baseline_commit'] + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert old['patch_sha256'] == record['baseline_patch_sha256']
    for relative, expected in old['files_sha256'].items():
        assert targeted.sha(baseline / relative) == expected, relative
    for relative, expected in manifest['files_sha256'].items():
        assert targeted.sha(source / relative) == expected, relative
    changed = {p for p, h in manifest['files_sha256'].items() if old['files_sha256'].get(p) != h}
    assert changed == set(record['files_after_sha256'])
    assert sum(manifest['files_sha256'].get(p) == h for p, h in old['files_sha256'].items()) == 311
    fixture = ROOT / record['delta_fixture']
    assert targeted.sha(fixture) == record['delta_sha256']
    with tempfile.TemporaryDirectory(prefix='rpcs3-device595-delta-') as temp:
        for relative in changed:
            dest = Path(temp) / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, dest)
        subprocess.run(['git', 'apply', '--reverse', str(fixture)], cwd=temp, check=True)
        for relative in changed:
            assert targeted.sha(Path(temp) / relative) == targeted.sha(baseline / relative)
    authenticated = {}
    for case in ['array', 'temporary', 'address']:
        code = (address.harness(source, baseline) if case == 'address'
                else getattr(targeted, 'make_' + case)(source, baseline)[0])
        for mode in ['plain', 'asan']:
            path = EVIDENCE / f'{case}-{mode}.json'
            proof = json.loads(path.read_text())
            assert proof['passed'] and not proof['physicalDeviceTested'] and not proof['gameplayMeasured']
            assert proof['harnessSHA256'] == hashlib.sha256(code.encode()).hexdigest(), path
            for relative, expected in proof['sourceSHA256'].items():
                assert targeted.sha(source / relative) == expected, relative
            for relative, expected in proof['baselineSHA256'].items():
                assert targeted.sha(baseline / relative) == expected, relative
            assert '-UNDEBUG' in proof['compilerFlags'] and '-DNDEBUG' not in proof['compilerFlags']
            assert ('-fsanitize=address,undefined' in proof['compilerFlags']) == (mode == 'asan')
            authenticated[path.name] = targeted.sha(path)
    report = dict(passed=True, canonicalPostimages=len(manifest['files_sha256']),
                  unchangedCanonicalPostimages=311, affectedNativeResults=authenticated,
                  reverseDeltaMatchesBaseline=True, nativeSuitesReexecuted=False,
                  physicalDeviceTested=False, gameplayMeasured=False)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
