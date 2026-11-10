"""Private Build 532: exact compiled SDL3 callback underrun fix on the MeloNX NativeAOT engine."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import melonxlaunch529_delivery as previous

ROOT = Path(__file__).resolve().parents[2]
SOURCE = previous.SOURCE
HOST_SOURCE = previous.HOST_SOURCE
APP_SOURCE = previous.APP_SOURCE
HEADER_SOURCE = previous.HEADER_SOURCE
HOST_RUN = previous.HOST_RUN
APP_RUN = previous.APP_RUN
PRODUCT = previous.PRODUCT
HOST = previous.HOST
CORE_SOURCE = previous.CORE_SOURCE
CORE_RUN = previous.CORE_RUN
validate_rpc_core_identity = previous.validate_rpc_core_identity
validate_rpc_core_pin = previous.validate_rpc_core_pin
validate_psp_core_identity = previous.validate_psp_core_identity

# The engine must be compiled afresh from the exact committed iOS Vulkan fix,
# rather than reusing Build 529's validated but GPU-crashing core.
MELONX_SOURCE = '6c08b52dac577b4d547f3e7bdd9cf5a7ed5a5b39'
MELONX_RUN = 40162516773
LAST_VALIDATED_APP = 'ab7997a0ec041412298ce64bb7b59b4ad4d051b1'
BUILD = '532'
MELONX_INPUTS = (
    'native/melonx/EmbeddedGraphicsSettings.cs',
    'native/melonx/EmbeddedSession.cs',
    'test/melonx_display_native_test.py',
    'build-utils/melonx/adapt_audio.py',
    'build-utils/melonx/prepare_embedded.py',
    'test/melonx_ios_audio_underrun_test.py',
    'build-utils/melonx/adapt_runtime.py',
    'build-utils/melonx/reuse_keys_validation.py',
    '.github/workflows/melonx-core.yml',
    'test/melonx_ios_vulkan_host_import_test.py',
)
ENGINE_REQUIRED_STEPS = (
    'Verify iOS Vulkan host-import fallback contract',
    'Verify SDL3 audio never queues synthetic silence on producer underrun',
    'Audit patched SDL3 audio callback in exact NativeAOT source receipt',
    'Exercise display ratios, existing memory settings and stale-session refusal',
    'Reuse exact successful Darwin and homebrew proofs',
    'Compile NativeAOT library and verify exported ABI',
    'Exercise this exact rebuilt engine in an ARM64 iOS app',
)

def cmd(*arguments):
    return subprocess.check_output(list(map(str, arguments)), cwd=ROOT, text=True).strip()

def check_source():
    assert os.environ.get('BUILD_NUMBER') == BUILD
    sha = cmd('git', 'rev-parse', 'HEAD')
    assert os.environ.get('GITHUB_SHA') == sha, 'Checkout/source-identity mismatch'
    for path in MELONX_INPUTS:
        expected = subprocess.check_output(['git', 'show', MELONX_SOURCE + ':' + path], cwd=ROOT)
        assert expected == (ROOT / path).read_bytes(), 'MeloNX engine source drift: '+path
    # Build 532 changes only the private, pinned MeloNX SDL3 callback.
    # All app/native/other emulator host inputs are byte-for-byte unchanged
    # since the validated Build 531, including RPCS3.
    changed = cmd('git', 'diff', '--name-only', LAST_VALIDATED_APP, 'HEAD', '--',
                  'lib', 'native', 'packages', 'assets', 'ios', 'pubspec.yaml', 'pubspec.lock')
    assert not changed, 'Build 532 app drift since validated Build 531: '+changed
    audio = (ROOT/'build-utils/melonx/adapt_audio.py').read_text()
    assert 'SDL_PutAudioStreamData(streamDevice, (nint)pStreamDst, byteCount);' in audio
    assert 'if (byteCount == 0)' in audio
    assert (ROOT/'build-utils/melonx/prepare_embedded.py').read_text().count('adapted += adapt_audio(source)') == 1
    cmd('python3','test/melonx_ios_audio_underrun_test.py')
    options = (ROOT/'native/melonx/EmbeddedGraphicsSettings.cs').read_text()
    defaults = (ROOT/'native/melonx/EmbeddedSession.cs').read_text()
    ui = (ROOT/'lib/widgets/melonx_internal_playlist_actions.dart').read_text()
    assert 'internal bool ShaderCache = true;' in options
    assert 'internal bool AsyncShaders = false;' in options
    assert 'DisableShaderCache = false, EnableAsyncShaderCompilation = false,' in defaults
    assert "('shaderCache', 'Shader cache', true)" in ui
    assert "('asyncShaders', 'Async shaders', false)" in ui
    display = (ROOT/'test/melonx_display_native_test.py').read_text()
    assert 'Check(explicitOld.DisableShaderCache && explicitOld.EnableAsyncShaderCompilation)' in display
    assert 'Check(!safeDefault.DisableShaderCache && !safeDefault.EnableAsyncShaderCompilation)' in display
    text = (ROOT/'build-utils/melonx/adapt_runtime.py').read_text()
    assert 'disable_ios_host_import(source)' in text
    assert '!OperatingSystem.IsIOS() && _physicalDevice.IsDeviceExtensionPresent(ExtExternalMemoryHost.ExtensionName)' in text
    assert '.Where(extension => !OperatingSystem.IsIOS() || extension != ExtExternalMemoryHost.ExtensionName)' in text
    cmd('python3','test/melonx_ios_vulkan_host_import_test.py')
    identity = ROOT/'dist/rpcs3-native/identity.json'
    if identity.exists():
        validate_rpc_core_identity(json.loads(identity.read_text()))
    return dict(source=sha, melonxEngineSource=MELONX_SOURCE,
                melonxEngineRun=MELONX_RUN, rpcs3CoreRun=CORE_RUN,
                build=BUILD, baselineBuild=531, physicalGameplayTested=False, audioRegressionTestedOnDevice=False)

def remote_status():
    return json.loads(subprocess.check_output(
        ['gh','api',f'repos/TarbleFR/RewindBox/actions/runs/{MELONX_RUN}']))

def check_engine():
    deadline = time.monotonic()+5400
    while True:
        state=remote_status()
        assert state['head_sha']==MELONX_SOURCE
        assert state['path']=='.github/workflows/melonx-core.yml'
        if state['status']=='completed':
            assert state['conclusion']=='success', ('MeloNX engine failed',state['html_url'])
            break
        if time.monotonic()>=deadline:raise TimeoutError('MeloNX engine build timed out')
        time.sleep(20)
    results=json.loads(subprocess.check_output(
        ['gh','api',f'repos/TarbleFR/RewindBox/actions/runs/{MELONX_RUN}/jobs']))
    jobs=[j for j in results['jobs'] if j.get('name')=='core']
    assert len(jobs)==1 and jobs[0]['conclusion']=='success'
    completed={step['name'] for step in jobs[0]['steps'] if step['conclusion']=='success'}
    assert set(ENGINE_REQUIRED_STEPS)<=completed,sorted(set(ENGINE_REQUIRED_STEPS)-completed)
    return dict(run=MELONX_RUN,source=MELONX_SOURCE,
                steps=list(ENGINE_REQUIRED_STEPS),gameplayTested=False,
                deviceVerified=False)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--rpc-core-inputs')
    p.add_argument('core_paths', nargs='*')
    p.add_argument('--source-only',action='store_true')
    p.add_argument('--wait-for-components',action='store_true')
    p.add_argument('--skin-session-evidence',action='store_true')
    p.add_argument('--scope')
    p.add_argument('--output',default='build/delivery/reused-validation532.json')
    a=p.parse_args()
    if a.rpc_core_inputs:
        validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths)
        return
    report=check_source()
    if a.wait_for_components or a.skin_session_evidence:
        report['nativeEngine']=check_engine()
        report['priorValidatedAppRun']=40160226793
        # Re-check prior clean App 529, not an implied claim of iPhone stability.
        prior=json.loads(subprocess.check_output(
            ['gh','api','repos/TarbleFR/RewindBox/actions/runs/40160226793']))
        assert prior['status']=='completed' and prior['conclusion']=='success'
    if not a.source_only:
        out=ROOT/a.output
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
