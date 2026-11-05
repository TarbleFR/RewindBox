#!/usr/bin/env python3
"""SetProgram without waiting for the warm-up of a program translated during play (adapt_setprogram_warmup), before and after.

Usage: melonx_setprogram_warmup_test.py <Core 658 prepared MeloNX tree>
       melonx_setprogram_warmup_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the Core 658 preparation, candidate adds the adapter (applied to a copy; the given tree is never modified).
Static: the candidate is the control plus exactly the adapter's replacements (undone, every file of the tree equals the
control's bytes); async compile skip, CanBindWhileIncomplete, the draw/dispatch callers of CreatePipeline, the GAL
SetProgramCommand/ProgramQueue and the main-cache lock are unchanged; the Library sets the policy per session from
the Hogwarts flag, on the Vulkan renderer, before it is wrapped by the threaded renderer. Builds: each variant's
production Ryujinx.Graphics.Vulkan assembly and the candidate's Ryujinx.Library.
Executed (test/melonx_setprogram_warmup): the REAL members of each variant (VulkanRenderer.CreateProgram, the
ShaderCollection constructors and compile/link/warm-up/pipeline-table members, Shader's constructors and waits,
PipelineBase.SetProgram and CreatePipeline, BackgroundCompilationScheduler, HashTableSlim, SpecData, the GAL ProgramQueue,
SetProgramCommand, CreateProgramCommand, SourceProgramRequest, TableRef) compiled with doubles whose shader module and
pipeline compiles are timed sleeps, on 6 logical processors (the iPhone's one pipeline worker). Every code line the
adapter adds to the Vulkan files must be in that compiled set. Scenarios: the 658 miss (warm-up TriangleList, draw
TriangleStrip with restart), the draw that needs the warm-up's pipeline, a burst of programs created ahead (match and
mismatch), a compute program, the GPU thread's save poll, teardown cancellation, warm-up and module failures; the policy
off, a cached program and async shaders on must behave as the control. No device; no claim on iPhone timings.
Writes dist/melonx/setprogram-warmup-checks.json.
"""
from pathlib import Path
import difflib, hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_setprogram_warmup', _HOLD)
import adapt_setprogram_warmup  # noqa: E402
from adapt_setprogram_warmup import apply, BASELINE  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
GAL = 'src/Ryujinx.Graphics.GAL/'
COLLECTION, RENDERER, PIPELINE = VULKAN + 'ShaderCollection.cs', VULKAN + 'VulkanRenderer.cs', VULKAN + 'PipelineBase.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
PIPELINE_MS = 400
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature, start_at=None):
    """The member whose declaration holds `signature`, from the start of its first line (or of `start_at`, searched
    backwards from it) through the brace that closes its body."""
    position = text.index(signature)
    assert text.count(signature) == 1, signature
    start = text.rindex(start_at, 0, position) if start_at else text.rindex('\n', 0, position) + 1
    depth, index = 0, text.index('{', position)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def region(text, first, last):
    """From the line starting with `first` through the end of the line starting with `last` (each unique)."""
    assert text.count(first) == 1 and text.count(last) == 1, (first, last)
    start = text.index(first)
    end = text.index('\n', text.index(last, start)) + 1
    return text[start:end]


def run(command, cwd, timeout=2400, extra=None):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=dict(environment, **(extra or {})), cwd=cwd)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    return result


def tree_digests(tree):
    return {p.relative_to(tree).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(tree.rglob('*')) if p.is_file() and not ({'bin', 'obj', '.git'} & set(p.relative_to(tree).parts))}


