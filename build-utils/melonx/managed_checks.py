"""Reuse successful phases only when their production/test inputs still match."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PRIOR = '90ac4ab188690c1130d58848ed7ad5f436e1101c'
RUN = 39508485894  # Core failed later; these are successful test phases only.
JOB = 118923327110
CHECKS = {
    'bootstrap': (15, 'Execute the embedded storage boundary', 'test/melonx_bootstrap_test.py',
                  ['native/melonx/EmbeddedDataRoot.cs', 'native/melonx/EmbeddedInitializationState.cs'],
                  'Embedded storage and initialization: 15 cases passed.'),
    'session': (20, 'Execute session ownership and render teardown', 'test/melonx_session_test.py',
                ['native/melonx/EmbeddedSessionCoordinator.cs', 'native/melonx/EmbeddedWindowLifetime.cs'],
                'Embedded session and window lifetime: 20 cases passed.'),
}


def execute(name):
    count, phase, script, production, summary = CHECKS[name]
    inputs = [script, *production]
    subprocess.run(['git', 'fetch', '--depth', '1', 'origin', PRIOR], cwd=ROOT, check=True)
    changed = subprocess.check_output(['git', 'diff', '--name-only', PRIOR, 'HEAD', '--', *inputs], cwd=ROOT, text=True).strip()
    sdk = subprocess.check_output(['dotnet', '--version'], text=True).strip()
    runtime_lines = subprocess.check_output(['dotnet', '--list-runtimes'], text=True).splitlines()
    versions = lambda value: tuple(map(int, value.split('.')))
    runtime = max([line.split()[1] for line in runtime_lines if line.startswith('Microsoft.NETCore.App 8.')], key=versions)
    reused = False
    if not changed:
        job = json.loads(subprocess.check_output(['gh', 'api', f'repos/TarbleFR/neostation-ios/actions/jobs/{JOB}']))
        assert job['head_sha'] == PRIOR and job['run_id'] == RUN
        step = next(step for step in job['steps'] if step['name'] == phase)
        assert step['conclusion'] == 'success', step
        log = subprocess.check_output(['gh', 'api', '--allow-escape-sequences', f'repos/TarbleFR/neostation-ios/actions/jobs/{JOB}/logs'], text=True)
        assert summary in log
        previous_sdks = re.findall(r'\s(\d+\.\d+\.\d+) \[[^\n]+/sdk\]', log)
        previous_runtimes = re.findall(r'Microsoft.NETCore.App (8\.\d+\.\d+) ', log)
        reused = sdk == max(previous_sdks, key=versions) and runtime == max(previous_runtimes, key=versions)
    out = ROOT / 'dist/melonx'
    out.mkdir(parents=True, exist_ok=True)
    if reused:
        report = f'Reused {count} passed {name} cases from run {RUN}, job {JOB}; exact inputs/SDK/runtime match.\n'
    else:
        result = subprocess.run(['python3', script], cwd=ROOT, check=True, capture_output=True, text=True, timeout=150)
        assert summary in result.stdout
        report = result.stdout
    print(report, end='')
    (out / f'{name}-checks.log').write_text(report)
    receipt = dict(source=PRIOR if reused else subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   passedCases=count, reexecuted=not reused, sdk=sdk, runtime=runtime,
                   inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
    if reused: receipt.update(run=RUN, job=JOB, phase=phase, originalRunConclusion='failure', inputsUnchanged=True)
    (out / f'{name}-checks.json').write_text(json.dumps(receipt, indent=2) + '\n')
