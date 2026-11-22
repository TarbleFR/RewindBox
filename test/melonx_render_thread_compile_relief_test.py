#!/usr/bin/env python3
"""No compile on the render thread for a skippable draw, recorded states before speculative warm-ups
(adapt_render_thread_compile_relief), before and after, real engine code.

Usage: melonx_render_thread_compile_relief_test.py <final preparation containing the adapter>
       melonx_render_thread_compile_relief_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter (and any later adapter sharing its files) reversed (melonx_adapter_control);
candidate is the adapter applied to it. For each, the real BackgroundCompilationScheduler and the real ShaderCollection
members TryWaitForBackgroundComputePipeline and, in the candidate, TryWaitBrieflyForQueuedGraphicsPipeline run with
doubles (test/melonx_render_thread_compile_relief): with every pipeline thread busy, 6 speculative warm-ups, 4 recorded
states, 2 high priority compiles and 1 demanded one are queued, and the order they run in is compared (recorded states
after the warm-ups in the control, before them in the candidate); a cancellation drains the prebuild queue too; a
dispatch of a compute program loaded from the cache creates the pipeline itself in the control while its warm-up waits
(two creations) and joins that warm-up in the candidate (one); a skippable draw's short wait obtains a quick compile,
leaves a slow one to its thread within its few milliseconds and promotes nothing; the allowance refills with elapsed
time and never passes its cap. The candidate's production Vulkan assembly is built, and static checks bind that a
skippable draw no longer creates a pipeline in PipelineBase.CreatePipeline. No device.
Writes dist/melonx/render-thread-compile-relief-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_render_thread_compile_relief', _HOLD)
from adapt_render_thread_compile_relief import apply, BASELINE  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_render_thread_compile_relief'
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


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the adapter\'s preparation: ' + name)

reports, texts = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-render-thread-relief-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            later = files_edited_later('adapt_render_thread_compile_relief')
            for name in BASELINE:
                if name not in later:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
            result = subprocess.run([DOTNET, 'build', str(work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release', '-nologo',
                                     '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
            if result.returncode:
                print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
            check(result.returncode == 0, 'candidate production Vulkan assembly builds')
        collection = (work / (VULKAN + 'ShaderCollection.cs')).read_text(encoding='utf-8-sig')
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
        methods = member(collection, 'public bool TryWaitForBackgroundComputePipeline(')
        if 'public bool TryWaitBrieflyForQueuedGraphicsPipeline(' in collection:
            methods += '\n' + member(collection, 'public bool TryWaitBrieflyForQueuedGraphicsPipeline(')
        check(('TryWaitBrieflyForQueuedGraphicsPipeline' in collection) == (variant == 'candidate'), variant + ': the short wait only in the candidate')
        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        template = (FIXTURE / 'Double.cs').read_text()
        check(template.count('/* SHADER_METHODS */') == 1, 'fixture mark')
        (fixture / 'Double.cs').write_text(template.replace('/* SHADER_METHODS */', methods))
        shutil.copyfile(work / (VULKAN + 'BackgroundCompilationScheduler.cs'), fixture / 'BackgroundCompilationScheduler.cs')
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0649;CS0414;CS0169;CS8321;CS1998</NoWarn>'
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
slack = (c['workers'] - 1) * 2  # two workers take neighbouring items at the same time


def inversions(order, first, then):
    position = {name: index for index, name in enumerate(order)}
    return sum(1 for a in order if a.startswith(first) for b in order if b.startswith(then) and position[a] > position[b])


for report in (c, k):
    check(sorted(report['order']) == sorted(['demanded'] + ['high%d' % i for i in range(2)] + ['replay%d' % i for i in range(4)] +
                                            ['warmup%d' % i for i in range(6)]), 'every queued compile ran once')
    check(inversions(report['order'], 'high', 'replay') <= slack and inversions(report['order'], 'high', 'warmup') <= slack,
          'high priority compiles first: ' + str(report['order']))
    check(report['order'].index('demanded') <= report['workers'] + 1, 'the demanded compile is taken at once: ' + str(report['order']))
check(inversions(c['order'], 'warmup', 'replay') <= slack, 'control: recorded states run after the speculative warm-ups: ' + str(c['order']))
check(inversions(k['order'], 'replay', 'warmup') <= slack, 'candidate: recorded states run before the speculative warm-ups: ' + str(k['order']))
check([n for n in k['order'] if n.startswith('replay')] == ['replay%d' % i for i in range(4)] or c['workers'] > 1, 'recorded states keep their order')
check(c['cancelled'] == k['cancelled'] == 10 and c['ranAfterStop'] == k['ranAfterStop'] == 0, 'a cancellation drains both queues')
check(c['joined'] is False and c['computeCompiles'] == 2, 'control: the dispatch creates the pipeline its warm-up also creates')
check(k['joined'] is True and k['computeCompiles'] == 1 and k['computePipeline'] is True, 'candidate: the dispatch joins the warm-up, one creation')
check(k['dispatchMs'] < 1000 and c['dispatchMs'] < 1000, 'the dispatch obtains its pipeline in one compile time')
check(c['otherJoined'] is False and k['otherJoined'] is False, 'a key without a warm-up is not joined')
check(c['briefAvailable'] is False and k['briefAvailable'] is True, 'the short wait exists in the candidate only')
check(k['quickObtained'] is True and k['quickMs'] < 40, 'a quick compile is obtained within the wait: ' + str(k['quickMs']))
check(k['slowObtained'] is False and k['slowMs'] < 100 and k['slowObtainedLater'] is True, 'a slow compile is left to its thread: ' + str(k['slowMs']))
check(k['briefPromotions'] == 0, 'the short wait promotes nothing')
check(k['allowanceIdle'] == 4 and k['allowanceSpent'] == 0 and 2 <= k['allowanceLater'] <= 4, 'the allowance: ' +
      str((k['allowanceIdle'], k['allowanceSpent'], k['allowanceLater'])))
check(k['waitText'].startswith('; skippable draws that waited briefly 2 (obtained in time 1, '), 'the journal text: ' + str(k['waitText']))

control, candidate = texts['control'], texts['candidate']
pipeline = candidate[VULKAN + 'PipelineBase.cs']
create = member(pipeline, 'private bool CreatePipeline(')
check('failOnCompileRequired: true' not in create and 'failOnCompileRequired: true' in member(control[VULKAN + 'PipelineBase.cs'], 'private bool CreatePipeline('),
      'a skippable draw no longer creates on the render thread')
i = create.index
check(i('_program.QueueBackgroundGraphicsPipeline(') < i('SkippableDrawWait.Take()') < i('_program.TryWaitBrieflyForQueuedGraphicsPipeline(') <
      i('RenderStageTimer.AsyncQueuedSkips++;') < i('else if (!_program.TryWaitForBackgroundGraphicsPipeline('),
      'queued, waited for within the allowance, then skipped; a draw that must wait still waits')
check(create.count('_newState.CreateGraphicsPipeline(') == member(control[VULKAN + 'PipelineBase.cs'], 'private bool CreatePipeline(').count('_newState.CreateGraphicsPipeline(') - 1,
      'one creation site removed, the others kept')
check('compileInBackground && (!info.FromCache || isCompute)' in candidate[VULKAN + 'VulkanRenderer.cs'], 'cached compute programs compile at high priority')
check('highPriority: false, prebuild: true)' in candidate[VULKAN + 'ShaderCollection.cs'], 'replays go to the prebuild queue')
scheduler = candidate[VULKAN + 'BackgroundCompilationScheduler.cs']
check('_highPriorityQueue.First ?? _prebuildQueue.First ?? _lowPriorityQueue.First' in scheduler and
      scheduler.count('Drain(_prebuildQueue, pending);') == 1, 'the prebuild queue is taken between the two and drained')

inputs = ['build-utils/melonx/adapt_render_thread_compile_relief.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_render_thread_compile_relief_test.py', 'test/melonx_render_thread_compile_relief/Double.cs',
          'test/melonx_render_thread_compile_relief/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyBuilt=True, nativePipelineDouble=True,
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host scheduler order and waits with compile doubles; PipelineBase.CreatePipeline is bound by text and by '
                          'the production build, not executed. Stutter on an iPhone is read from the render-stage lines of a device run.')
out = ROOT / 'dist/melonx/render-thread-compile-relief-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