USINGS = '''using Ryujinx.Common.Logging;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Silk.NET.Vulkan;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Runtime.ExceptionServices;
using System.Threading;
using System.Threading.Tasks;
'''
COLLECTION_MEMBERS = [
    'private async Task BackgroundShaderModuleCompilation()', 'private async Task BackgroundCompilation()',
    'public void PromoteBackgroundCompilation()', 'private void RegisterInitialBackgroundPipelineTask(Task task)',
    'private void ClearInitialBackgroundPipelineTask()', 'private static SpecData GetInitialComputePipelineKey()',
    'private PipelineUid GetInitialGraphicsPipelineKey()', 'private string DescribeMissContext()',
    'private string DescribeInitialKeyDifference(ref PipelineUid drawKey)', 'private Task RunBackgroundPipelineCompile(',
    'private void LogBackgroundPipelineFailure(', 'private async Task<bool> WaitForShaderModuleCompilation()',
    'private void EnsureShadersReadyLegacy()', 'private bool EnsureShadersReady(bool blocking)', 'public bool TryGetInfos(',
    'public bool WaitForShaderModules(int timeoutMs)', 'public PipelineShaderStageCreateInfo[] GetInfos()',
    'protected DisposableRenderPass CreateDummyRenderPass()', 'public void CreateBackgroundComputePipeline(',
    'public void CreateBackgroundGraphicsPipeline(', 'public ProgramLinkStatus CheckProgramLink(bool blocking)',
    'public byte[] GetBinary()', 'public Auto<DisposablePipeline> AddComputePipeline(',
    'public Auto<DisposablePipeline> AddGraphicsPipeline(', 'public bool TryGetComputePipeline(',
    'public bool TryGetGraphicsPipeline(', 'public bool TryWaitForBackgroundGraphicsPipeline(',
    'public bool QueueBackgroundComputePipeline(', 'private async Task CompileQueuedComputePipeline(',
    'private void AddBackgroundComputePipelineFailure(', 'public bool QueueBackgroundGraphicsPipeline(',
    'private async Task CompileQueuedGraphicsPipeline(', 'private void AddBackgroundGraphicsPipelineFailure(',
    'public void CancelPendingWarmUp()', 'public void WaitForBackgroundCompilation()', 'private static bool CancelledByTeardown(',
    'private void WaitForBackgroundPipelineQueue()']
BASE_CTOR = '        public ShaderCollection(\n            VulkanRenderer gd,\n            Device device,\n            ShaderSource[] shaders,'
STATE_CTOR = '        public ShaderCollection(\n            VulkanRenderer gd,\n            Device device,\n            ShaderSource[] sources,'
LAYOUT_CUT = ('            bool usePushDescriptors = !isMinimal &&', '            _compileTask = compileInBackground && startBackgroundTask')


