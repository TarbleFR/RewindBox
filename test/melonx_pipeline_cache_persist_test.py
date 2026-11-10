#!/usr/bin/env python3
"""adapt_pipeline_cache_persist on the final preparation, against the Core 681 postimage as control.

The main pipeline cache is written when the guest is paused (the app leaves the foreground) and checkpointed every 90 s
after 8 main pipelines, also from render-thread pipelines (queued on the thread pool); Dispose waits for a write in
flight. Control: the final preparation with the adapter reversed (melonx_adapter_control), which must be the Core 681
bytes. Executed (test/melonx_pipeline_cache_persist with test/melonx_main_cache_checkpoint/Double.cs) for control and
candidate on the variant's real PipelineCacheManager.cs; VulkanRenderer.cs and Library.cs are checked in source.
Writes dist/melonx/pipeline-cache-persist-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
import adapt_pipeline_cache_persist as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
MANAGER, STATE = VULKAN + 'PipelineCacheManager.cs', VULKAN + 'PipelineState.cs'
HARNESS = ROOT / 'test/melonx_pipeline_cache_persist'
DOUBLE = ROOT / 'test/melonx_main_cache_checkpoint/Double.cs'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


temporary = tempfile.TemporaryDirectory(prefix='melonx-pipeline-cache-persist-')
WORK = Path(temporary.name).resolve()  # resolved: on macOS /var is a link to /private/var
# The adapter's postimage: later adapters sharing its files (adapt_pipeline_build_journal, Core 685) reversed first; the
# receipt binds the final preparation, which re-applying them forward must give back.
PREPARED = FINAL_SOURCE
POST = WORK / 'post'
LATER = control_tools.postimage('adapt_pipeline_cache_persist', FINAL_SOURCE, POST)
replay = WORK / 'replay'
shutil.copytree(POST, replay)
for later in LATER:
    __import__(later).apply(replay)
for name in adapter.BASELINE:
    check((replay / name).read_bytes() == (PREPARED / name).read_bytes(), 'the later adapters reproduce the final preparation: ' + name)
shutil.copyfile(PREPARED / (VULKAN + 'VulkanException.cs'), WORK / 'VulkanException.cs')
FINAL_SOURCE = POST
CONTROL = WORK / 'control'
for name in adapter.BASELINE:
    (CONTROL / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FINAL_SOURCE / name, CONTROL / name)

# --- Control: the adapter reversed must be the Core 671 bytes; forward reproduces the final preparation ---
control_tools._reverse('adapt_pipeline_cache_persist', CONTROL)
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 681 postimage: ' + name)
forward = WORK / 'forward'
for name in adapter.BASELINE:
    (forward / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL / name, forward / name)
changed = sorted(str(p.relative_to(forward)) for p in adapter.apply(forward))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only its files')
for name in adapter.BASELINE:
    check((forward / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

# --- Static: the exact scope ---
RENDERER, LIBRARY = adapter.RENDERER, adapter.LIBRARY
manager = read(FINAL_SOURCE, MANAGER)
restored = manager
for old, new in ((adapter.CADENCE_OLD, adapter.CADENCE_NEW), (adapter.NOTIFY_OLD, adapter.NOTIFY_NEW),
                 (adapter.PAUSE_METHOD_ANCHOR, adapter.PAUSE_METHOD_NEW), (adapter.DISPOSE_OLD, adapter.DISPOSE_NEW)):
    restored = restored.replace(new, old)
check(restored == read(CONTROL, MANAGER), 'PipelineCacheManager.cs differs only by the four replacements')
check(read(FINAL_SOURCE, RENDERER).replace(adapter.RENDERER_NEW, adapter.RENDERER_OLD) == read(CONTROL, RENDERER),
      'VulkanRenderer.cs differs only by CheckpointPipelineCacheOnPause')
library = read(FINAL_SOURCE, LIBRARY)
check(library.replace(adapter.LIBRARY_NEW, adapter.LIBRARY_OLD) == read(CONTROL, LIBRARY), 'Library.cs differs only by the pause request')
pause = library[library.index(adapter.LIBRARY_NEW):library.index(adapter.LIBRARY_NEW) + len(adapter.LIBRARY_NEW)]
check('if (paused &&' in pause and 'ThreadPool.UnsafeQueueUserWorkItem(_ => pausedVulkan.CheckpointPipelineCacheOnPause(), null)' in pause,
      'the pause callback only queues the write, and only when pausing')
check(library.index('_emulationContext.System.TogglePauseEmulation(paused);', library.index('EmbeddedSessions.PublishControls')) <
      library.index('if (paused && _emulationContext?.Gpu?.Renderer'), 'the write is requested after the guest is paused')
notify = member(manager, 'public void NotifyMainPipelineCreated()')
check('ThreadPool.UnsafeQueueUserWorkItem' in notify and 'SaveCache(' not in notify and 'GetCacheDataSize(' not in notify,
      'a render-thread creation only queues a checkpoint; it never writes the cache itself')
check('lock (_mainCacheLock)' in member(manager, 'public unsafe void Dispose()'), 'Dispose takes the main cache lock')

# --- Executed: control and candidate fixtures ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
reports = {}
for variant in ('control', 'candidate'):
    tree = CONTROL if variant == 'control' else FINAL_SOURCE
    fixture = WORK / ('fixture-' + variant)
    fixture.mkdir()
    shutil.copyfile(tree / MANAGER, fixture / 'PipelineCacheManager.cs')
    shutil.copyfile(WORK / 'VulkanException.cs', fixture / 'VulkanException.cs')
    shutil.copyfile(DOUBLE, fixture / 'Double.cs')
    shutil.copyfile(HARNESS / 'Program.cs', fixture / 'Program.cs')
    constants = '<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if variant == 'candidate' else ''
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit>' + constants +
        '<NoWarn>CS0649;CS0414;CS0169;CS8321;CS0162;CS1998;CS8632</NoWarn></PropertyGroup></Project>\n')
    build = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                           capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if build.returncode:
        print('\n'.join(line for line in build.stdout.splitlines() if ': error ' in line)[:6000], flush=True)
    check(build.returncode == 0, variant + ' fixture builds with the real PipelineCacheManager.cs')
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant],
                         capture_output=True, text=True, timeout=600, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
    print(variant + ': ' + json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
check(c['pausedAfterNewPipelines']['mainFileMiB'] == 10, 'control (Core 681): pausing writes nothing; the three new pipelines are lost')
check(k['pausedAfterNewPipelines']['mainFileMiB'] >= 10.75, 'candidate: pausing writes the new pipelines: %s' % k['pausedAfterNewPipelines'])
check(k['pausedAgainUnchanged']['extraWrites'] == 0, 'candidate: a second pause with nothing new does not write')
check(c['renderThreadTrigger']['afterEightMiB'] == 10, 'control: render-thread pipelines never trigger a checkpoint')
kr = k['renderThreadTrigger']
check(kr['afterSevenMiB'] == 10 and kr['afterEightMiB'] >= 12 and kr['writtenOffTheCreatingThread'],
      'candidate: the eighth render-thread pipeline past the interval checkpoints, off the creating thread: %s' % kr)
check(c['withinInterval']['mainFileMiB'] == 10 and k['withinInterval']['mainFileMiB'] == 10, 'no checkpoint within the interval')
kd = k['disposeDuringPauseWrite']
check(kd['disposeWaitedMs'] >= 250 and kd['writeCompleted'] and kd['mainFileMiB'] >= 10.5,
      'candidate: Dispose waits for the pause write in flight: %s' % kd)
check(k['pauseLine'] is not None and 'checkpointed on pause' in k['pauseLine'], 'the pause write is journaled')
check(c['errors'] == 0 and k['errors'] == 0, 'no error line')

inputs = ['build-utils/melonx/adapt_pipeline_cache_persist.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_pipeline_cache_persist_test.py',
          'test/melonx_main_cache_checkpoint/Double.cs', 'test/melonx_pipeline_cache_persist/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               postimages={n: sha(PREPARED / n) for n in adapter.BASELINE},
               testedPostimages={n: sha(FINAL_SOURCE / n) for n in adapter.BASELINE}, reports=reports, sdk=sdk, host=platform.system(),
               physicalDeviceTested=False, gameTested=False, inputs={n: sha(ROOT / n) for n in inputs},
               limitation='Host fixture of the real cache manager with a Vulkan double. Whether iOS leaves the app the few seconds a '
                          'pause write takes before suspending it is known only from a device run.')
out = ROOT / 'dist/melonx/pipeline-cache-persist-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
