"""Reuse only the unchanged successful archive/personal-files test inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = '741918e15a6bfe79ab213cdd5038ea31f1c0cc62'
RUN = 39879059963
GROUPS = {
    'Exercise firmware archive discovery and rollback integration': [
        'test/melonx_firmware_archive_test.py', 'native/melonx/EmbeddedFirmwareArchive.cs',
        'build-utils/melonx/adapt_firmware.py'],
    'Check personal configuration and actual LibHac save API': [
        'test/melonx_library_api_test.py', 'native/melonx/EmbeddedSaveTransfer.cs',
        'native/melonx/EmbeddedPersonalOptions.cs', 'native/melonx/EmbeddedKeyValidation.cs',
        'build-utils/melonx/source.json'],
}
subprocess.run(['git', 'fetch', '--depth', '1', 'origin', SOURCE], cwd=ROOT, check=True)
jobs = json.loads(subprocess.check_output(['gh', 'api', f'repos/TarbleFR/RewindBox/actions/runs/{RUN}/jobs']))['jobs']
job = next(j for j in jobs if j['head_sha'] == SOURCE and j['conclusion'] == 'success')
records = []
for phase, paths in GROUPS.items():
    if "--firmware-only" in sys.argv and phase == "Check personal configuration and actual LibHac save API":
        continue
    assert next(s for s in job['steps'] if s['name'] == phase)['conclusion'] == 'success'
    hashes = {}
    for path in paths:
        old = subprocess.check_output(['git', 'show', SOURCE + ':' + path], cwd=ROOT)
        assert old == (ROOT / path).read_bytes(), path
        hashes[path] = hashlib.sha256(old).hexdigest()
    records.append({'phase': phase, 'source': SOURCE, 'run': RUN, 'inputs': hashes,
        'sdk': '10.0.100', 'reexecuted': False})
out = ROOT / 'dist/melonx/launch-library-reuse.json'
out.write_text(json.dumps(records, indent=2) + '\n')
print('Reused successful unchanged firmware/archive and personal-file proofs; changed launch preflight is executed separately.')
