"""Authenticate unchanged 533 runtime tests; execute the new Apple tests separately."""
from pathlib import Path
import hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = '77388b61cbd265559ae79f4748fdf7b12df33928'
RUN = 40179193884
def api(endpoint):
    return json.loads(subprocess.check_output(['gh','api','repos/TarbleFR/RewindBox/'+endpoint]))
run = api(f'actions/runs/{RUN}')
assert run['head_sha'] == SOURCE and run['conclusion'] == 'success'
job = next(j for j in api(f'actions/runs/{RUN}/jobs')['jobs'] if j['name'] == 'core')
assert job['conclusion'] == 'success'
required = ['Verify iOS Vulkan host-import fallback contract',
            'Verify SDL3 audio never queues synthetic silence on producer underrun',
            'Execute production audio accounting and Vulkan failure regressions',
            'Exercise display ratios, existing memory settings and stale-session refusal']
assert all(any(s['name'] == name and s['conclusion'] == 'success' for s in job['steps']) for name in required)
paths = ['build-utils/melonx/source.json', 'build-utils/melonx/adapt_audio.py',
         'build-utils/melonx/adapt_runtime.py', 'build-utils/melonx/adapt_session.py',
         'test/melonx_ios_vulkan_host_import_test.py', 'test/melonx_ios_audio_underrun_test.py',
         'test/melonx_runtime_regressions_test.py', 'native/melonx/EmbeddedGraphicsSettings.cs',
         'native/melonx/EmbeddedSessionCoordinator.cs', 'native/melonx/EmbeddedMemory.cs',
         'build-utils/melonx/adapt_memory.py', 'test/melonx_display_native_test.py']
inputs = {}
for path in paths:
    data = (ROOT/path).read_bytes()
    assert data == subprocess.check_output(['git','show',SOURCE+':'+path],cwd=ROOT), path
    inputs[path] = hashlib.sha256(data).hexdigest()
out = ROOT/'dist/melonx/apple-update-retained-tests.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(dict(result='passed',source=SOURCE,run=RUN,job=job['id'],steps=required,
    inputs=inputs,reexecuted=False),indent=2)+'\n')
print('PASS unchanged SDL3, Vulkan and display tests retained; active Apple backend has new executable coverage.')