def extract(work):
    """The real members of a variant, as compilable partial classes (Extracted.cs), plus the real whole files."""
    collection = (work / COLLECTION).read_text(encoding='utf-8-sig')
    renderer = (work / RENDERER).read_text(encoding='utf-8-sig')
    pipeline = (work / PIPELINE).read_text(encoding='utf-8-sig')
    shader = (work / (VULKAN + 'Shader.cs')).read_text(encoding='utf-8-sig')
    spec = (work / (VULKAN + 'SpecInfo.cs')).read_text(encoding='utf-8-sig')

    header_start = collection.index('    class ShaderCollection : IProgram\n    {\n') + len('    class ShaderCollection : IProgram\n    {\n')
    header = collection[header_start:collection.index(BASE_CTOR)]
    base = member(collection, BASE_CTOR)
    cut = base[base.index(LAYOUT_CUT[0]):base.index(LAYOUT_CUT[1])]
    check('_plce = gd.PipelineLayoutCache.GetOrCreate(' in cut and '            Stages = stages;\n' in cut and '_compileTask' not in cut,
          'the base constructor part left out is the descriptor layout part only')
    base = base.replace(cut, '            _plce = new PipelineLayoutCacheEntry(); // RewindBox fixture: no descriptor layout\n'
                                  '            Stages = stages;\n\n')
    members = [header, base, member(collection, STATE_CTOR)]
    signatures = COLLECTION_MEMBERS + (['public bool TryWaitForBackgroundComputePipeline('] if 'TryWaitForBackgroundComputePipeline(' in collection else [])
    members += [member(collection, s) for s in signatures]
    shader_members = [region(shader, '        private readonly VulkanRenderer _gd;', '        public readonly Task CompileTask;')]
    shader_members += [member(shader, s) for s in ('public unsafe Shader(Vk api, Device device, ShaderSource shaderSource)',
                                                   'public unsafe Shader(VulkanRenderer gd, Device device, ShaderSource shaderSource,',
                                                   'public void WaitForCompile()', 'public void PromoteCompilation()')]
    renderer_members = ['        private ExceptionDispatchInfo _backgroundPipelineFailure;\n',
                        member(renderer, 'internal void RecordBackgroundPipelineFailure('),
                        member(renderer, 'internal void ThrowIfBackgroundPipelineFailed()')]
    policy = re.search(r'\n((?:        //[^\n]*\n)*        public bool DetachPlayTimeWarmUps \{ get; set; \}\n)', renderer)
    renderer_members.append((policy.group(1) + '\n' if policy else '') + member(renderer, 'public IProgram CreateProgram('))
    pipeline_members = [member(pipeline, s) for s in ('public void SetProgram(IProgram program)', 'private bool CreatePipeline(',
                                                      'private bool CanSkipForBackgroundCompile(', 'private bool UpdateProgramStagesIfReady(')]
    text = (USINGS + '\nnamespace Ryujinx.Graphics.Vulkan\n{\n'
            + '    partial class ShaderCollection : IProgram\n    {\n' + '\n\n'.join(members) + '\n    }\n\n'
            + '    partial class Shader\n    {\n' + '\n\n'.join(shader_members) + '\n    }\n\n'
            + '    partial class VulkanRenderer\n    {\n' + '\n\n'.join(renderer_members) + '\n    }\n\n'
            + '    partial class PipelineBase\n    {\n' + '\n\n'.join(pipeline_members) + '\n    }\n\n'
            + member(spec, 'readonly struct SpecData : IRefEquatable<SpecData>') + '\n}\n')
    whole = {VULKAN + 'BackgroundCompilationScheduler.cs', VULKAN + 'HashTableSlim.cs', GAL + 'ShaderInfo.cs',
             GAL + 'Multithreading/Resources/ProgramQueue.cs', GAL + 'Multithreading/Resources/Programs/IProgramRequest.cs',
             GAL + 'Multithreading/Resources/Programs/SourceProgramRequest.cs', GAL + 'Multithreading/Commands/SetProgramCommand.cs',
             GAL + 'Multithreading/Commands/Renderer/CreateProgramCommand.cs', GAL + 'Multithreading/Commands/IGALCommand.cs',
             GAL + 'Multithreading/Model/TableRef.cs'}
    return text, sorted(whole)


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

# The adapter's replacements, recorded on a scratch copy: the candidate must be the control with exactly these.
replacements = []
with tempfile.TemporaryDirectory(prefix='melonx-setprogram-warmup-record-') as scratch:
    for name in BASELINE:
        (Path(scratch) / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, Path(scratch) / name)
    original_once = adapt_setprogram_warmup.once

    def recording_once(path, old, new):
        replacements.append((path.relative_to(scratch).as_posix(), old, new))
        original_once(path, old, new)

    adapt_setprogram_warmup.once = recording_once
    try:
        apply(Path(scratch))
    finally:
        adapt_setprogram_warmup.once = original_once
