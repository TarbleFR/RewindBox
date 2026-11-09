#!/usr/bin/env python3
"""adapt_pipeline_variant_replay on the final preparation, against the Core 709 preparation as control.

Usage: melonx_pipeline_variant_replay_test.py <control> --candidate-source <final preparation containing the adapter>

Control: the final preparation with the adapter reversed (melonx_adapter_control), which must be the Core 709 bytes;
forward reproduces the final preparation. Static (both variants): in the control a cached program warms up one graphics
state and a draw in any other state creates it on the render thread with nothing recorded; the candidate records such a
state after the draw obtained it, replays recorded states of cached programs at low priority through the program's
queued-compile table, and a draw joining a queued replay promotes it. Executed: the production Ryujinx.Graphics.Vulkan of
the candidate builds (and Ryujinx.Graphics.Vulkan alone: no warning in the edited files), then (test-only
InternalsVisibleTo) test/melonx_pipeline_variant_replay/Program.cs runs the real PipelineState codec (3 000 random states:
same key, hash, colour slots and tessellation flag read back; malformed variants refused), the real PipelineVariantJournal
(file, torn tail, schema, stale and failed variants, bounds, load off the startup path) and replays on the real
BackgroundCompilationScheduler: relaunch ranking and the two-in-flight bound, a demanded state behind 20 queued warm-ups
with 8 simultaneous waiters, close during compilation, a failed state, device memory admission, costly replays, the
per-session cap. Writes dist/melonx/pipeline-variant-replay-checks.json. No device: host times, no Vulkan creation.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
import adapt_pipeline_variant_replay as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
HARNESS = ROOT / 'test/melonx_pipeline_variant_replay'
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


environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')


def dotnet(*arguments, cwd, timeout=2400):
    result = subprocess.run([DOTNET, *arguments], capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
    if result.returncode:
        errors = [line for line in result.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), result.stdout[-3000:], result.stderr[-2000:], sep='\n', flush=True)
    return result


temporary = tempfile.TemporaryDirectory(prefix='melonx-pipeline-variant-replay-')
WORK = Path(temporary.name).resolve()
# The adapter's postimage (later adapters sharing its files reversed first); the receipt binds the final preparation.
PREPARED = FINAL_SOURCE
POST = WORK / 'post'
LATER = control_tools.postimage('adapt_pipeline_variant_replay', FINAL_SOURCE, POST)
replay = WORK / 'replay'
shutil.copytree(POST, replay)
for later in LATER:
    __import__(later).apply(replay)
for name in adapter.BASELINE:
    check((replay / name).read_bytes() == (PREPARED / name).read_bytes(), 'the later adapters reproduce the final preparation: ' + name)
CONTROL = WORK / 'control'
for name in adapter.BASELINE:
    (CONTROL / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(POST / name, CONTROL / name)

# --- Control: the adapter reversed must be the Core 709 bytes; forward reproduces the postimage ---
control_tools._reverse('adapt_pipeline_variant_replay', CONTROL)
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 709 postimage: ' + name)
forward = WORK / 'forward'
for name in adapter.BASELINE:
    (forward / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL / name, forward / name)
changed = sorted(str(p.relative_to(forward)) for p in adapter.apply(forward))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only its files')
for name in adapter.BASELINE:
    check((forward / name).read_bytes() == (POST / name).read_bytes(), 'final preparation is the adapter: ' + name)
try:
    adapter.apply(forward)
    refused = False
except AssertionError:
    refused = True
check(refused, 'fail closed: an adapted tree is refused')

# --- Static: the exact scope, both variants ---
pairs = {
    adapter.STATE: [(adapter.STATE_ANCHOR, adapter.STATE_NEW)],
    adapter.PROGRAM: [(adapter.PROGRAM_CLASS_OLD, adapter.PROGRAM_CLASS_NEW), (adapter.PROGRAM_FIELDS_OLD, adapter.PROGRAM_FIELDS_NEW),
                      (adapter.PROGRAM_CTOR_OLD, adapter.PROGRAM_CTOR_NEW), (adapter.PROGRAM_JOIN_OLD, adapter.PROGRAM_JOIN_NEW),
                      (adapter.PROGRAM_QUEUED_OLD, adapter.PROGRAM_QUEUED_NEW), (adapter.PROGRAM_METHODS_OLD, adapter.PROGRAM_METHODS_NEW)],
    adapter.DRAWS: [(adapter.DRAW_START_OLD, adapter.DRAW_START_NEW), (adapter.DRAW_JOIN_OLD, adapter.DRAW_JOIN_NEW),
                    (adapter.DRAW_END_OLD, adapter.DRAW_END_NEW)],
    adapter.MANAGER: [(adapter.MANAGER_USINGS_OLD, adapter.MANAGER_USINGS_NEW), (adapter.MANAGER_PROPERTY_OLD, adapter.MANAGER_PROPERTY_NEW),
                      (adapter.MANAGER_CTOR_OLD, adapter.MANAGER_CTOR_NEW), (adapter.MANAGER_SUMMARY_OLD, adapter.MANAGER_SUMMARY_NEW),
                      (adapter.MANAGER_PAUSE_OLD, adapter.MANAGER_PAUSE_NEW), (adapter.MANAGER_CLOSE_OLD, adapter.MANAGER_CLOSE_NEW),
                      (adapter.MANAGER_CLASS_OLD, adapter.MANAGER_CLASS_NEW)],
}
for name, replacements in pairs.items():
    text = read(POST, name)
    for old, new in reversed(replacements):
        check(text.count(new) == 1, 'replacement present once: ' + new.strip()[:60])
        text = text.replace(new, old)
    check(text == read(CONTROL, name), name + ' differs from Core 709 only by the adapter\'s replacements')

control_draws, draws = read(CONTROL, adapter.DRAWS), read(POST, adapter.DRAWS)
control_program, program = read(CONTROL, adapter.PROGRAM), read(POST, adapter.PROGRAM)
state, manager = read(POST, adapter.STATE), read(POST, adapter.MANAGER)
# Control: one warm-up state per cached program; any other state is created by the draw, and nothing records it.
check('CreateBackgroundGraphicsPipeline' in control_program and '_state.ToVulkanPipelineState(_gd)' in control_program,
      'control: the warm-up is the translation state (ProgramPipelineState)')
check('NoteLate' not in control_draws and 'Variants' not in read(CONTROL, adapter.MANAGER), 'control records no late state')
create = member(control_draws, 'private bool CreatePipeline(')
check('pipeline = _newState.CreateGraphicsPipeline(Gd, Device, _program, PipelineCache, renderPass.Get(Cbs).Value);' in create,
      'control: the draw creates a missing state synchronously on the render thread')
check(program.count('PromotePipelineCompile(task)') == 1 and program.count('PromotePipelineCompile(queued)') == 1,
      'a draw joining a queued compile promotes that compile itself (synchronous and async paths)')
schedule = member(program, 'Task<long> PipelineVariantJournal.ITarget.Schedule(PipelineVariantJournal.Record record)')
check(schedule.index('lock (_pipelineCacheLock)') < schedule.index('RunBackgroundPipelineCompile(') <
      schedule.index('_graphicsPipelineBackgroundQueue ??= new()).Add(ref key, compile)'), 'registered under the lock as it is scheduled')
check('highPriority: false' in schedule and 'demanded:' not in schedule, 'replays are scheduled at low priority, undemanded')
check('throwOnError: false' in schedule and 'cachePipelineFailure: false' in schedule and 'AddBackgroundGraphicsPipelineFailure(ref key)' in schedule,
      'a failed replay is noted as a failure of that state, not cached as the draw\'s result')
for guard in ('_graphicsPipelineCache.TryGetValue(ref key, out _)', '_graphicsPipelineBackgroundQueue.TryGetValue(ref key, out _)',
              '_graphicsPipelineBackgroundFailures.TryGetValue(ref key, out _)', 'state.StagesCount != (uint)_shaders.Length',
              'state.HasTessellationControlShader != HasTessellationControlShader'):
    check(guard in schedule, 'a replay is not scheduled when: ' + guard)
check('state.CreateVariantRenderPass(_gd, _device, colorSlots)' in schedule and 'state.PipelineLayout = PipelineLayout;' in schedule and
      'stages[i] = _shaders[i].GetInfo();' in schedule, 'session objects rebuilt: layout, stages and render pass')
ctor = program[program.index(adapter.PROGRAM_CTOR_NEW):][:len(adapter.PROGRAM_CTOR_NEW)]
check('if (fromCache && !IsCompute && compileInBackground)' in ctor, 'only cached graphics programs replay')
offer = member(program, 'private async Task OfferRecordedVariants()')
check('await Task.WhenAll(_shaderCompileTasks);' in offer and '.Wait(' not in offer, 'offered after the modules, never awaited by the game')
note = member(program, 'internal void NoteLateVariant(')
check('GetInitialGraphicsPipelineKey()' in note and 'return;' in note, 'the warm-up\'s own state is not recorded')
cancel = member(program, 'public void CancelPendingWarmUp()')
check(cancel.index('CancelVariantReplays();') < cancel.index('if (!_detachedWarmUp'), 'disposal and close cancel undemanded replays first')
end = draws[draws.index(adapter.DRAW_END_NEW):][:len(adapter.DRAW_END_NEW)]
check('if (pipeline != null)' in end and 'NoteLateVariant' in end, 'only a state the draw obtained is recorded')
check(draws.count('_renderPassHadSkippedDraw = true;') == control_draws.count('_renderPassHadSkippedDraw = true;') and
      draws.count('return false;') == control_draws.count('return false;'), 'no draw skip and no early return added')
journal = manager[manager.index('sealed class PipelineVariantJournal'):]
for bound in ('MaxRecords = 2048', 'MaxFileBytes = 2L * 1024 * 1024', 'RecentSessions = 8', 'MaxReplaysPerSession = 512',
              'ReplayWorkBudgetMs = 120_000', 'MaxInFlight = 2', 'CostlyReplayMs = 300', 'LowDevicePercent = 8'):
    check(bound in journal, 'bound: ' + bound)
check('File.Move(temporary, _path, overwrite: true)' in journal and 'Checksum(body) != checksum' in journal, 'atomic compaction, checked lines')
check('ThreadPool.UnsafeQueueUserWorkItem(_ => Load(), null)' in journal and
      'ThreadPool.UnsafeQueueUserWorkItem(_ => Append(copy, KindVariant), null)' in journal, 'file work off the startup and render threads')
added = ''.join(new for replacements in pairs.values() for _, new in replacements)
check(re.search(r'\b(IntPtr|nint|Handle)\b', state[state.index('internal readonly byte[] WriteVariant('):state.index('internal bool TryReadVariant(')]) is None,
      'the variant writes no handle or pointer')
check('MemoryMarshal' not in added and 'Unsafe.As' not in added, 'no raw structure written')
fields = adapter.STATE_NEW[adapter.STATE_NEW.index('internal readonly byte[] WriteVariant('):adapter.STATE_NEW.index('internal bool TryReadVariant(')]
schema = re.search(r'internal const string StateFields =\s*"([^"]+);"', manager).group(1).split(',')
written = re.findall(r'Put\(buffer, ref offset, (?:BitConverter\.SingleToUInt32Bits\((\w+)\)|\((\w+) \? 1u : 0u\)|\(uint\)(\w+)|(\w+))\);', fields)
written = [next(x for x in w if x) for w in written][:len(schema)]
check(written == schema, 'WriteVariant writes the key fields in the schema\'s order')

# --- Executed: the production Vulkan assembly of the candidate, then the probe on it ---
work = WORK / 'tree'
shutil.copytree(FINAL_SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
build = dotnet('build', str(work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false', cwd=work)
check(build.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds')
warnings = sorted({line for line in build.stdout.splitlines() if 'warning' in line and
                   any(f in line for f in ('PipelineCacheManager.cs', 'ShaderCollection.cs', 'PipelineBase.cs', 'PipelineState.cs'))
                   and 'RewindBox' not in line})
project = work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')
project.write_text(project.read_text(encoding='utf-8-sig').replace(
    '</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXVariantProbe" /></ItemGroup>\n</Project>'))
probe = WORK / 'probe'
probe.mkdir()
shutil.copyfile(HARNESS / 'Program.cs', probe / 'Program.cs')
(probe / 'MeloNXVariantProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn><NuGetAudit>false</NuGetAudit>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{work}/src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj" />
  </ItemGroup>
</Project>
''')
for extra in ('global.json', 'nuget.config'):
    if (work / extra).exists():
        shutil.copyfile(work / extra, probe / extra)
build = dotnet('build', str(probe / 'MeloNXVariantProbe.csproj'), '-c', 'Release', '-nologo', '-m:1', cwd=probe)
check(build.returncode == 0, 'probe builds against the production Vulkan assembly')
run = subprocess.run([DOTNET, str(probe / 'bin/Release/net10.0/MeloNXVariantProbe.dll')], capture_output=True, text=True,
                     timeout=1200, env=environment, cwd=probe)
if run.returncode or run.stderr.strip():
    print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
check(run.returncode == 0, 'probe runs')
r = json.loads(next(line for line in reversed(run.stdout.splitlines()) if line.startswith('{')))
print(json.dumps(r, indent=1)[:6000], flush=True)
check(r['requireFailures'] == 0, 'probe requirements')

c = r['codec']
check(r['codecFields'] == r['stateProperties'] == 49, 'the schema names the 49 key properties')
check(c['readBack'] == c['sameKey'] == c['sameHash'] == c['sameSlots'] == c['sameTessellation'] == c['deterministic'] == c['states'] == 3000,
      'every random state reads back with the same key, hash, slots and tessellation flag: %s' % c)
check(c['maxBytes'] <= 2048, 'a variant fits its bound: %s' % c['maxBytes'])
check(all(r['codecRejects'].values()), 'malformed variants refused: %s' % r['codecRejects'])

f = r['file']
check(f['session1New'] == 18 and f['session2Loaded'] == 18 and f['session2Session'] == 2, 'first encounter recorded once per session, read back: %s' % f)
check(f['loadedLine'] and '18 variants of 6 programs planned for session 2' in f['loadedLine'], 'loaded line: %s' % f['loadedLine'])
check(r['otherSchemaLoaded'] == 0, 'a journal of another schema is not read')
s = r['stale']
check(s['session'] == 10 and s['loaded'] == 9 and s['dropped'] >= 1, 'a variant older than 8 sessions is dropped, one met again kept: %s' % s)
b = r['bounds']
check(b['reloaded'] == 2048 and b['fileBytes'] <= 2 * 1024 * 1024, 'at most 2048 variants and 2 MiB: %s' % b)
check(b['backgroundConstructorMs'] <= 50 and b['loadMs'] <= 2000, 'the load is off the startup path and short: %s' % b)

rl = r['relaunch']
check(rl['planned'] == 9 and rl['replayed'] == 9 and rl['executedOnce'], 'relaunch: every recorded state replayed once: %s' % rl)
check(rl['firstThreeAreTwoSessionStates'], 'states met in more sessions replay first')
check(1 <= rl['maxInFlight'] <= 2 and rl['offerMs'] <= 50, 'two in flight at most, the offer never waits: %s' % rl)
check(r['afterReplayLate']['builtButMissed'] == 1 and r['afterReplayLate']['new'] == 0, 'a late state already built is counted apart')
p = r['priority']
check(p['compilesOfIt'] == 1 and p['waiters'] == 8, 'eight simultaneous waits share one compile: %s' % p)
check(p['warmUpsBeforeIt'] <= 3 and p['waitedMs'] < 600, 'a demanded state is created before the queued warm-ups (20 x 60 ms): %s' % p)
cl = r['close']
check(cl['executed'] < cl['planned'] and cl['executedAfterClose'] == 0 and cl['failedMarked'] == 0 and not cl['fileGrew'],
      'close during compilation: running ones finish, queued ones cancelled, nothing marked failed: %s' % cl)
fa = r['failure']
check(fa['session2Replayed'] == 1 and fa['session2Failed'] == 1 and fa['lateAfterFailed'] == 1, 'a failed state is marked: %s' % fa)
check(fa['session3Planned'] == 1, 'a failed state is not replayed at the next launch')
check(fa['deviceShortExecuted'] == 0 and fa['deviceBackReplayed'] == 1, 'no replay while device memory is short: %s' % fa)
co = r['costly']
check(co['replayed'] == 5 and co['maxInFlightOnceCostly'] == 1, 'one in flight once replays are costly: %s' % co)
check(co['joined'] == 1 and co['joinedMs'] == 12 and co['new'] == 1, 'joined draws and new late states counted apart: %s' % co)
check(r['cap']['replayed'] == 512 and r['cap']['executed'] == 512, 'at most 512 replays per session: %s' % r['cap'])

inputs = ['build-utils/melonx/adapt_pipeline_variant_replay.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_pipeline_variant_replay_test.py', 'test/melonx_pipeline_variant_replay/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               productionVulkanAssemblyBuilt=True, editedFileWarnings=warnings,
               postimages={n: sha(PREPARED / n) for n in adapter.BASELINE}, testedPostimages={n: sha(POST / n) for n in adapter.BASELINE},
               report=r, sdk=sdk, host=platform.system(), physicalDeviceTested=False, gameTested=False,
               inputs={n: sha(ROOT / n) for n in inputs},
               limitation='Host run of the production codec, journal and scheduler; no Vulkan device, so a replay creates nothing '
                          'and its cost is simulated. Whether replayed states are the ones a later draw asks for (built but missed '
                          'stays 0), the late creations saved, and launch time and memory on an iPhone are shown only by a device run.')
out = ROOT / 'dist/melonx/pipeline-variant-replay-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
