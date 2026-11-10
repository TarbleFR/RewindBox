#!/usr/bin/env python3
"""Close without compiling the background backlog, save the pipeline cache first
(adapt_teardown_cache), on the real prepared engine, before and after.

Usage: melonx_teardown_cache_test.py <Core 658 prepared MeloNX tree>
       melonx_teardown_cache_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the Core 658 preparation. Static checks: each file equals the preparation once the
adapter's replacements are undone (nothing else changes); the GPU release calls the hook before Device.DisposeGpu and
nowhere else calls it; Dispose marks teardown begun before its own cancel and saves again only when the content
generation moved; ShaderCollection.Dispose promotes nothing once teardown has begun; no pause checkpoint of the pipeline
cache remains anywhere (it would hold PipelineCreationLock while the render thread runs and skip draws). The production Ryujinx.Library
(with Ryujinx.Graphics.Vulkan) is built. Executed (test/melonx_teardown_cache), for control and candidate: the real
PipelineCacheManager.cs, BackgroundCompilationScheduler.cs and VulkanException.cs, the real ShaderCollection warm-up,
wait and Dispose(bool) members, the real VulkanRenderer Dispose prefix (and the candidate's added members) and the real
WindowBase GPU release body and teardown hook run with a host Vulkan double (each VkPipelineCache a byte count, every
cache read recorded with its thread and whether the main cache lock is held) and a 20 ms compile double. The build 658
close (both compile threads inside a compile, 200 play-time pipelines queued, 20 warm-ups pending, programs disposed on
a render thread by the GPU release, then the renderer) must compile the backlog and save the cache only after the last
program in the control, and in the candidate compile nothing, save the main cache to disk before the first program is
disposed, save once, release nothing while a worker runs and log no failure. Candidate only: a pipeline added after the
hook is still saved by Dispose; a failing hook leaves the release going. No device; no close-time or stutter claim on an iPhone. Writes dist/melonx/teardown-cache-checks.json.
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
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_teardown_cache', _HOLD)
import adapt_teardown_cache  # noqa: E402
from adapt_teardown_cache import apply, BASELINE  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
WINDOW = 'src/Ryujinx.Library/Window/WindowBase.cs'
RENDERER = VULKAN + 'VulkanRenderer.cs'
COLLECTION = VULKAN + 'ShaderCollection.cs'
CACHE = VULKAN + 'PipelineCacheManager.cs'
FIXTURE = ROOT / 'test/melonx_teardown_cache'
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def run(command, cwd, timeout):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    return result


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

replacements = []
original_once = adapt_teardown_cache.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports, texts = {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-teardown-cache-') as temporary:
    temporary = Path(temporary).resolve()
    work = temporary / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)

    def recording_once(path, old, new):
        replacements.append((path.relative_to(work).as_posix(), old, new))
        original_once(path, old, new)

    adapt_teardown_cache.once = recording_once
    try:
        changed = apply(work)
    finally:
        adapt_teardown_cache.once = original_once
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    if FINAL_PREPARATION:
        later = files_edited_later('adapt_teardown_cache')
        for name in BASELINE:
            if name not in later:
                check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    control = {name: (SOURCE / name).read_text(encoding='utf-8-sig') for name in BASELINE}
    candidate = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
    for name in BASELINE:
        undone = candidate[name]
        for path, old, new in reversed(replacements):
            if path == name:
                check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
                undone = undone.replace(new, old)
        check(undone == control[name], 'unchanged but the adapter\'s replacements: ' + name)
    check(len(replacements) == 6, 'six local replacements')

    window, renderer, collection, cache = (candidate[n] for n in (WINDOW, RENDERER, COLLECTION, CACHE))
    i = window.index
    check(i('"gpuRelease"') < i('EmbeddedGpuReleased = true;') < i('BeginRendererTeardown();\n                    Device.DisposeGpu();') <
          i('"gpuReleased"') < i('finally { FinalizeWindowRenderer(); }'), 'the hook runs right before Device.DisposeGpu, after the drain')
    callers = [p for p in (work / 'src').rglob('*.cs') if re.search(r'\.BeginTeardown\(\)', p.read_text(encoding='utf-8-sig', errors='replace'))]
    check([p.relative_to(work).as_posix() for p in callers] == [WINDOW], 'BeginTeardown is called by the GPU release only: ' + str(callers))
    check(window.count('BeginRendererTeardown();') == 1, 'one hook call')
    hook = member(window, 'private void BeginRendererTeardown()')
    check('catch (Exception error)' in hook and '"compileCancelFailed"' in hook, 'a failing hook is journalled, the release goes on')
    check('        internal void SetEmbeddedPaused(bool paused) => _embeddedLifetime.SetPaused(paused);\n' in window and 'SetEmbeddedPaused(bool paused)\n' not in window,
          'the pause control is unchanged')
    check(not re.search(r'CheckpointMain|RequestPausedPipelineCacheCheckpoint|CheckpointPausedPipelineCache|PauseCheckpoint|pauseCheckpoint|_hostPaused|Pipeline Cache Checkpoint',
                        '\n'.join(candidate.values())), 'no pause checkpoint code remains in the edited files')
    begin = member(renderer, 'public void BeginTeardown()')
    b = begin.index
    check(b('Interlocked.Exchange(ref _teardownBegun, 1) != 0') < b('shader.CancelPendingWarmUp();') <
          b('BackgroundCompilationScheduler.Dispose();') < b('"compilesCancelled"') < b('PipelineCacheManager.MergeAndSave();') <
          b('_teardownSavedGeneration, PipelineCacheManager.ContentGeneration') < b('"pipelineCacheSaved"'),
          'hook: once, cancel and join, journal, save, record the saved generation')
    dispose = member(renderer, 'public unsafe void Dispose()')
    d = dispose.index
    check(d('Interlocked.Exchange(ref _teardownBegun, 1);') < d('shader.CancelPendingWarmUp();') < d('BackgroundCompilationScheduler.Dispose();') <
          d('Api.DeviceWaitIdle(_device);') < d('if (Volatile.Read(ref _teardownSavedGeneration) != PipelineCacheManager.ContentGeneration)') <
          d('PipelineCacheManager.MergeAndSave();') < d('CommandBufferPool.Dispose();'), 'Dispose: teardown begun, then its order unchanged')
    after = lambda text: text[text.index('            CommandBufferPool.Dispose();'):]
    check(after(dispose) == after(member(control[RENDERER], 'public unsafe void Dispose()')), 'release order unchanged after the cache save')
    gated = member(collection, 'protected virtual void Dispose(bool disposing)')
    check('if (!_gd.TeardownBegun && (!_detachedWarmUp || Volatile.Read(ref _backgroundCompilationDemanded) != 0))\n                {\n'
          '                    PromoteBackgroundCompilation();' in gated, 'disposal promotes nothing once teardown has begun')
    # The main cache lock is the lock pipeline creation in the main cache takes (and the one MergeAndSave takes).
    check('BackgroundCompilationScheduler.PipelineCacheCount,\n                PipelineCreationLock);' in control[RENDERER],
          'PipelineCacheManager gets PipelineCreationLock as its main cache lock')
    state = (SOURCE / VULKAN / 'PipelineState.cs').read_text(encoding='utf-8-sig')
    check(state.count('if (gd.PipelineCacheManager.IsMainCache(cache))') >= 2 and 'lock (gd.PipelineCreationLock)' in state and
          'gd.PipelineCreationLock.TryEnter()' in state, 'main-cache pipeline creation takes that lock (TryEnter on the non-blocking path)')
    # Why, in the preparation: GpuContext disposes the programs before the renderer, and a program disposal waits.
    gpu = (SOURCE / 'src/Ryujinx.Graphics.Gpu/GpuContext.cs').read_text(encoding='utf-8-sig')
    gdispose = member(gpu, 'public void Dispose()')
    check(gdispose.index('physicalMemory.Dispose();') < gdispose.index('DeferredActions.TryDequeue') < gdispose.index('Renderer.Dispose();'),
          'GpuContext disposes physical memory (its shader caches) before the renderer')
    check('ShaderCache.Dispose();' in (SOURCE / 'src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs').read_text(encoding='utf-8-sig') and
          'program.Dispose();' in member((SOURCE / 'src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs').read_text(encoding='utf-8-sig'), 'public void Dispose()'),
          'PhysicalMemory.Destroy disposes every cached program')
    control_dispose = member(control[COLLECTION], 'protected virtual void Dispose(bool disposing)')
    check(control_dispose.index('PromoteBackgroundCompilation();') < control_dispose.index('_compileTask.Wait();') <
          control_dispose.index('WaitForBackgroundPipelineQueue();'), 'control: a disposal promotes, then waits for every queued pipeline')
    check(member(control[RENDERER], 'public unsafe void Dispose()').count('PipelineCacheManager.MergeAndSave();') == 1 and
          len(re.findall(r'\.MergeAndSave\(\)', '\n'.join(control.values()))) == 1, 'control: the main cache is saved only in Dispose')
    texts = dict(window=window, renderer=renderer)

    result = run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo', '-m:1',
                  '-p:NuGetAudit=false'], work, 2400)
    check(result.returncode == 0, 'production Ryujinx.Library (and Ryujinx.Graphics.Vulkan) builds with the adapter')
    check((work / 'src/Ryujinx.Graphics.Vulkan/bin/Release/net10.0/Ryujinx.Graphics.Vulkan.dll').is_file(), 'Vulkan assembly built')

    for variant, tree in (('control', SOURCE), ('candidate', work)):
        source = {name: (tree / name).read_text(encoding='utf-8-sig') for name in BASELINE}
        collection_text, renderer_text, window_text = source[COLLECTION], source[RENDERER], source[WINDOW]
        signatures = ['private async Task BackgroundCompilation()', 'private async Task<bool> WaitForShaderModuleCompilation()',
                      'public void PromoteBackgroundCompilation()', 'private Task RunBackgroundPipelineCompile(',
                      'private void LogBackgroundPipelineFailure(', 'public void CancelPendingWarmUp()',
                      'public void WaitForBackgroundCompilation()', 'private static bool CancelledByTeardown(']
        methods = '\n'.join(member(collection_text, s) for s in signatures)
        disposal = member(collection_text, 'protected virtual void Dispose(bool disposing)')
        disposal = disposal[:disposal.index('                for (int i = 0; i < _shaders.Length; i++)')] + '            }\n        }\n'
        close = member(renderer_text, 'public unsafe void Dispose()')
        close = close[close.index('{') + 1:close.index('            CommandBufferPool.Dispose();')]
        members = ''
        if variant == 'candidate':
            start = renderer_text.index('        // RewindBox (adapt_teardown_cache): set once')
            members = renderer_text[start:renderer_text.index('        public unsafe void Dispose()', start)]
        start = window_text.rindex('\n', 0, window_text.index('internal void SetEmbeddedPaused(bool paused)')) + 1
        if variant == 'candidate':
            hook_text = member(window_text, 'private void BeginRendererTeardown()')
            window_members = window_text[start:window_text.index(hook_text) + len(hook_text)]
        else:
            window_members = window_text[start:window_text.index('\n', start) + 1]
        release_start = window_text.rindex('\n', 0, window_text.index('long gpuReleaseStart = Stopwatch.GetTimestamp();')) + 1
        release_end = window_text.index('finally { FinalizeWindowRenderer(); }', release_start) + len('finally { FinalizeWindowRenderer(); }')
        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        template = (FIXTURE / 'Double.cs').read_text()
        (fixture / 'Double.cs').write_text(template.replace('/* SHADER_METHODS */', methods + '\n' + disposal)
                                           .replace('/* RENDERER_MEMBERS */', members).replace('/* RENDERER_CLOSE_PREFIX */', close)
                                           .replace('/* WINDOW_MEMBERS */', window_members)
                                           .replace('/* WINDOW_RELEASE */', window_text[release_start:release_end]))
        for name in ('PipelineCacheManager.cs', 'BackgroundCompilationScheduler.cs', 'VulkanException.cs'):
            shutil.copyfile(tree / VULKAN / name, fixture / name)
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        constants = '<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if variant == 'candidate' else ''
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit>' + constants +
            '<NoWarn>CS0649;CS0414;CS0169;CS8321;CS0162;CS1998;CS8632</NoWarn></PropertyGroup></Project>\n')
        result = run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'], fixture, 900)
        check(result.returncode == 0, variant + ' fixture builds with the real members')
        result = run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant], fixture, 900)
        check(result.returncode == 0, variant + ' fixture runs')
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
workers = c['workers']
check(c['compiledDuringClose'] >= 200 and c['closeMs'] >= 300 + 0.8 * 200 * 20 / (workers + 1),
      'control: the release compiles the backlog: %d in %d ms' % (c['compiledDuringClose'], c['closeMs']))
check(k['compiledDuringClose'] == 0 and k['closeMs'] < 1500, 'candidate: nothing compiled: %d in %d ms' % (k['compiledDuringClose'], k['closeMs']))
check(c['releasedWhileWorkerRan'] is False and k['releasedWhileWorkerRan'] is False, 'nothing released while a worker runs')
check(c['programDisposes'] == k['programDisposes'] == 220 and c['finalized'] == k['finalized'] == 1, 'every program disposed, window finalized')
check(c['mainWrites'] == 1 and not c['mainWrittenBeforeFirstProgramDispose'] and c['mainWrittenAfterRendererDispose'],
      'control: the main cache is written once, after every program disposal')
check(k['mainWrites'] == 1 and k['mainWrittenBeforeFirstProgramDispose'] and not k['mainWrittenAfterRendererDispose'],
      'candidate: the main cache is on disk before the first program disposal, written once')
check(k['mainFileSaved'] and k['mainFileBytes'] >= 32 + 10 * 64 * 1024 and c['mainFileSaved'], 'the main cache file holds the session\'s pipelines')
check(c['deviceIdles'] == k['deviceIdles'] == 1, 'device wait once')
check(k['failureLines'] == 0 and k['failureLinesTotal'] == 0, 'no failure logged by the candidate: ' + str(k['warnings']))
journal = [line for line in k['journal'] if line.startswith(('teardown', 'gpuTeardown'))]
names = [' '.join(line.split(' ')[:2]) for line in journal]
check(names == ['teardown gpuRelease', 'teardown compilesCancelled', 'teardown pipelineCacheSaved', 'gpuTeardown deviceIdleWait',
                'gpuTeardown compiles', 'teardown gpuReleased'], 'candidate journal order: ' + str(names))
check(journal[1].startswith('teardown compilesCancelled programs 220; cancelled before a worker took them: shader modules 0, '
                            'pipelines 200; cancel and join '), 'the hook counts the cancelled backlog: ' + journal[1])
check('pipelines 200' in journal[3] and ', pipelines 200;' in journal[4], 'Dispose reports the same counts (its cancel is a no-op)')
order = k['order']
check(order.index('journal teardown compilesCancelled') < order.index('data main end') < order.index('programDispose') <
      order.index('rendererDispose') < order.index('deviceIdle'), 'candidate order: cancel, save, programs, renderer, device wait')
check(k['mainWritesWhenChangedAfterHook'] == 2 and k['savedBytesWhenChangedAfterHook'] == k['expectedBytesWhenChangedAfterHook'],
      'a pipeline added after the hook is still saved by Dispose')
check(k['disposeGpuAfterHookFailure'] is True and len(k['hookFailureJournal']) == 1 and
      'ObjectDisposedException' in k['hookFailureJournal'][0], 'a failing hook is journalled and the release goes on')

inputs = ['build-utils/melonx/adapt_teardown_cache.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_teardown_cache_test.py',
          'test/melonx_teardown_cache/Double.cs', 'test/melonx_teardown_cache/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionLibraryAssemblyBuilt=True,
               productionVulkanAssemblyBuilt=True, nativePipelineDouble=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host teardown ordering and cache persistence with a Vulkan double and a 20 ms compile double; the close '
                          'time on an iPhone, MoltenVK\'s real vkGetPipelineCacheData cost for a 600 MiB main cache, and the '
                          'close behaviour on a device are known only from a device run.')
out = ROOT / 'dist/melonx/teardown-cache-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