check(len(replacements) == 12 and all(old in new for name, old, new in replacements if name in (LIBRARY, PIPELINE)),
      'twelve local replacements; the Library and PipelineBase ones keep their anchor (pure insertions)')

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
texts, reports, digests, assemblies, compiled = {}, {}, {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-setprogram-warmup-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(p.relative_to(work).as_posix() for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                later = files_edited_later('adapt_setprogram_warmup')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
        digests[variant] = tree_digests(work)
        check(run([DOTNET, 'build', str(work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release', '-nologo', '-m:1',
                   '-p:NuGetAudit=false'], work).returncode == 0, variant + ' production Vulkan assembly builds')
        built = sorted((work / VULKAN / 'bin').rglob('Ryujinx.Graphics.Vulkan.dll'))
        check(len(built) == 1, variant + ': one production Ryujinx.Graphics.Vulkan.dll')
        assemblies[variant] = hashlib.sha256(built[0].read_bytes()).hexdigest()
        if variant == 'candidate':
            check(run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo', '-m:1',
                       '-p:NuGetAudit=false'], work).returncode == 0, 'candidate Ryujinx.Library builds (policy wiring)')
        print(variant + ': production assemblies built', flush=True)

        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        extracted, whole = extract(work)
        compiled[variant] = extracted
        (fixture / 'Extracted.cs').write_text(extracted)
        for relative in whole:
            shutil.copyfile(work / relative, fixture / ('Real.' + Path(relative).name))
        for name in ('Double.cs', 'Program.cs'):
            shutil.copyfile(ROOT / 'test/melonx_setprogram_warmup' / name, fixture / name)
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
            '<ImplicitUsings>disable</ImplicitUsings><NoWarn>CS0649;CS0414;CS0169;CS8321;CS0162;CS1998;CS0067</NoWarn>'
            '</PropertyGroup></Project>\n')
        check(run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'], fixture,
                  900).returncode == 0, variant + ': fixture of the real members builds')
        # Six logical processors: BackgroundCompilationScheduler then has the iPhone's one pipeline worker (cores / 4).
        result = run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant, str(PIPELINE_MS)], fixture, 900,
                     {'DOTNET_PROCESSOR_COUNT': '6'})
        check(result.returncode == 0, variant + ': fixture ran')
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

# --- Static: the candidate is the control plus exactly the adapter's replacements; nothing else in the tree changed.
control_texts, candidate_texts = texts['control'], texts['candidate']
undone = dict(candidate_texts)
for name, old, new in reversed(replacements):
    check(undone[name].count(new) == 1, 'replacement present once: ' + new[:60])
    undone[name] = undone[name].replace(new, old)
check(undone == control_texts, 'undoing the replacements gives the control')
check(sorted(n for n in digests['candidate'] if digests['candidate'][n] != digests['control'].get(n)) == sorted(BASELINE)
      and set(digests['candidate']) == set(digests['control']), 'no other file of the tree changed')
added = []
for name in (COLLECTION, RENDERER, PIPELINE):
    for line in difflib.unified_diff(control_texts[name].splitlines(), candidate_texts[name].splitlines(), lineterm='', n=0):
        if line.startswith('+') and not line.startswith('+++') and line[1:].strip() and not line[1:].strip().startswith('//'):
            added.append(line[1:])
compiled_lines = set(compiled['candidate'].splitlines())
check(added and all(line in compiled_lines for line in added), 'every code line the adapter adds to Vulkan is compiled and executed by the fixture: '
      + str([line for line in added if line not in compiled_lines][:3]))

renderer_c, renderer_k = control_texts[RENDERER], candidate_texts[RENDERER]
create = member(renderer_k, 'public IProgram CreateProgram(')
check('bool allowAsyncCompileSkip = info.EnableAsyncCompile && info.AllowAsyncCompileSkip;' in create and
      'bool playTimeWarmUp = DetachPlayTimeWarmUps && !info.EnableAsyncCompile && !info.FromCache && (info.State.HasValue || isCompute);' in create,
      'play-time warm-ups only with synchronous compilation; async compile skip unchanged (no draw skipped)')
collection_c, collection_k = control_texts[COLLECTION], candidate_texts[COLLECTION]
check('public bool CanBindWhileIncomplete => CompilesInBackground && AllowAsyncCompileSkip;' in collection_k,
      'CanBindWhileIncomplete unchanged: SetProgram still waits for the program (its modules)')
pipeline_c, pipeline_k = control_texts[PIPELINE], candidate_texts[PIPELINE]
for signature in ('private bool PrepareGraphicsDraw()', 'private bool PrepareComputeDispatch(bool allowAsyncSkip)',
                  'private bool CanSkipForBackgroundCompile(', 'public void SetProgram(IProgram program)', 'public void DispatchCompute('):
    check(member(pipeline_c, signature) == member(pipeline_k, signature), 'unchanged: ' + signature)
