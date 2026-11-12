#!/usr/bin/env python3
"""adapt_build_journal_load_wait on the final preparation, against the Core 741 preparation as control.

Usage: melonx_build_journal_load_wait_test.py <control> [--candidate-source <final preparation containing the adapter>]

Diagnostics only: the pipeline build journal takes a worker creation's time without its wait for the main cache's
background load, and nothing for a creation the main cache served. Required:
 1. PipelineState.cs only; the replacements add the timing members and calls, and replace the journal's two time
    expressions only; the waits, the lookups, every vkCreate*Pipelines call and the performance phases are the control's;
 2. the production Ryujinx.Graphics.Vulkan assembly builds with no compiler warning in PipelineState.cs; drift is refused;
 3. executed (test/melonx_build_journal_load_wait/Program.cs, the candidate's production members): IPA 727's first worker
    creation of a launch (1 300 ms of load wait, then served by the main cache) has a journal time of 0 (the control's
    is its whole 1.3 s, a "compilation"); a worker that waited and then compiled for 900 ms is timed about 900 ms; a
    render-thread compilation keeps its time; a creation after a served one on the same thread is not taken as served;
    the first long wait is recorded once in the engine journal, with whether the main cache served it.
The clock is read, never waited on: tolerances of 25 ms bound the work between two reads. Writes
dist/melonx/build-journal-load-wait-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_build_journal_load_wait', _HOLD)
import adapt_build_journal_load_wait as adapter  # noqa: E402
from adapt_descriptor_updates import method  # noqa: E402

FIXTURE = ROOT / 'test/melonx_build_journal_load_wait'
DOTNET = os.environ.get('DOTNET', 'dotnet')
S = adapter.STATE
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


check(list(adapter.BASELINE) == [S] and all(p[0] == S for p in adapter.PAIRS), 'the adapter edits PipelineState.cs only')
check(sha(SOURCE / S) == adapter.BASELINE[S], 'control is the Core 741 preparation: ' + S)
control = read(SOURCE, S)
candidate = control
for _, old, new in adapter.PAIRS:
    check(control.count(old) == 1 and candidate.count(old) == 1, 'one site in the control: ' + old.strip()[:60])
    candidate = candidate.replace(old, new)
journal_old = '            double buildMs = System.Diagnostics.Stopwatch.GetElapsedTime(buildStart).TotalMilliseconds;\n'
journal_new = '            double buildMs = CompiledMs(buildStart); // ' + adapter.TAG + ': without the main load wait\n'
for _, old, new in adapter.PAIRS:
    if journal_old in old:
        check(new == old.replace(journal_old, journal_new), 'the journal\'s time expression only is replaced')
    elif old == adapter.LOOKUP_OLD:
        check(new.count(old) == 1 and new.index(old) > 0 and new.split(old)[1].startswith('            _servedByMain = hit;'),
              'the timing members are added before NoteMainCacheLookup, its first statements after its brace')
    else:
        check(''.join(line for line in new.splitlines(True) if adapter.TAG not in line) == old, 'only tagged lines added: ' + old.strip()[:60])
for token in ('WaitForMainLoadOnWorker()', 'gd.Api.CreateGraphicsPipelines(', 'gd.Api.CreateComputePipelines(',
              'PD.Measure(PD.Phase.GraphicsPipelineBuild)', 'PD.Measure(PD.Phase.ComputePipelineBuild)', 'EnterMainCreation(',
              'NotePipelineBuild(', 'program.AddGraphicsPipeline(', 'program.AddComputePipeline(', 'return Result.PipelineCompileRequired;'):
    check(control.count(token) == candidate.count(token) and control.count(token) > 0, 'unchanged: ' + token)
check(candidate.count('BeginBuildTiming();') == 2 and candidate.count('NoteMainLoadWait(loadWaitStart);') == 2 and
      candidate.count('CompiledMs(buildStart)') == 2, 'both creations (graphics, compute) and both lookups are timed')
lookup = method(candidate, '        private static void NoteMainCacheLookup(bool hit)')
check(lookup.index('_servedByMain = hit;') < lookup.index('if (!hit)'), 'the lookup records its result before the delivered counts')
check(lookup.replace(method(control, '        private static void NoteMainCacheLookup(bool hit)').split('{', 1)[1], '') != lookup and
      method(control, '        private static void NoteMainCacheLookup(bool hit)').split('{', 1)[1] in lookup,
      'the delivered body of NoteMainCacheLookup follows, unchanged')
if FINAL_PREPARATION:
    check(not files_edited_later('adapt_build_journal_load_wait'), 'no later adapter edits PipelineState.cs')
    check(read(FINAL_SOURCE, S) == candidate, 'the final preparation is the control plus the adapter\'s replacements')

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
with tempfile.TemporaryDirectory(prefix='melonx-build-journal-load-wait-') as temporary:
    temporary = Path(temporary).resolve()
    tree = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
    changed = adapter.apply(tree)
    check([p.relative_to(tree).as_posix() for p in changed] == [S], 'the adapter changed PipelineState.cs only')
    check(read(tree, S) == candidate, 'applied tree is the candidate text')
    drift = temporary / 'drift'
    (drift / S).parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / S, drift / S)
    (drift / S).write_bytes((drift / S).read_bytes() + b'\n// unreviewed drift\n')
    try:
        adapter.apply(drift)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'a drifted PipelineState.cs is refused')
    result = subprocess.run([DOTNET, 'build', str(tree / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=tree)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')
    warnings = sorted({line for line in result.stdout.splitlines() if 'warning' in line and 'PipelineState.cs(' in line})
    check(not warnings, 'no compiler warning in PipelineState.cs: ' + '\n'.join(warnings[:5]))

    first = candidate.index('        // RewindBox (adapt_build_journal_load_wait): on the creating thread')
    members = candidate[first:candidate.index('        private static void NoteMainCacheLookup(bool hit)', first)]
    members += method(candidate, '        private static void NoteMainCacheLookup(bool hit)') + '\n'
    work = temporary / 'probe'
    work.mkdir()
    (work / 'Program.cs').write_text((FIXTURE / 'Program.cs').read_text().replace('//__MEMBERS__\n', members))
    (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable><Optimize>true</Optimize>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit><NoWarn>0649;0169;0414;CS0649;CS0169;CS0414</NoWarn>
</PropertyGroup></Project>''')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
    build = subprocess.run([DOTNET, 'build', str(work / 'Probe.csproj'), '-c', 'Release', '-nologo'], cwd=work,
                           capture_output=True, text=True, env=environment, timeout=1200)
    if build.returncode:
        print(build.stdout[-5000:], build.stderr[-2000:], flush=True)
    check(build.returncode == 0, 'probe builds with the production members')
    out = subprocess.run([DOTNET, str(work / 'bin/Release/net10.0/Probe.dll')], capture_output=True, text=True, env=environment, timeout=600)
    check(out.returncode == 0, 'probe runs: ' + out.stderr[-500:])
    report = json.loads(next(line for line in out.stdout.splitlines() if line.startswith('{')))

near = lambda value, expected: abs(value - expected) <= 25
r = report
check(r['servedAfterLoadWait']['candidate'] == 0 and near(r['servedAfterLoadWait']['control'], 1302),
      'IPA 727 case: served after 1 300 ms of load wait: 0 for the journal (the control: 1.3 s, a compilation)')
check(r['servedAfterLoadWait']['control'] >= 50, 'the control journals it as a compilation (50 ms or more)')
check(near(r['compiledAfterLoadWait']['candidate'], 900) and near(r['compiledAfterLoadWait']['control'], 2200),
      'waited 1 300 ms then compiled: about 900 ms (the control: 2.2 s)')
check(near(r['renderThreadCompile']['candidate'], 945) and near(r['renderThreadCompile']['control'], 945),
      'a render-thread compilation keeps its time')
check(r['servedNoWait']['candidate'] == 0 and r['servedNoWait']['control'] < 50, 'served without a wait: not a compilation in either')
check(near(r['compiledNoLookup']['candidate'], 690), 'after a served creation, a creation without a lookup is timed (no stale served)')
check(near(r['compileAfterServed']['candidate'], 945), 'a miss compiles and is timed')
check(r['secondLongWait']['candidate'] == 0, 'a second served creation after a long wait: 0')
expected_record = ('pipelineBuilds mainLoadWait a worker pipeline creation waited 1300 ms for the main cache\'s background load, then '
                   'the main cache served it; the wait is not counted as a compilation (adapt_build_journal_load_wait)')
check(r['recordsAfterFirst'] == [expected_record], 'the first long wait is recorded at once, with the lookup result')
check(r['records'] == [expected_record], 'and only once in the session')

inputs = ['build-utils/melonx/adapt_build_journal_load_wait.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_build_journal_load_wait_test.py', 'test/melonx_build_journal_load_wait/Program.cs', 'test/melonx_adapter_control.py']
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core741Preparation',
               postimages={S: sha(FINAL_SOURCE / S)} if FINAL_PREPARATION else {}, physicalDeviceTested=False,
               productionVulkanAssemblyBuilt=True, sourceBaseline=adapter.BASELINE, report=report,
               deviceEvidence='IPA 727 Hogwarts Legacy (private journals): "compiled again 1" of 1 308, 1 346 and 1 299 ms at the '
                              'launches of pids 54035, 55836 and 56836; main cache background loads of 1 350 and 1 307 ms; first '
                              'worker lookup found in the main cache 20 ms after the load',
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Journal accounting only; the next launches\' "pipelineBuilds" lines are the device check.')
out = ROOT / 'dist/melonx/build-journal-load-wait-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks)))
