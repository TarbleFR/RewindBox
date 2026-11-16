#!/usr/bin/env python3
"""adapt_draw_wait_lanes on the final preparation, against its predecessor as control.

Usage: melonx_draw_wait_lanes_test.py <predecessor preparation> [--candidate-source <final preparation containing the adapter>]

IPA 760 / Core 127b72b9, Super Smash Bros. Ultimate (pid 26654, 1 207 s): 253 first compiles of programs new to the
device, 98 ms each in Metal's compiler, each waited for in full by the render thread (25.7 s; 28.2 of the 28.8 s of
presentation gaps of 50 ms or more are in the windows that hold them), one after the other when a frame brings several
(17.1 s of the gap time is in gaps of 150 ms or more).

Static: the candidate is the control plus exactly the adapter's fourteen replacements in five files, and nothing else in
the tree changes; the scheduler's Schedule, TryCancel, Enqueue, WorkerLoop, Dispose and its work item are the control's,
TryTake and Promote are the control's plus one block each; both draw callers of TryWaitForBackgroundGraphicsPipeline pass an
infinite timeout; the production Vulkan assembly (and the GAL it references) builds for both.
Executed (test/melonx_draw_wait_lanes): the REAL BackgroundCompilationScheduler.cs and the REAL GAL ProgramQueue.cs of each
variant, whole, with doubles whose pipeline compile is a timed sleep on the scheduler's own threads, on 6 logical
processors (the iPhone's one pipeline worker and its demand thread). A render thread and a GPU thread follow the
production order: the GPU thread queues a program every 6 ms, the render thread runs each program's CreateProgram command
and ProcessQueue, waits 4 ms for its modules (the worker takes the warm-up meanwhile, as measured in IPA 740), then
promotes the warm-up and waits for it as a draw does. Scenarios: a frame with five new programs, with two, with one; the
same with the promotion before any thread took the warm-up; no draw waiting; a compile demanded while both threads are
busy; an awaited compile that runs on the demand thread; an awaited compile that is not queued yet; a thread that is not
the render thread; a failed compile; a creation that asks again from inside itself; one long wait with nothing queued.
Not executed here: the two call sites in ShaderCollection.cs (the setprogram-warmup gate runs the final preparation's
members, these two included, on its own doubles), Metal's compiler, and anything on a device. Whether Metal compiles two
pipelines at once as fast as one is read from the next IPA's journals.
Writes dist/melonx/draw-wait-lanes-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_draw_wait_lanes', _HOLD)
import adapt_draw_wait_lanes as adapter  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
GAL = 'src/Ryujinx.Graphics.GAL/'
DOTNET = os.environ.get('DOTNET', 'dotnet')
COMPILE_MS = 200
WORKER, DEMAND = 'Vulkan Pipeline Compile 0', 'Vulkan Pipeline Demand Compile'
TEXT = re.compile(r'^; draws that waited for a compile (\d+) \((\d+\.\d) ms; programs created meanwhile (\d+), compiles started ahead (\d+)\)$')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def member(text, signature):
    """The member whose declaration holds `signature` (once), from the start of its line through its closing brace."""
    assert text.count(signature) == 1, signature
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def tree_digests(tree):
    return {p.relative_to(tree).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(tree.rglob('*')) if p.is_file() and not ({'bin', 'obj', '.git'} & set(p.relative_to(tree).parts))}


def counters(text):
    match = TEXT.match(text or '')
    check(match is not None, 'the journal clause has its form: ' + repr(text))
    return dict(waits=int(match.group(1)), ms=float(match.group(2)), created=int(match.group(3)), ahead=int(match.group(4)))


for name, expected in adapter.BASELINE.items():
    check(sha(SOURCE / name) == expected, 'the control is the adapter\'s pinned preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
texts, digests, reports, assemblies, executed = {}, {}, {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-draw-wait-lanes-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = adapter.apply(work)
            check(sorted(p.relative_to(work).as_posix() for p in changed) == sorted(adapter.BASELINE), 'the adapter edits its five files only')
            if FINAL_PREPARATION:
                check(files_edited_later('adapt_draw_wait_lanes') == set() or not files_edited_later('adapt_draw_wait_lanes'),
                      'no later adapter edits these files: the candidate is the final preparation')
                for name in adapter.BASELINE:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'the final preparation is the control plus the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
        digests[variant] = tree_digests(work)
        result = subprocess.run([DOTNET, 'build', str(work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release', '-nologo', '-m:1',
                                 '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ': the production Vulkan assembly builds (with the GAL it references)')
        built = sorted((work / VULKAN / 'bin').rglob('Ryujinx.Graphics.Vulkan.dll'))
        check(len(built) == 1, variant + ': one production Ryujinx.Graphics.Vulkan.dll')
        assemblies[variant] = sha(built[0])
        print(variant + ': production assembly built', flush=True)

        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        for relative in (adapter.SCHEDULER, adapter.QUEUE):
            shutil.copyfile(work / relative, fixture / ('Real.' + Path(relative).name))
            executed.setdefault(variant, {})[relative] = sha(fixture / ('Real.' + Path(relative).name))
        for name in ('Double.cs', 'Program.cs'):
            shutil.copyfile(ROOT / 'test/melonx_draw_wait_lanes' / name, fixture / name)
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><ImplicitUsings>disable</ImplicitUsings>'
            '<NoWarn>CS0649;CS0414;CS0169;CS8321</NoWarn>' + ('<DefineConstants>LANES</DefineConstants>' if variant == 'candidate' else '')
            + '</PropertyGroup></Project>\n')
        result = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                                capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ': the fixture of the two real files builds')
        # Six logical processors: BackgroundCompilationScheduler then has the iPhone's one pipeline worker (cores / 4).
        result = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant, str(COMPILE_MS)], capture_output=True,
                                text=True, timeout=900, env=dict(environment, DOTNET_PROCESSOR_COUNT='6'), cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ': the fixture ran')
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps({k: ({f: v[f] for f in v if f != 'records'} if isinstance(v, dict) else v) for k, v in reports[variant].items()}), flush=True)

# --- Static: the candidate is the control plus exactly the adapter's replacements.
control, candidate = texts['control'], texts['candidate']
check(len(adapter.PAIRS) == 14 and {name for name, old, new in adapter.PAIRS} == set(adapter.BASELINE), 'fourteen replacements in the five files')
undone = dict(candidate)
for name, old, new in reversed(adapter.PAIRS):
    check(undone[name].count(new) == 1, 'replacement present once: ' + new[:70])
    undone[name] = undone[name].replace(new, old)
check(undone == control, 'undoing the replacements gives the control')
check(set(digests['candidate']) == set(digests['control']) and
      sorted(n for n in digests['candidate'] if digests['candidate'][n] != digests['control'][n]) == sorted(adapter.BASELINE),
      'no other file of the tree changed, none added')
scheduler_c, scheduler_k = control[adapter.SCHEDULER], candidate[adapter.SCHEDULER]
for signature in ('public Task Schedule(Action<int> action, bool highPriority, bool demanded = false, Action<int> afterCompletion = null)',
                  'public bool TryCancel(Task task)', 'private void Enqueue(WorkItem item, bool demanded, bool highPriority)',
                  'private void WorkerLoop(int workerIndex, bool demandOnly)', 'private static void Drain(', 'private sealed class WorkItem',
                  'public Task SchedulePipelineCompile(', 'public Task ScheduleShaderCompile(', 'private static int GetBackgroundCompileThreadCount()'):
    check(member(scheduler_c, signature) == member(scheduler_k, signature), 'scheduler unchanged: ' + signature)
check(scheduler_c.count('public void Dispose()') == scheduler_k.count('public void Dispose()') == 2, 'the two Dispose members are there')
take_c, take_k = member(scheduler_c, 'private WorkItem TryTake(bool demandOnly)'), member(scheduler_k, 'private WorkItem TryTake(bool demandOnly)')
block = adapter.TAKE_NEW[adapter.TAKE_NEW.index('                // RewindBox (adapt_draw_wait_lanes)'):adapter.TAKE_NEW.index('                if (demandOnly)\n')]
check(take_k.replace(block, '') == take_c and block.count('demandOnly && _awaitedAtDraw is { IsCompleted: false } &&\n') == 1 and
      block.count('_promotedInFlight is { Completion.Task.IsCompleted: false } && _highPriorityQueue.First != null)') == 1,
      'TryTake is the control\'s plus one block, for the demand thread only, while a draw waits for a compile a thread runs')
promote_c, promote_k = member(scheduler_c, 'public void Promote(Task task)'), member(scheduler_k, 'public void Promote(Task task)')
recorded = adapter.PROMOTE_NEW[adapter.PROMOTE_NEW.index('                    // RewindBox (adapt_draw_wait_lanes)'):adapter.PROMOTE_NEW.index('                    if (_stopping ||\n')]
check(promote_k.replace(recorded, '') == promote_c and 'taken.Node == null' in recorded and scheduler_k.count('_promotedInFlight = ') == 2,
      'Promote is the control\'s plus the record of a compile promoted once taken; the end of the wait forgets it')
check('_pipelineQueue.BeginDrawWait(task);' in scheduler_k and '_shaderQueue.BeginDrawWait' not in scheduler_k, 'the pipeline queue only')
wait = member(scheduler_k, 'public void WaitForPipelineAtDraw(Task task)')
check(wait.index('RenderThreadPrograms.Bound)') < wait.index('task.Wait();') < wait.index('return;') < wait.index('_pipelineQueue.BeginDrawWait(task);')
      < wait.index('try') < wait.index('finally') < wait.index('_pipelineQueue.EndDrawWait(task);')
      and 'while (!task.Wait(DrawWaitSliceMs));' in wait and wait.count('task.Wait();') == 1
      and 'public const int DrawWaitSliceMs = %d;' % adapter.SLICE_MS in scheduler_k,
      'the wait: the plain Wait and nothing else off a bound render thread; on it, begun, sliced, ended in a finally')
collection_k, pipeline_k = candidate[adapter.COLLECTION], candidate[adapter.PIPELINE]
check('public bool CanBindWhileIncomplete => CompilesInBackground && AllowAsyncCompileSkip;' in collection_k, 'CanBindWhileIncomplete unchanged')
check(collection_k.count('_gd.BackgroundCompilationScheduler.WaitForPipelineAtDraw(task)') == 2 and
      'WaitForPipelineAtDraw(task);' in member(collection_k, 'public bool TryWaitForBackgroundGraphicsPipeline(') and
      'WaitForPipelineAtDraw(task);' in member(collection_k, 'public bool TryWaitForBackgroundComputePipeline('),
      'the two waits of a draw and of a dispatch call it, nothing else does')
check(len(re.findall(r'TryWaitForBackgroundGraphicsPipeline\(\s*ref key,\s*Timeout\.Infinite,', pipeline_k)) == 2
      and pipeline_k.count('TryWaitForBackgroundGraphicsPipeline(') == 2 and candidate[adapter.COLLECTION].count('TryWaitForBackgroundGraphicsPipeline(') == 1,
      'both draw callers wait without a bound (the sliced wait is theirs)')
check(member(control[adapter.PIPELINE], 'private bool CreatePipeline(') == member(pipeline_k, 'private bool CreatePipeline('),
      'the draw and dispatch path that obtains the pipeline is unchanged')
queue_c, queue_k = control[adapter.QUEUE], candidate[adapter.QUEUE]
check(member(queue_k, 'public void ProcessQueue()').replace('                    _created++; // RewindBox (adapt_draw_wait_lanes)\n', '') == member(queue_c, 'public void ProcessQueue()')
      and member(queue_c, 'public void WaitForProgram(ThreadedProgram program)') == member(queue_k, 'public void WaitForProgram(ThreadedProgram program)')
      and member(queue_c, 'public void EnsureProgramCreated(ThreadedProgram program)') == member(queue_k, 'public void EnsureProgramCreated(ThreadedProgram program)'),
      'ProcessQueue is the control\'s plus a count; the waits of SetProgram are unchanged')
threaded_k = candidate[adapter.THREADED]
loop = member(threaded_k, 'public void RunLoop(ThreadStart gpuLoop)')
check(loop.index('RenderThreadPrograms.Bind(Programs);') < loop.index('RenderLoop();') < loop.index('RenderThreadPrograms.Bind(null);') < loop.index('_renderLoopExited.Set();'),
      'the render thread is bound for the time of its loop and unbound in the finally, before the exit is signalled')

# --- Executed: control and candidate on the same doubles.
c, k = reports['control'], reports['candidate']
P = COMPILE_MS
check(c['processors'] == k['processors'] == 6 and c['pipelineWorkers'] == k['pipelineWorkers'] == 1, 'one pipeline worker, as on a six-core iPhone')
for scenario, count in (('burst', 5), ('pair', 2), ('single', 1), ('burstPromotedFirst', 5), ('pairPromotedFirst', 2)):
    for variant, r in (('control', c[scenario]), ('candidate', k[scenario])):
        where = scenario + ' (' + variant + '): '
        check(r['compiles'] == count and r['compiledOnce'] and r['notified'] == count, where + 'each pipeline is compiled once: ' + str(r['compiles']))
        check(r['createdOnce'] and r['createdOnRenderThread'] and r['createdInOrder'], where + 'each program is created once, by the render thread, in the queue\'s order')
        check(r['drawnInOrder'] and r['everyDrawAfterItsPipeline'], where + 'draws in order, none before its own pipeline exists')
        check(r['onDemandThread'] + r['onWorker'] == count and r['demandCache'] in ([], [1]), where + 'compiled by the worker or the demand thread, each in its own cache')
cb, kb = c['burst'], k['burst']
check(cb['onWorker'] == 5 and cb['overlappedMs'] == 0 and cb['totalMs'] >= 4.6 * P and cb['createdBeforeFirstDrawEnd'] == 1,
      'control, five new programs: created after each wait, compiled one after the other by the worker: %s ms' % cb['totalMs'])
check(kb['createdBeforeFirstDrawEnd'] == 5 and kb['onDemandThread'] >= 2 and kb['overlappedMs'] >= 1.5 * P and kb['totalMs'] <= 3.4 * P,
      'candidate, five new programs: all created during the first wait, two compiles at a time: %s ms' % kb['totalMs'])
burst_text = counters(kb['text'])
check(3 <= burst_text['waits'] <= 5 and burst_text['created'] == 4 and burst_text['ahead'] == kb['onDemandThread'] and counters(kb['textAgain']) == dict(waits=0, ms=0.0, created=0, ahead=0),
      'the journal clause counts the waits (a draw whose compile was started ahead may find it done), the programs created during them and '
      'the compiles started ahead, then starts again: ' + kb['text'])
check(c['pair']['totalMs'] >= 1.8 * P and k['pair']['totalMs'] <= 1.3 * P and k['pair']['overlappedMs'] >= 0.8 * P,
      'two new programs: %s ms, then %s ms' % (c['pair']['totalMs'], k['pair']['totalMs']))
check(abs(k['single']['totalMs'] - c['single']['totalMs']) <= 0.2 * P and k['single']['totalMs'] >= 0.95 * P and counters(k['single']['text'])['ahead'] == 0,
      'one new program: the wait is the compile, as before (%s / %s ms)' % (c['single']['totalMs'], k['single']['totalMs']))
for scenario in ('burstPromotedFirst', 'pairPromotedFirst'):
    check(k[scenario]['totalMs'] <= c[scenario]['totalMs'] + 0.15 * P, scenario + ': never longer than the control (%s / %s ms)' % (c[scenario]['totalMs'], k[scenario]['totalMs']))
check(k['burstPromotedFirst']['totalMs'] <= 3.4 * P and k['pairPromotedFirst']['totalMs'] <= 1.3 * P,
      'the promotion before any thread took the warm-up: the same overlap (%s, %s ms)' % (k['burstPromotedFirst']['totalMs'], k['pairPromotedFirst']['totalMs']))

check(c['reserved']['threads'] == k['reserved']['threads'] == [WORKER] * 3 and counters(k['reserved']['text']) == dict(waits=0, ms=0.0, created=0, ahead=0),
      'no draw waits: the demand thread takes no high priority compile')
cp, kp = c['precedence'], k['precedence']
check(cp['aThread'] == kp['aThread'] == WORKER and cp['bThread'] == WORKER and not cp['bStartedDuringWait'] and kp['bThread'] == DEMAND and kp['bStartedDuringWait'],
      'a draw waits for a compile the worker runs: the demand thread starts the next one (control: it waits)')
check(cp['yBeforeC'] and kp['yBeforeC'] and kp['yStartAfterFirstEndMs'] <= 0.25 * P and counters(kp['text'])['ahead'] == 1,
      'a compile demanded while both threads are busy is taken by the first thread free, before the queued one: %s ms after it' % kp['yStartAfterFirstEndMs'])
check(cp['yStartAfterDemandMs'] <= 0.25 * P, 'control: the idle demand thread took that compile at once (the cost named by the adapter): %s / %s ms'
      % (cp['yStartAfterDemandMs'], kp['yStartAfterDemandMs']))
for r in (c['afterAwaited'], k['afterAwaited']):
    check(r['xThread'] == DEMAND and r['lThread'] == WORKER and r['hThread'] == WORKER and r['hAfterL'],
          'an awaited compile that runs on the demand thread: once it completes that thread takes no high priority compile')
check(counters(k['afterAwaited']['text'])['ahead'] == 0, 'none started ahead in that case')
for r in (c['notQueuedYet'], k['notQueuedYet']):
    check(r['xThread'] == DEMAND and r['tThread'] == WORKER and r['xStartAfterQueuedMs'] <= 0.25 * P,
          'a draw whose compile is not queued yet: the demand thread stays free and takes it at once (%s ms after it is queued)' % r['xStartAfterQueuedMs'])
check(counters(k['notQueuedYet']['text'])['ahead'] == 0, 'none started ahead in that case either')
u = k['unbound']
check(u['bound'] is False and u['created'] == 0 and u['requestCreated'] is False and u['completed'] is True and u['queuedThread'] == WORKER and
      counters(u['text']) == dict(waits=0, ms=0.0, created=0, ahead=0),
      'a thread that is not the bound render thread waits as before: nothing created, nothing started ahead, nothing counted')
f = k['failure']
check(f['thrown'] == f['expected'] == 'System.AggregateException < System.InvalidOperationException: compile failed' and f['queuedThread'] == WORKER,
      'a failed compile is thrown as Wait() throws it; the wait is over for the queue')
check(k['reentrant'] == dict(outer=2, nested=0, firstCreations=1, secondCreations=1), 'a creation that asks again from inside itself creates nothing more')
idle = k['idle']
check(idle['sliceMs'] == adapter.SLICE_MS and 1.9 * P <= idle['elapsedMs'] <= 2.3 * P and idle['processorMs'] <= 0.4 * idle['elapsedMs'],
      'a wait with nothing queued sleeps in slices: %s ms of processor for the whole process in %s ms' % (idle['processorMs'], idle['elapsedMs']))

inputs = ['build-utils/melonx/adapt_draw_wait_lanes.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_draw_wait_lanes_test.py',
          'test/melonx_draw_wait_lanes/Double.cs', 'test/melonx_draw_wait_lanes/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
summary = {v: {s: reports[v][s]['totalMs'] for s in ('burst', 'pair', 'single', 'burstPromotedFirst', 'pairPromotedFirst')} for v in reports}
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'predecessorPreparation',
               postimages={name: sha(FINAL_SOURCE / name) for name in adapter.BASELINE} if FINAL_PREPARATION else {},
               sdk=sdk, physicalDeviceTested=False, sourceBaseline=adapter.BASELINE, productionVulkanAssemblyBuilt=True,
               productionVulkanAssemblies=assemblies, executedWholeFiles=executed, pipelineCompileDoubleMs=P, timingsMs=summary,
               queuedProgramsCreatedDuringTheWait=True, compilesOverlapDuringTheWait=True, noDrawBeforeItsPipeline=True,
               everyPipelineCompiledOnce=True, demandedCompilesKeepPrecedence=True, demandThreadReservedWithoutDrawWait=True,
               singleCompileWaitUnchanged=True, awaitedCompileNotQueuedLeavesDemandThreadFree=True,
               plainWaitOffTheRenderThread=True, callSitesExecutedHere=False, reports=reports,
               inputs={path: sha(ROOT / path) for path in inputs},
               limitation='Host execution of the real scheduler and program queue with a timed compile double (no Vulkan, no MoltenVK, '
                          'no Metal compiler). It proves which compiles run during a draw\'s wait and that no draw precedes its '
                          'pipeline, not that Metal compiles two pipelines at once as fast as one, nor how often a frame of the '
                          'game brings several new programs; those are read on a device (render-stage line, build journal, gaps). '
                          'The two call sites in ShaderCollection.cs are run by the setprogram-warmup gate\'s final variant.')
out = ROOT / 'dist/melonx/draw-wait-lanes-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, timingsMs=summary)))