draw = member(pipeline_k, 'private bool PrepareGraphicsDraw()')
check('bool requiresCompletePipeline = canSkipForBackgroundCompile &&' in draw and
      'CreatePipeline(\n                    PipelineBindPoint.Graphics,\n                    allowAsyncSkip: true,\n'
      '                    waitForBackgroundGraphicsPipeline: requiresCompletePipeline);' in draw and
      'CreatePipeline(PipelineBindPoint.Compute, allowAsyncSkip);' in member(pipeline_k, 'private bool PrepareComputeDispatch(bool allowAsyncSkip)') and
      'RecreateComputePipelineIfNeeded(allowAsyncSkip: true)' in member(pipeline_k, 'public void DispatchCompute('),
      'the fixture calls CreatePipeline as a draw and a dispatch do (no skip without async compile skip)')
check('shader.CancelPendingWarmUp();' in member(renderer_k, 'public unsafe void Dispose()'), 'teardown cancels pending detached warm-ups (now these too)')
state = (SOURCE / (VULKAN + 'PipelineState.cs')).read_text(encoding='utf-8-sig')
check(state.count('if (gd.PipelineCacheManager.IsMainCache(cache))\n                {\n                    lock (gd.PipelineCreationLock)') == 1 and
      'gd.PipelineCreationLock.Enter();' in state and 'result = gd.Api.CreateGraphicsPipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle);' in state,
      'PipelineState: only the main cache is built under PipelineCreationLock (as the double)')
for relative in ('Multithreading/Commands/SetProgramCommand.cs', 'Multithreading/Resources/ProgramQueue.cs'):
    check(digests['control'][GAL + relative] == digests['candidate'][GAL + relative], 'GAL unchanged: ' + relative)
library = candidate_texts[LIBRARY]
context = member(library, 'private static Switch InitializeEmulationContext(')
line = '            if (renderer is VulkanRenderer warmUpVulkan) warmUpVulkan.DetachPlayTimeWarmUps = hogwarts;'
check(context.count(line) == 1 and context.index('bool hogwarts = EmbeddedIsHogwarts(options.InputPath);') < context.index(line)
      < context.index('renderer = renderer.TryMakeThreaded(options.BackendThreading);'),
      'the Library sets the policy per session from the Hogwarts flag, on the Vulkan renderer, before threading')
check(library.count('DetachPlayTimeWarmUps') == 1, 'the policy is set in one place')

# --- Executed: control vs candidate on the same doubles.
c, k = reports['control'], reports['candidate']
P = PIPELINE_MS
check(c['hasPolicyProperty'] is False and k['hasPolicyProperty'] is True, 'only the candidate has the policy')
check(c['pipelineWorkers'] == k['pipelineWorkers'] == 1 and c['processors'] == 6, 'one pipeline worker, as on a six-core iPhone')

cm, km = c['mismatch'], k['mismatch']
check(cm['compilesInBackground'] is False and km['compilesInBackground'] is True and cm['canBindWhileIncomplete'] is False
      and km['canBindWhileIncomplete'] is False, '658 miss: the play-time program moves to the scheduler, still not bindable while incomplete')
# bindMs: CreateProgramCommand + SetProgramCommand on the render thread. In the control a warm-up whose modules are
# already compiled runs synchronously in the constructor (BackgroundCompilation's await completes inline), otherwise
# SetProgram waits for it; either way the render thread pays it before binding.
check(cm['setProgramReturnedBeforeWarmUpEnd'] is False and cm['bindMs'] >= 0.8 * P,
      'control: binding waits for the warm-up the draw does not use: ' + str(cm['bindMs']))
check(km['setProgramReturnedBeforeWarmUpEnd'] is True and km['bindMs'] < 0.25 * P and km['renderThreadWarmUps'] == 0,
      'candidate: SetProgram returns before that warm-up ends, never compiled on the render thread: ' + str(km['bindMs']))
check(cm['drawn'] and km['drawn'] and cm['boundOwnPipeline'] and km['boundOwnPipeline'], 'the draw is made with its own pipeline in both')
check(cm['drawBuildStartedBeforeWarmUpEnd'] is False and km['drawBuildStartedBeforeWarmUpEnd'] is True,
      'candidate: the draw builds its pipeline while the warm-up compiles (no wait for it)')
