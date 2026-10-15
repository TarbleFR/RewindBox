#!/usr/bin/env python3
"""Load and render every complete indexed PocketArch conversion on iOS Simulator."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.parse
import urllib.request

import libretro_simulator_probe as probe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('cores', 'inputs', 'evidence', 'label', 'layouts'):
        parser.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    args.sources = None; args.only = []; args.lot1 = False; args.lot2 = False; args.official_shaders = False
    layouts = sorted(p for p in Path(args.layouts).iterdir() if p.is_dir())
    assert len(layouts) == 39, '28 originals, two incomplete PSP files, 39 console associations'
    probe.REAL_CORES = ()
    probe.SCENARIOS = [{'name': 'pocketarch-catalog', 'core': 'neotest', 'console': 'psx',
        'content': 'content/Shader Pattern.ntc', 'previewProbe': True,
        'previewChecksExpected': 4 * len(layouts) + 2, 'expect': 'run'}]
    evidence = Path(args.evidence); evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='catalog-skins-') as temporary:
        app, scenarios = probe.assemble(args, probe.BRIDGE, Path(temporary))
        required = {}
        for folder in layouts:
            source = json.loads((folder / 'source.json').read_text())
            for remote, expected in source['hashes'].items():
                required[remote] = (source, expected)

        def download(remote):
            source, expected = required[remote]
            url = ('https://raw.githubusercontent.com/' + source['repository'] + '/' + source['commit']
                   + '/' + urllib.parse.quote(remote, safe='/'))
            with urllib.request.urlopen(url, timeout=45) as response:
                data = response.read(16 * 1024 * 1024 + 1)
            assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'], remote
            return remote, data

        with ThreadPoolExecutor(max_workers=8) as pool:
            resources = dict(pool.map(download, required))
        specs = []
        for folder in layouts:
            source = json.loads((folder / 'source.json').read_text())
            target = app / 'SkinFixtures' / folder.name; target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(folder / 'info.json', target / 'info.json')
            for local, remote in json.loads((folder / 'resources.json').read_text()).items():
                file = target / local; file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(resources[remote])
            for orientation in ('portrait', 'landscape'):
                specs.append({'identifier': folder.name, 'console': source['console'],
                              'orientation': orientation, 'minimumAssets': 0})
        (app / 'SkinFixtures/catalog-audit.json').write_text(json.dumps(specs))
        probe.run(['codesign', '--force', '--sign', '-', '--timestamp=none', app])
        outcome = probe.run_in_simulator(app, evidence, 360)
        (evidence / 'outcome.json').write_text(json.dumps(outcome, indent=2))
        report = json.loads((evidence / 'probe.json').read_text())
        problems = probe.evaluate(report, scenarios)
        (evidence / 'verdict.json').write_text(json.dumps({'source': args.label, 'problems': problems,
            'originalConfigurations': 28, 'excludedIncomplete': 2, 'consoleAssociations': len(layouts),
            'orientations': len(specs), 'verifiedImageFiles': len(resources),
            'physicalDeviceValidated': False}, indent=2))
        if problems:
            raise SystemExit('\n'.join(problems))
    print('39 PocketArch console associations: 78 native compatibility/resource/rendering checks passed.')


if __name__ == '__main__':
    main()
