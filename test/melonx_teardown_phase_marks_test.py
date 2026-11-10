#!/usr/bin/env python3
"""Durable close-phase marks (adapt_teardown_phase_marks) on the real prepared engine. Journal only.

Usage: melonx_teardown_phase_marks_test.py <Core 647 prepared MeloNX tree>
       melonx_teardown_phase_marks_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the Core 647 preparation and builds the production Ryujinx.Library (with the GPU,
Vulkan and HLE assemblies). Static checks bind that each file equals the preparation once the added journal lines are
removed (no order, wait or decision changes), that every mark sits where it names (guest stop before and after the
guest's termination, GPU release before and after DisposeGpu, the device-wait mark before vkDeviceWaitIdle, the
swapchain mark after the window's release), and that no mark uses the "begin" status, which would change the failure
stage. No device. Writes dist/melonx/teardown-phase-marks-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_teardown_phase_marks', _HOLD)
from adapt_teardown_phase_marks import apply, BASELINE  # noqa: E402

WINDOW = 'src/Ryujinx.Library/Window/WindowBase.cs'
RENDERER = 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def strip_marks(text):
    """The file without the adapter's journal lines (marks, their timers and comments)."""
    text = re.sub(r'\n *// RewindBox \(adapt_teardown_phase_marks\)[^\n]*(\n *// [^\n]*)*', '', text)
    text = re.sub(r'\n *long (guestStopStart|gpuReleaseStart) = Stopwatch\.GetTimestamp\(\);', '', text)
    text = re.sub(r'\n *Ryujinx\.Common\.EmbeddedLaunchDiagnostics\.Record\("(teardown|gpuTeardown)", "(guestStop|guestStopped|gpuRelease|'
                  r'gpuReleased|deviceIdleWait|swapchainReleased)".*?\);(?=\n)', '', text, flags=re.S)
    return text


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 647 preparation: ' + name)
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-teardown-marks-') as temporary:
    work = Path(temporary).resolve() / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)
    changed = apply(work)
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    if FINAL_PREPARATION:
        # Files a later adapter also edits (Core 656: adapt_present_pacing in VulkanRenderer) are proven by control_source's
        # forward check; the others must be the final preparation's bytes here.
        later = files_edited_later('adapt_teardown_phase_marks')
        for name in BASELINE:
            if name not in later:
                check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    control = {name: (SOURCE / name).read_text(encoding='utf-8-sig') for name in BASELINE}
    candidate = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
    window, renderer = candidate[WINDOW], candidate[RENDERER]
    # The WindowBase GPU release gains a block around DisposeGpu; compare it normalised to the delivered one-line form.
    normal = strip_marks(window).replace('''                try
                {
                    Device.DisposeGpu();
                }
                finally''', '''                try { Device.DisposeGpu(); }
                finally''')
    check(normal == control[WINDOW], 'WindowBase unchanged but its marks')
    point = 'long programsWaited = System.Diagnostics.Stopwatch.GetTimestamp();\n'
    check(strip_marks(renderer).replace(point + '\n\n', point + '\n') == control[RENDERER],
          'VulkanRenderer unchanged but its marks (and the blank line after the device-wait mark)')
    marks = re.findall(r'EmbeddedLaunchDiagnostics\.Record\("(?:teardown|gpuTeardown)", "(\w+)"', window + renderer)
    check(sorted(marks) == sorted(['guestStop', 'guestStopped', 'gpuRelease', 'gpuReleased', 'deviceIdleWait', 'compiles', 'swapchainReleased']),
          'six marks added beside the existing compiles line: ' + str(marks))
    check(all(m != 'begin' for m in marks), 'no begin status')
    i = window.index
    check(i('"guestStop"') < i('Library.WithdrawEmbeddedControls();') < i('Device.System.Dispose();') < i('"guestStopped"') <
          i('"gpuRelease"') < i('EmbeddedGpuReleased = true;') < i('Device.DisposeGpu();') < i('"gpuReleased"') <
          i('finally { FinalizeWindowRenderer(); }'), 'window marks around their phases')
    j = renderer.index
    check(j('BackgroundCompilationScheduler.Dispose();') < j('shader.WaitForBackgroundCompilation();') < j('"deviceIdleWait"') <
          j('Api.DeviceWaitIdle(_device);') < j('PipelineCacheManager.MergeAndSave();') < j('"gpuTeardown", "compiles"') <
          j('_window.Dispose();') < j('"swapchainReleased"') < j('HelperShader.Dispose();'), 'renderer marks around their phases')
    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo',
                             '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Library builds with the marks')

inputs = ['build-utils/melonx/adapt_teardown_phase_marks.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_teardown_phase_marks_test.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core647Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               sdk=sdk, physicalDeviceTested=False, productionLibraryBuilt=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Journal only; which phase holds the SSBU close while recording is known only from a device run.')
out = ROOT / 'dist/melonx/teardown-phase-marks-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