check(cm['warmUp']['cache'] == 'main' and km['warmUp']['cache'].startswith('worker') and km['drawBuild']['cache'] == 'main'
      and km['drawBuild']['thread'] == 'render', 'candidate: the warm-up on a worker cache (outside PipelineCreationLock), the draw on main')
check(cm['toFirstDrawMs'] >= 1.7 * P and km['toFirstDrawMs'] <= 1.35 * P,
      'time to the first draw: control warm-up + own build, candidate own build only: %s / %s' % (cm['toFirstDrawMs'], km['toFirstDrawMs']))
check(cm['secondDrawn'] and km['secondDrawn'] and cm['secondBoundWarmUp'] and km['secondBoundWarmUp'] and cm['compiles'] == km['compiles'] == 2,
      'a later draw with the warm-up key binds the warm-up pipeline; two compiles in both')
difference = ' Differs from warm-up: Topology warm-up=0 draw=1; PrimitiveRestartEnable warm-up=False draw=True'
check(len(cm['missLines']) == 1 and len(km['missLines']) == 1 and difference in cm['missLines'][0] and difference in km['missLines'][0]
      and km['missLines'][0].endswith('(pipelines already built for this program: 0)'),
      'the miss diagnostic is kept (once, same differing fields; 0 pipelines: the draw came before the warm-up)')

cx, kx = c['match'], k['match']
check(cx['drawn'] and kx['drawn'] and cx['boundWarmUp'] and kx['boundWarmUp'] and not kx['skipped'] and cx['compiles'] == kx['compiles'] == 1,
      'a draw needing the warm-up pipeline gets it, once compiled, never skipped')
check(kx['setProgramReturnedBeforeWarmUpEnd'] is True and kx['drawEndedAfterWarmUpEnd'] is True and cx['setProgramReturnedBeforeWarmUpEnd'] is False
      and kx['renderThreadWarmUps'] == 0, 'candidate: SetProgram does not wait, the draw waits for that pipeline')
check(kx['toFirstDrawMs'] <= cx['toFirstDrawMs'] + 0.25 * P and cx['missLines'] == kx['missLines'] == 0,
      'no regression to the first draw when the key matches: %s / %s' % (cx['toFirstDrawMs'], kx['toFirstDrawMs']))

for scenario in ('burstMatch', 'burstMismatch'):
    cb, kb = c[scenario], k[scenario]
    check(cb['drawn'] and kb['drawn'] and cb['boundNeeded'] and kb['boundNeeded'] and cb['compiles'] == kb['compiles'],
          scenario + ': drawn with the needed pipeline, same compiles')
    check(cb['neededServedBeforeQueuedWarmUps'] >= 1 and kb['neededServedBeforeQueuedWarmUps'] == 0,
          scenario + ': the needed pipeline no longer waits behind warm-ups of programs created ahead')
    check(cb['mainCacheWarmUps'] >= 3 and kb['mainCacheWarmUps'] == 0, scenario + ': no warm-up competes on the main-cache lock')
    check(cb['toFirstDrawMs'] >= 1.5 * P and kb['toFirstDrawMs'] <= 1.4 * P and kb['renderThreadWarmUps'] == 0,
          scenario + ': time to the first draw %s / %s' % (cb['toFirstDrawMs'], kb['toFirstDrawMs']))
check('Demand' in next(r['thread'] for r in k['burstMatch']['records'] if r['key'] == 'graphics topology 13'),
      'burst: the demanded warm-up runs on the demand worker, ahead of the queued ones')

cc, kc = c['compute'], k['compute']
check(cc['dispatched'] and kc['dispatched'] and cc['boundCompiled'] and kc['boundCompiled'] and cc['compiles'] == kc['compiles'] == 1,
      'compute: dispatched with the warm-up pipeline, compiled once (no second compile on the main cache)')
check(cc['setProgramReturnedBeforeWarmUpEnd'] is False and kc['setProgramReturnedBeforeWarmUpEnd'] is True and kc['bindMs'] < 0.25 * P
      and kc['renderThreadWarmUps'] == 0, 'compute: SetProgram no longer waits for the warm-up: %s / %s' % (cc['bindMs'], kc['bindMs']))
