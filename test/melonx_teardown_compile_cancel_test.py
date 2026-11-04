#!/usr/bin/env python3
"""Close without compiling the queue (adapt_teardown_compile_cancel) on the real prepared engine, before and after.

Usage: melonx_teardown_compile_cancel_test.py <Core 642 prepared MeloNX tree>
       melonx_teardown_compile_cancel_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the Core 642 preparation (adapt_shader_warmup included), candidate adds the adapter. For each, the production
Vulkan assembly is built, and the real BackgroundCompilationScheduler, the real VulkanRenderer.Dispose prefix (up to
its first release) and the real ShaderCollection methods (BackgroundCompilation, WaitForShaderModuleCompilation,
PromoteBackgroundCompilation, RunBackgroundPipelineCompile, LogBackgroundPipelineFailure, CancelPendingWarmUp,
WaitForBackgroundCompilation, and the candidate's CancelledByTeardown) run with doubles
(test/melonx_teardown_compile_cancel). The IPA 643 SSBU case (every background worker inside a compile, 200 play-time
pipeline compiles of 20 ms queued) must take seconds in the control and compile all 200 during close, and in the
candidate complete once the running compile ends, compile none of them, release nothing while a worker runs and log no
failure. Demanded work and queued shader modules are cancelled in the candidate, work scheduled after close is refused
in both. No device; no close-time claim on an iPhone. Writes dist/melonx/teardown-compile-cancel-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_teardown_compile_cancel', _HOLD)
from adapt_teardown_compile_cancel import apply, BASELINE  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
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


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 642 preparation: ' + name)

reports, texts = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-teardown-compile-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                for name in BASELINE:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        result = subprocess.run([DOTNET, 'build', str(work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800,
                                env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Vulkan assembly builds')

        collection = (work / (VULKAN + 'ShaderCollection.cs')).read_text(encoding='utf-8-sig')
        renderer = (work / (VULKAN + 'VulkanRenderer.cs')).read_text(encoding='utf-8-sig')
        texts[variant] = (collection, renderer, (work / (VULKAN + 'BackgroundCompilationScheduler.cs')).read_text(encoding='utf-8-sig'))
        signatures = ['private async Task BackgroundCompilation()', 'private async Task<bool> WaitForShaderModuleCompilation()',
                      'public void PromoteBackgroundCompilation()', 'private Task RunBackgroundPipelineCompile(',
                      'private void LogBackgroundPipelineFailure(', 'public void CancelPendingWarmUp()',
                      'public void WaitForBackgroundCompilation()']
        if 'private static bool CancelledByTeardown(' in collection:
            signatures.append('private static bool CancelledByTeardown(')
        methods = '\n'.join(member(collection, s) for s in signatures)
        close = member(renderer, 'public unsafe void Dispose()')
        close = close[close.index('{') + 1:close.index('            CommandBufferPool.Dispose();')]
        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        template = (ROOT / 'test/melonx_teardown_compile_cancel/Double.cs').read_text()
        (fixture / 'Double.cs').write_text(template.replace('/* SHADER_METHODS */', methods).replace('/* RENDERER_CLOSE_PREFIX */', close))
        shutil.copyfile(work / (VULKAN + 'BackgroundCompilationScheduler.cs'), fixture / 'BackgroundCompilationScheduler.cs')
        shutil.copyfile(ROOT / 'test/melonx_teardown_compile_cancel/Program.cs', fixture / 'Program.cs')
        # HostThreadQos is a production helper of the Vulkan GAL layer; the demand worker only raises its own QoS.
        (fixture / 'Qos.cs').write_text('namespace Ryujinx.Graphics.GAL.Multithreading { static class HostThreadQos { '
                                        'public static void RaiseCurrentThread() { } } }\n')
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0649;CS0414;CS0169;CS8321</NoWarn>'
            '</PropertyGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
check(c['queuedCompiledDuringClose'] == 200 and c['closeMs'] >= 200 + 0.8 * 200 * 20 / c['workers'], 'control compiles the whole queue during close: ' + str(c['closeMs']))
check(k['queuedCompiledDuringClose'] == 0 and k['closeMs'] < 1000, 'candidate cancels the queue: ' + str(k['closeMs']))
check(c['releasedWhileWorkerRan'] is False and k['releasedWhileWorkerRan'] is False, 'nothing released while a worker runs')
check(k['cancelledPipelines'] == 200 and c['cancelledPipelines'] is None, 'candidate counts the cancelled pipelines')
check(k['failureLines'] == 0, 'cancellation is not logged as a failure')
journal = k['journal']
check(len(journal) == 1 and journal[0].startswith('gpuTeardown compiles programs 200; cancelled before a worker took them: '
      'shader modules 0, pipelines 200; cancel and join ') and c['journal'] == [], 'one durable teardown line: ' + str(journal))
check(c['demandedCompiledDuringClose'] == 1 and k['demandedCompiledDuringClose'] == 0, 'queued demanded work cancelled at close')
check(c['modulesCompiledDuringClose'] == 20 and k['modulesCompiledDuringClose'] == 0 and k['pipelinesAfterModules'] == 0,
      'queued shader modules cancelled, no pipeline after them')
check(c['moduleFailureLines'] > 0 or c['modulesCompiledDuringClose'] == 20, 'control path observed')
check(k['moduleFailureLines'] == 0, 'cancelled modules are not logged as failures')
check(c['idles'] == k['idles'] == 1 and c['saves'] == k['saves'] == 1, 'device idle and cache save once')
check(c['lateRan'] == k['lateRan'] == 0 and c['lateFaulted'] and k['lateFaulted'], 'work scheduled after close refused')

control_renderer, candidate_renderer = texts['control'][1], texts['candidate'][1]
body = member(candidate_renderer, 'public unsafe void Dispose()')
check(body.index('shader.CancelPendingWarmUp();') < body.index('BackgroundCompilationScheduler.Dispose();') <
      body.index('shader.WaitForBackgroundCompilation();') < body.index('Api.DeviceWaitIdle(_device);') <
      body.index('PipelineCacheManager.MergeAndSave();') < body.index('CommandBufferPool.Dispose();'),
      'cancel and join before the per-program waits, before any release')
check(body.count('BackgroundCompilationScheduler.Dispose();') == 1, 'scheduler disposed once')
after = lambda text: text[text.index('CommandBufferPool.Dispose();'):]
check(after(member(control_renderer, 'public unsafe void Dispose()')) == after(body), 'release order unchanged after the cache save')
added = ["""
        // RewindBox (adapt_teardown_compile_cancel): compiles that no worker had taken when the queues were disposed.
        public int CancelledShaderCompiles => _shaderQueue.Cancelled;
        public int CancelledPipelineCompiles => _pipelineQueue.Cancelled;
""", """
            public int Cancelled { get; private set; }
""", """                Cancelled = pending.Count;

"""]
stripped = texts['candidate'][2]
for block in added:
    check(stripped.count(block) == 1, 'scheduler addition present once')
    stripped = stripped.replace(block, '', 1)
check(stripped.replace('\n\n\n', '\n\n') == texts['control'][2].replace('\n\n\n', '\n\n'), 'scheduler unchanged but its cancellation count')

inputs = ['build-utils/melonx/adapt_teardown_compile_cancel.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_teardown_compile_cancel_test.py', 'test/melonx_teardown_compile_cancel/Double.cs',
          'test/melonx_teardown_compile_cancel/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core642Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyBuilt=True,
               nativePipelineDouble=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host scheduler and teardown ordering with a 20 ms compile double; the SSBU close time on an '
                          'iPhone and the guest-stop share of it are known only from the gpuTeardown line of a device run.')
out = ROOT / 'dist/melonx/teardown-compile-cancel-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
