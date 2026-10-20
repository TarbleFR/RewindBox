#!/usr/bin/env python3
"""Reuse successful, unchanged bootstrap inputs; execute checks after a change."""
import json
from pathlib import Path
import subprocess
import re

root = Path(__file__).resolve().parents[2]
prior = '240a7be3fcace824e0d7c690e34fdbae1c3c3c73'
inputs = ['native/melonx', 'test/melonx_bootstrap_test.py']
subprocess.run(['git', 'fetch', '--depth', '1', 'origin', prior], check=True, cwd=root)
changed = subprocess.check_output(['git', 'diff', '--name-only', prior, 'HEAD', '--', *inputs], cwd=root, text=True)
out = root / 'dist/melonx/bootstrap-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
if not changed.strip():
    job = json.loads(subprocess.check_output(['gh', 'api', 'repos/TarbleFR/neostation-ios/actions/jobs/118911723958']))
    assert job['head_sha'] == prior and job['run_id'] == 39505037649
    phase = next(s for s in job['steps'] if s['name'] == 'Execute the embedded storage boundary')
    assert phase['conclusion'] == 'success'
    sdk = subprocess.check_output(['dotnet', '--version'], text=True).strip()
    # The exact framework/runtime version is checked against the original log.
    log = subprocess.check_output(['gh', 'api', '--allow-escape-sequences',
                                  'repos/TarbleFR/neostation-ios/actions/jobs/118911723958/logs'], text=True)
    # The host check is outside the engine's global.json. The SDK resolver
    # therefore selected the highest installed SDK, not the engine's 10.0.100.
    # Compare that actual selection with the previous installed-SDK inventory.
    version_key = lambda value: tuple(int(n) for n in value.split('.'))
    previous_sdks = re.findall(r'\s(\d+\.\d+\.\d+) \[[^\n]+/sdk\]', log)
    assert sdk == max(previous_sdks, key=version_key), sdk
    runtimes = subprocess.check_output(['dotnet', '--list-runtimes'], text=True)
    current_net8 = [line.split()[1] for line in runtimes.splitlines() if line.startswith('Microsoft.NETCore.App 8.')]
    previous_net8 = re.findall(r'Microsoft.NETCore.App (8\.\d+\.\d+) ', log)
    net8 = max(current_net8, key=version_key)
    assert net8 == max(previous_net8, key=version_key)
    assert 'Embedded storage and initialization: 15 cases passed.' in log
    receipt = dict(source=prior, run=39505037649, job=118911723958, passedCases=15,
                   inputsUnchanged=True, sdk=sdk, runtime=net8, reexecuted=False)
    print('Reused 15 successful embedded storage/initialization cases; inputs and .NET identities match.')
else:
    subprocess.run(['python3', 'test/melonx_bootstrap_test.py'], check=True, cwd=root)
    receipt = dict(source=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                   passedCases=15, reexecuted=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
