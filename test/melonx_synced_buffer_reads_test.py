#!/usr/bin/env python3
"""Buffer flushes read after their sync without a render-thread round trip (adapt_synced_buffer_reads), before and after.

Usage: melonx_synced_buffer_reads_test.py <Core 699 prepared MeloNX tree>
       melonx_synced_buffer_reads_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the Core 699 preparation, candidate adds the adapter. Static checks bind the mechanism in the preparation:
Buffer.FlushImpl is Buffer.cs's only GetBufferData; Buffer.Flush is only the modified-range list's flush action and
FlushImpl only reached from Flush, the pre-flush and the migration snapshot action; the range list runs its flush action
only from RemoveRangesAndFlush, called after WaitForAndFlushRanges' WaitSync (or for a migration target, from
itself); the pre-flush runs its action only from FlushWithAction (Buffer.Flush); ThreadedRenderer.CreateSync registers
the handle before queueing CreateSyncCommand and WaitSync waits for its availability (the render thread ran it) and
then the backend fence. Candidate: only the adapter's replacements; GetBufferDataAfterSync reads exactly as the
non-GPU-thread branch of GetBufferData; IRenderer's default member forwards to GetBufferData; FlushImpl is the only
caller; no backend defines the member. The production Ryujinx.Graphics.GAL, Ryujinx.Graphics.Gpu and
Ryujinx.Graphics.Vulkan assemblies build with the adapter. Executed: for each variant a fixture runs the production GAL
(ThreadedRenderer, BufferMap, SyncMap, InvokeCommand) with a native backend double that keeps buffer contents
(test/melonx_synced_buffer_reads): GPU-thread reads after a waited sync, with no work queued, behind 300 ms of queued
work, 20 successive reads each behind 20 ms, read after write, a later unsynced write, a buffer still being created
behind 300 ms, and a renderer failure. Control waits for the queued work on every read (round trips on the render
thread); candidate reads at once off the render thread with the synced bytes, still waits for a buffer being created
and fails with the renderer. No device.
Writes dist/melonx/synced-buffer-reads-checks.json.
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
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_synced_buffer_reads', _HOLD)
import adapt_synced_buffer_reads  # noqa: E402
from adapt_synced_buffer_reads import apply, BASELINE, INTERFACE, RENDERER, BUFFER  # noqa: E402

GAL = 'src/Ryujinx.Graphics.GAL/'
RANGES = 'src/Ryujinx.Graphics.Gpu/Memory/BufferModifiedRangeList.cs'
PREFLUSH = 'src/Ryujinx.Graphics.Gpu/Memory/BufferPreFlush.cs'
FIXTURE = ROOT / 'test/melonx_synced_buffer_reads'
DOTNET = os.environ.get('DOTNET', 'dotnet')
TAG = 'RewindBox (adapt_synced_buffer_reads)'
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


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 699 preparation: ' + name)

# The mechanism, in the preparation: every buffer flush read follows the wait for its sync.
buffer = read(SOURCE, BUFFER)
check(buffer.count('GetBufferData(') == 1 and 'GetBufferData(handle, offset, (int)size)' in member(
      buffer, 'private void FlushImpl(BufferHandle handle, ulong address, ulong size)'), 'Buffer.cs: FlushImpl is the only read')
code = re.sub(r'^\s*//.*$', '', buffer, flags=re.M)
check(re.findall(r'\bFlush\b(?!\()', code) == ['Flush'] and 'new BufferModifiedRangeList(_context, this, Flush)' in code,
      'Buffer.Flush is only the range list flush action')
check(sorted(re.findall(r'\bFlushImpl\b\(?', code)) == sorted(['FlushImpl', 'FlushImpl(', 'FlushImpl(', 'FlushImpl(', 'FlushImpl(', 'FlushImpl(']) and
      'new BufferPreFlush(_context, this, FlushImpl)' in buffer and 'FlushImpl(handle, address, size);' in member(buffer, 'public BufferFlushAction GetSnapshotFlushAction()') and
      'FlushImpl(address, size);' in member(buffer, 'public void Flush(ulong address, ulong size, ulong syncNumber)') and
      'FlushImpl(Handle, address, size);' in member(buffer, 'private void FlushImpl(ulong address, ulong size)'),
      'FlushImpl: two definitions, reached from Flush, the pre-flush and the snapshot action only: ' + str(re.findall(r'\bFlushImpl\b\(?', code)))
ranges = read(SOURCE, RANGES)
check(ranges.count('_flushAction') == 4 and 'RangeActionWithMigration(clampAddress, clampEnd - clampAddress, waitSync, _flushAction);' in
      member(ranges, 'private void RemoveRangesAndFlush(') and 'BufferMigrationSpan span = new(ranges._parent, ranges._flushAction, oldMigration);' in ranges,
      'range list: its flush action runs from RemoveRangesAndFlush and its migration spans')
wait = member(ranges, 'public void WaitForAndFlushRanges(ulong address, ulong size)')
check(wait.index('_context.Renderer.WaitSync(currentSync + (ulong)highestDiff);') < wait.index('RemoveRangesAndFlush(') and
      ranges.count('RemoveRangesAndFlush(') == 3, 'RemoveRangesAndFlush runs after WaitSync (or recursively for a migration target)')
preflush = read(SOURCE, PREFLUSH)
check(preflush.count('_flushAction(') == 1 and '_flushAction(handle,' in member(preflush, 'private void FlushPageRange(') and
      'preFlush.FlushWithAction(address, size, syncNumber);' in member(buffer, 'public void Flush(ulong address, ulong size, ulong syncNumber)'),
      'pre-flush: its action runs from FlushWithAction, reached from Buffer.Flush')
renderer_text = read(SOURCE, RENDERER)
sync = member(renderer_text, 'public unsafe void CreateSync(ulong id, bool strict)')
check(sync.index('Sync.CreateSyncHandle(id);') < sync.index('New<CreateSyncCommand>()') < sync.index('QueueCommand();'),
      'CreateSync registers the handle before queueing its command')
waitsync = member(renderer_text, 'public void WaitSync(ulong id)')
check(waitsync.index('Sync.WaitSyncAvailability(id);') < waitsync.index('_baseRenderer.WaitSync(id);'), 'WaitSync: availability, then the fence')
get = member(renderer_text, 'public unsafe PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size)')
check('InvokeCommand();' in get and 'return _baseRenderer.GetBufferData(Buffers.MapBufferBlocking(buffer), offset, size);' in get,
      'GetBufferData: an invoke on the GPU thread, a direct read elsewhere')

replacements = []
original_once = adapt_synced_buffer_reads.once
reports, built = {}, []
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-synced-buffer-reads-') as temporary:
    temporary = Path(temporary).resolve()
    for variant in ('control', 'candidate'):
        work = temporary / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            def recording_once(path, old, new):
                replacements.append((path.relative_to(work).as_posix(), old, new))
                original_once(path, old, new)

            adapt_synced_buffer_reads.once = recording_once
            try:
                changed = apply(work)
            finally:
                adapt_synced_buffer_reads.once = original_once
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
                check(read(work, name).count(TAG) >= 1, 'commented: ' + name)
            if FINAL_PREPARATION:
                later = files_edited_later('adapt_synced_buffer_reads')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

            new_renderer = read(work, RENDERER)
            after = member(new_renderer, 'public PinnedSpan<byte> GetBufferDataAfterSync(BufferHandle buffer, int offset, int size)')
            check('return _baseRenderer.GetBufferData(Buffers.MapBufferBlocking(buffer), offset, size);' in after and
                  'InvokeCommand' not in after and 'New<' not in after, 'candidate: the read of the non-GPU-thread branch, no invoke')
            check(member(new_renderer, 'public unsafe PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size)') == get,
                  'candidate: GetBufferData unchanged for its other callers')
            interface = read(work, INTERFACE)
            check('PinnedSpan<byte> GetBufferDataAfterSync(BufferHandle buffer, int offset, int size) => GetBufferData(buffer, offset, size);' in interface,
                  'default member: GetBufferData')
            new_buffer = read(work, BUFFER)
            check('_context.Renderer.GetBufferDataAfterSync(handle, offset, (int)size)' in member(
                  new_buffer, 'private void FlushImpl(BufferHandle handle, ulong address, ulong size)') and 'GetBufferData(' not in new_buffer,
                  'candidate: FlushImpl reads after sync')
            texts = {p.relative_to(work).as_posix(): p.read_text(errors='ignore') for p in (work / 'src').rglob('*.cs')}
            callers = sorted(name for name, text in texts.items() if '.GetBufferDataAfterSync(' in text)
            definitions = sorted(name for name, text in texts.items() if 'PinnedSpan<byte> GetBufferDataAfterSync(' in text)
            check(callers == [BUFFER] and definitions == sorted([INTERFACE, RENDERER]),
                  'GetBufferDataAfterSync defined by IRenderer and ThreadedRenderer, called by FlushImpl only: ' + str((callers, definitions)))

            for project in ('Ryujinx.Graphics.GAL', 'Ryujinx.Graphics.Gpu', 'Ryujinx.Graphics.Vulkan'):
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
            f'<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
            f'<NoWarn>CS0067;CS0649;CS0414;CS0169</NoWarn>{defines}'
            f'</PropertyGroup><ItemGroup><ProjectReference Include="{work / GAL / "Ryujinx.Graphics.GAL.csproj"}" /></ItemGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            check(result.returncode == 0, variant + ': ' + ' '.join(command[1:3]))
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(variant, json.dumps(reports[variant]), flush=True)

c, k = reports['control']['calls'], reports['candidate']['calls']
for variant, calls in (('control', c), ('candidate', k)):
    check(calls['noWorkValue'] == '1' and calls['behindWorkValue'] == '1' and calls['repeatedValues'] == ['1'] and
          calls['afterWriteValue'] == '2' and calls['afterLaterSyncValue'] == '3', variant + ': every read after a sync returns the synced bytes')
    check(calls['unsyncedLaterValue'] in ('2', '3'), variant + ': a later unsynced write is either not seen or whole, never mixed')
    check(calls['inFlightMs'] >= 270 and calls['inFlightValue'] == '0' and calls['readsOfMissingBuffers'] == 0,
          variant + ': a buffer still being created is waited for, never read missing: ' + str(calls))
    check(calls['noWorkMs'] < 100, variant + ': no work queued, no wait')
    failure = reports[variant]['failure']
    check(failure['readOutcome'] != 'none' and failure['readMs'] < 1000 and failure['scenarioError'] is None and failure['loopError'],
          variant + ': after a renderer failure the read fails at once, it does not block: ' + str(failure))
    check(reports[variant]['loopError'] is None, variant + ': the render loop stops normally at teardown')
check(c['behindWorkMs'] >= 280 and c['repeatedMs'] >= 380 and c['repeatedReads'] == 20 and c['repeatedReadsOffRenderThread'] == 0,
      'control: every read waits for the queued work, read on the render thread: ' + str(c))
check(k['behindWorkMs'] < 50 and k['repeatedMs'] < 100 and k['repeatedLongestMs'] < 20 and k['repeatedReads'] == 20 and
      k['repeatedReadsOffRenderThread'] == 20, 'candidate: reads at once, off the render thread, no round trip: ' + str(k))
for variant, calls in (('control', c), ('candidate', k)):
    check(calls['usableValue'] == '4' and calls['concurrentReads'] == 400 and calls['concurrentBad'] == 0,
          variant + ': the whole path and 400 concurrent reads (guest thread and GPU thread) return the synced bytes')
    check(calls['necessaryWaitMs'] < 100 and calls['toNextSyncMs'] >= 280,
          variant + ': the necessary wait is short here; the next sync still waits for the later work it needs')
check(c['toUsableBytesMs'] >= 280 and k['toUsableBytesMs'] < 50,
      'whole path to usable bytes: control waits for the later work too, candidate only for the necessary sync: ' +
      str((c['toUsableBytesMs'], k['toUsableBytesMs'])))
check(c['unsyncedLaterValue'] == '3' and k['unsyncedLaterValue'] == '2',
      'the only difference: control drains the later write first, candidate reads the synced state')

inputs = ['build-utils/melonx/adapt_synced_buffer_reads.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_synced_buffer_reads_test.py', 'test/melonx_adapter_control.py',
          'test/melonx_synced_buffer_reads/Program.cs', 'test/melonx_synced_buffer_reads/Backend.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core699Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(roundTripsControl=c['repeatedReads'] - c['repeatedReadsOffRenderThread'],
                               roundTripsCandidate=k['repeatedReads'] - k['repeatedReadsOffRenderThread'],
                               behindWorkMs=[c['behindWorkMs'], k['behindWorkMs']], repeatedMs=[c['repeatedMs'], k['repeatedMs']],
                               toUsableBytesMs=[c['toUsableBytesMs'], k['toUsableBytesMs']], toNextSyncMs=[c['toNextSyncMs'], k['toNextSyncMs']]),
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionAssembliesBuilt=built, productionGalExecuted=True,
               nativeBackendDouble=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host threads with a native backend double; the Vulkan BufferHolder read off the render thread is the '
                          'path guest threads already use and is not executed here. The GPU thread time saved in Hogwarts Legacy '
                          'and any frame-time change are known only from a device run.')
out = ROOT / 'dist/melonx/synced-buffer-reads-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
