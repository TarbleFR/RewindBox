#!/usr/bin/env python3
"""The GPU thread's synchronous waits attributed per invoked command (adapt_sync_wait_attribution), before and after.

Usage: melonx_sync_wait_attribution_test.py <Core 697 prepared MeloNX tree>
       melonx_sync_wait_attribution_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the Core 697 preparation, candidate adds the adapter. Static checks bind the mechanism in the preparation
(every synchronous GAL call is a New<T> followed by InvokeCommand, eight command types; the invoked command's type is the
last byte of its queue slot, the byte the render thread dispatches on; LogRenderWork prints one line per 5 s of render
work), that ThreadedRenderer.cs is the preparation once the adapter's replacements are undone (nothing else changes,
no log call added) and the order of the new steps (type and start noted before queueing, the tally after the
wake-up and the failure check; the own time written before the waiter is woken; the totals appended to the existing
line before its print). The production Ryujinx.Graphics.GAL assembly is built with the adapter. Executed: for each
variant a fixture runs the production GAL (ThreadedRenderer, its queue, dispatch, InvokeCommand, LogRenderWork) built
from that tree with a native backend double (test/melonx_sync_wait_attribution): on the GPU thread, a 200 ms read-back
queued behind 300 ms of render work, an empty action behind 250 ms, an action of 150 ms, then a 50 ms read-back in a
second window. The candidate's line names each call's type, its wait and its own time (the read-back 500 ms of which
200 ms its own; the actions 400 ms of which 150 ms), counts each window apart, and prints no other line; the GPU
thread's own timing of each call is the same in both variants. No device.
Writes dist/melonx/sync-wait-attribution-checks.json.
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
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_sync_wait_attribution', _HOLD)
import adapt_sync_wait_attribution  # noqa: E402
from adapt_sync_wait_attribution import apply, BASELINE, RENDERER  # noqa: E402

GAL = 'src/Ryujinx.Graphics.GAL/'
FIXTURE = ROOT / 'test/melonx_sync_wait_attribution'
DOTNET = os.environ.get('DOTNET', 'dotnet')
TAG = 'RewindBox (adapt_sync_wait_attribution)'
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


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def in_order(text, *parts):
    positions = [text.find(part) for part in parts]
    return all(p >= 0 for p in positions) and positions == sorted(positions) and all(text.count(p) == 1 for p in parts)


def pipeline_double(interface):
    """No-op members for every IPipeline member of the tree."""
    usings = ''.join(line + '\n' for line in interface.splitlines() if line.startswith('using '))
    body = re.sub(r'^\s*///.*$', '', interface[interface.index('public interface IPipeline'):], flags=re.M)
    body = body[body.index('{') + 1:body.rindex('}')]
    members = []
    for returns, name, parameters in re.findall(r'([\w<>\[\]]+)\s+(\w+)\s*\(([^;]*?)\)\s*;', body, flags=re.S):
        parameters = ' '.join(parameters.split())
        code = 'OnSetProgram(program);' if name == 'SetProgram' else '' if returns == 'void' else 'return default;'
        members.append(f'    public {returns} {name}({parameters}) {{ {code} }}\n')
    check(len(members) == body.count(');') and len(members) >= 50, 'IPipeline members generated')
    return usings + 'using Ryujinx.Graphics.GAL;\n\nsealed partial class PipelineDouble\n{\n' + ''.join(members) + '}\n'


LINE = re.compile(r' GPU thread sync waits (\d+) calls ([\d.]+) ms \(invoked commands themselves ([\d.]+) ms, the rest queued ahead\); '
                  r'top \(calls, ms, own ms\):((?: \w+ \d+ [\d.]+ [\d.]+;)*)$')


def attribution(line):
    found = LINE.search(line)
    check(found is not None, 'candidate line carries the sync waits: ' + line[-300:])
    entries = {name: (int(calls), float(ms), float(own))
               for name, calls, ms, own in re.findall(r' (\w+) (\d+) ([\d.]+) ([\d.]+);', found.group(4))}
    return dict(calls=int(found.group(1)), ms=float(found.group(2)), own=float(found.group(3)), entries=entries)


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 697 preparation: ' + name)

# The mechanism, in the preparation.
control_renderer = read(SOURCE, RENDERER)
invoke = member(control_renderer, 'internal void InvokeCommand()')
check('_invokePtr = _lastProducedPtr;' in invoke and '_invokeRun.Wait();' in invoke, 'InvokeCommand waits until the render thread ran it')
new = member(control_renderer, 'internal unsafe T* New<T>()')
check('_lastProducedPtr = taken;' in new and 'memory[^1] = (byte)(result)->CommandType;' in new and
      'Span<byte> memory = new(_commandQueue, taken * _elementSize, _elementSize);' in new,
      'New<T>: the command type is the last byte of the slot it takes, recorded as the last produced')
loop = member(control_renderer, 'public void RenderLoop()')
check(in_order(loop, 'byte commandType = command[^1];', 'long commandStart = Stopwatch.GetTimestamp();',
               'CommandHelper.RunCommand(command, this, _baseRenderer);', 'NoteRenderCommand(commandType, commandStart);',
               'Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr', '_invokeRun.Set();'),
      'RenderLoop: dispatch on the slot type, then wake the waiter of that slot')
log = member(control_renderer, 'private void LogRenderWork(long end)')
check(log.count('Logger.Warning?.Print(') == 1 and control_renderer.count('LogRenderWork(end);') == 1 and
      'Stopwatch.Frequency * 5' in member(control_renderer, 'private void NoteRenderCommand(byte type, long start)'),
      'one line per 5 s of render work')
invokers = {}
for path in sorted((SOURCE / GAL / 'Multithreading').rglob('*.cs')):
    text = path.read_text(encoding='utf-8-sig')
    for found in re.finditer(r'InvokeCommand\(\);', text):
        before = text[:found.start()]
        if before.rstrip().endswith('internal void'):
            continue
        method = before[before.rfind('\n        public'):] if '\n        public' in before else before
        types = re.findall(r'New<(\w+)>\(\)', method)
        check(len(types) >= 1, 'a synchronous call queues its command first: ' + path.name)
        invokers.setdefault(types[-1], []).append(path.relative_to(SOURCE).as_posix())
check(sorted(invokers) == sorted(['ActionCommand', 'BufferGetDataCommand', 'GetCapabilitiesCommand', 'TryHostConditionalRenderingCommand',
                                  'ProgramGetBinaryCommand', 'ProgramCheckLinkCommand', 'TextureGetDataCommand',
                                  'TextureGetDataSliceCommand']), 'the eight synchronous commands: ' + str(sorted(invokers)))

replacements = []
original_once = adapt_sync_wait_attribution.once
reports, built = {}, []
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-sync-wait-attribution-') as temporary:
    temporary = Path(temporary).resolve()
    for variant in ('control', 'candidate'):
        work = temporary / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            def recording_once(path, old, new):
                replacements.append((path.relative_to(work).as_posix(), old, new))
                original_once(path, old, new)

            adapt_sync_wait_attribution.once = recording_once
            try:
                changed = apply(work)
            finally:
                adapt_sync_wait_attribution.once = original_once
            check(sorted(p.relative_to(work).as_posix() for p in changed) == sorted(BASELINE), 'adapter changed other files')
            duplicate = temporary / 'duplicate'
            for name in BASELINE:
                (duplicate / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work / name, duplicate / name)
            try:
                apply(duplicate)
                refused = False
            except AssertionError:
                refused = True
            check(refused, 'fail closed: an adapted tree is refused')
            for name in BASELINE:
                undone = read(work, name)
                for path, old, new in reversed(replacements):
                    if path == name:
                        check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
                        undone = undone.replace(new, old)
                check(undone == read(SOURCE, name), name + ' is the preparation but the adapter\'s replacements')
                check(read(work, name).count(TAG) >= 4, 'commented: ' + name)
            if FINAL_PREPARATION:
                later = files_edited_later('adapt_sync_wait_attribution')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

            renderer = read(work, RENDERER)
            check(renderer.count('Logger.') == control_renderer.count('Logger.') and
                  renderer.count('Print(') == control_renderer.count('Print('), 'candidate: no log call added')
            new_invoke = member(renderer, 'internal void InvokeCommand()')
            check(in_order(new_invoke, '_invokePtr = _lastProducedPtr;',
                           'byte invokedType = _commandQueue[_lastProducedPtr * _elementSize + _elementSize - 1];',
                           'Volatile.Write(ref _invokedOwnTicks, 0);', 'long waitStart = Stopwatch.GetTimestamp();',
                           'QueueCommand();', '_invokeRun.Wait();', 'NoteSyncWait(invokedType, waitStart);') and
                  new_invoke.rstrip().endswith('ThrowIfFailed();\n            NoteSyncWait(invokedType, waitStart);\n        }'),
                  'candidate: type and start noted before queueing, the tally once woken and past the failure check')
            new_loop = member(renderer, 'public void RenderLoop()')
            check(in_order(new_loop, 'Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr',
                           'Volatile.Write(ref _invokedOwnTicks, Stopwatch.GetTimestamp() - commandStart);', '_invokeRun.Set();'),
                  'candidate: the own time is written before the waiter is woken, for the invoked slot only')
            new_log = member(renderer, 'private void LogRenderWork(long end)')
            check(in_order(new_log, 'AppendSyncWaits(text);', 'Array.Clear(_renderWorkTicks);', 'Logger.Warning?.Print('),
                  'candidate: the totals join the existing line before its print')
            note = member(renderer, 'private void NoteSyncWait(byte type, long waitStart)')
            check(note.count('Interlocked.') == 3 and 'Math.Max(0, Math.Min(Volatile.Read(ref _invokedOwnTicks), waited))' in note and 'Clamp' not in note and
                  'new ' not in note and 'Logger' not in note, 'candidate: three atomic adds per synchronous call, no allocation')
            append = member(renderer, 'private void AppendSyncWaits(System.Text.StringBuilder text)')
            check(append.count('Interlocked.Exchange(') == 3 and 'rank < 6' in append, 'candidate: read and cleared once per window, six types')
            check(renderer.count('NoteSyncWait(') == 2 and renderer.count('AppendSyncWaits(') == 2,
                  'candidate: one tally site (InvokeCommand) and one print site (LogRenderWork)')

            project = 'Ryujinx.Graphics.GAL'
            result = subprocess.run([DOTNET, 'build', str(work / 'src' / project / (project + '.csproj')), '-c', 'Release', '-nologo',
                                     '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                                    env=environment, cwd=work)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
            check(result.returncode == 0, 'production ' + project + ' builds with the adapter')
            built.append(project)

        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        (fixture / 'Pipeline.g.cs').write_text(pipeline_double(read(work, GAL + 'IPipeline.cs')))
        for name in ('Program.cs', 'Backend.cs'):
            shutil.copyfile(FIXTURE / name, fixture / name)
        defines = '<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if variant == 'candidate' else ''
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            f'<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0067;CS0649;CS0414;CS0169</NoWarn>{defines}'
            f'</PropertyGroup><ItemGroup><ProjectReference Include="{work / GAL / "Ryujinx.Graphics.GAL.csproj"}" /></ItemGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            check(result.returncode == 0, variant + ': ' + ' '.join(command[1:3]))
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(variant, json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
for variant, report in reports.items():
    check(len(report['lines']) == 2 and all('Render thread commands over' in line for line in report['lines']),
          variant + ': two render work lines, one per window')
    check(report['readBacks'] == 2 and report['readBacksOffRenderThread'] == 0, variant + ': both read-backs ran on the render thread')
    calls = report['calls']
    check(calls['readBackBehindWorkMs'] >= 470 and calls['emptyActionBehindWorkMs'] >= 230 and calls['busyActionMs'] >= 140 and
          calls['readBackAloneMs'] >= 45, variant + ': each synchronous call waited for the work ahead and its own: ' + str(calls))
check(not any('sync waits' in line for line in c['lines']), 'control: the line has no sync waits')
check(c['loggerEvents'] == k['loggerEvents'], 'candidate: no log line added: ' + str((c['loggerEvents'], k['loggerEvents'])))
for key in ('readBackBehindWorkMs', 'emptyActionBehindWorkMs', 'busyActionMs', 'readBackAloneMs'):
    check(abs(c['calls'][key] - k['calls'][key]) < 150, 'the GPU thread waits as long in both variants: ' + key)
for control_line, candidate_line in zip(c['lines'], k['lines']):
    check(candidate_line[:candidate_line.index(' over ')] == control_line[:control_line.index(' over ')] and ' GPU thread sync waits ' in candidate_line and
          candidate_line.index('top (calls, ms):') < candidate_line.index(' GPU thread sync waits '),
          'candidate: the same line, the sync waits appended')
first, second = attribution(k['lines'][0]), attribution(k['lines'][1])
kc = k['calls']
read_back = first['entries'].get('BufferGetData')
check(read_back is not None and read_back[0] == 1 and 470 <= read_back[1] <= kc['readBackBehindWorkMs'] + 50 and
      190 <= read_back[2] <= 400 and read_back[1] - read_back[2] >= 270,
      'read-back behind work: one call, 500 ms of which 200 ms its own: ' + str(read_back))
actions = first['entries'].get('Action')
check(actions is not None and actions[0] == 2 and 370 <= actions[1] <= kc['emptyActionBehindWorkMs'] + kc['busyActionMs'] + 50 and
      140 <= actions[2] <= 300 and actions[1] - actions[2] >= 220,
      'actions: two calls, 400 ms of which 150 ms their own (the empty one waited only for the work ahead): ' + str(actions))
check(first['entries'].get('GetCapabilities', (0,))[0] == 1 and first['calls'] == 4,
      'first window: the warm-up call too, four in all: ' + str(first))
check(abs(first['ms'] - sum(v[1] for v in first['entries'].values())) <= 1 and
      abs(first['own'] - sum(v[2] for v in first['entries'].values())) <= 1, 'totals are the sum of the types listed')
alone = second['entries'].get('BufferGetData')
check(alone is not None and alone[0] == 1 and alone[2] >= 45 and alone[1] >= alone[2] and 'Action' not in second['entries'] and
      second['calls'] == 2 and second['entries'].get('GetCapabilities', (0,))[0] == 1,
      'second window: counted apart (the read-back alone and the first window\'s closing call): ' + str(second))

inputs = ['build-utils/melonx/adapt_sync_wait_attribution.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_sync_wait_attribution_test.py', 'test/melonx_adapter_control.py',
          'test/melonx_sync_wait_attribution/Program.cs', 'test/melonx_sync_wait_attribution/Backend.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core697Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               attribution=dict(first=first, second=second), reports=reports, sdk=sdk, physicalDeviceTested=False,
               productionAssembliesBuilt=built, productionGalExecuted=True, nativeBackendDouble=True, sourceBaseline=BASELINE,
               synchronousCommands={name: sorted(set(paths)) for name, paths in sorted(invokers.items())},
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host threads with a native backend double whose work and read-backs are timed spins; the real '
                          'Vulkan backend and MoltenVK are not run. Which commands Hogwarts Legacy waits for, and how long, '
                          'is known only from a device run.')
out = ROOT / 'dist/melonx/sync-wait-attribution-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