check(kc['toFirstDispatchMs'] <= cc['toFirstDispatchMs'] + 0.25 * P, 'compute: no regression to the first dispatch')

check(c['savePoll']['duringWarmUp'] == 'Incomplete' and k['savePoll']['duringWarmUp'] == 'Success'
      and c['savePoll']['after'] == k['savePoll']['after'] == 'Success', 'GPU save poll: complete once the modules exist')
check(c['cancel']['warmUpCompiled'] == 1 and k['cancel']['warmUpCompiled'] == 0 and k['cancel']['failureLines'] == 0,
      'teardown/dispose cancels a pending play-time warm-up quietly')
cf, kf = c['failures'], k['failures']
check(cf['warmUpFailedDrawn'] and kf['warmUpFailedDrawn'] and cf['warmUpFailedBoundSecondBuild'] and kf['warmUpFailedBoundSecondBuild'],
      'a failed warm-up: the draw builds and binds its pipeline in both')
check(cf['moduleFailedLink'] == kf['moduleFailedLink'] == 'Failure' and cf['moduleFailedDrawn'] is False and kf['moduleFailedDrawn'] is False
      and cf['moduleFailedCompiles'] == kf['moduleFailedCompiles'] == 0, 'a failed module: same link failure and no draw in both')

# Gates: the policy off, cached programs and async shaders behave as the control.
ko, co = k['mismatchPolicyOff'], c['mismatchPolicyOff']
check(ko['compilesInBackground'] is False and ko['setProgramReturnedBeforeWarmUpEnd'] is False and ko['warmUp']['cache'] == 'main'
      and ko['drawBuildStartedBeforeWarmUpEnd'] is False and co['setProgramReturnedBeforeWarmUpEnd'] is False and len(ko['missLines']) == 1,
      'policy off (other titles): the delivered path')
check(k['computePolicyOff']['compilesInBackground'] is False and k['computePolicyOff']['setProgramReturnedBeforeWarmUpEnd'] is False,
      'policy off: compute as delivered')
for scenario in ('cachedMatch', 'asyncMatch'):
    for field in ('compilesInBackground', 'canBindWhileIncomplete', 'setProgramReturnedBeforeWarmUpEnd', 'drawn', 'boundWarmUp', 'compiles', 'missLines'):
        check(c[scenario][field] == k[scenario][field], scenario + ' unchanged: ' + field)
check(k['cachedMatch']['setProgramReturnedBeforeWarmUpEnd'] is True and k['asyncMatch']['setProgramReturnedBeforeWarmUpEnd'] is False,
      'cached programs were already detached; async-shader programs keep their wait')
check(c['cachedCompute']['compilesInBackground'] == k['cachedCompute']['compilesInBackground'] is True
      and c['cachedCompute']['dispatched'] and k['cachedCompute']['dispatched'], 'cached compute unchanged')

inputs = ['build-utils/melonx/adapt_setprogram_warmup.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_setprogram_warmup_test.py',
          'test/melonx_setprogram_warmup/Double.cs', 'test/melonx_setprogram_warmup/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
summary = {v: {s: {f: reports[v][s][f] for f in ('bindMs', 'setProgramMs', 'toFirstDrawMs', 'toFirstDispatchMs') if f in reports[v][s]}
               for s in ('mismatch', 'match', 'burstMatch', 'burstMismatch', 'compute')} for v in reports}
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyBuilt=True, productionLibraryAssemblyBuilt=True,
               productionVulkanAssemblies=assemblies, pipelineCompileDoubleMs=P, timings=summary, reports=reports,
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host execution of the real members with a timed compile double (no Vulkan, no MoltenVK, no Metal '
                          'compiler). It proves where the render thread waits, not how long Metal compiles take on the iPhone, '
                          'whether MTLCompilerService runs concurrent compiles in parallel, nor the memory of the worker caches; '
                          'those need a device run (render-stage SetProgram ms, syncpoint timeouts, pipeline build lines).')
out = ROOT / 'dist/melonx/setprogram-warmup-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
