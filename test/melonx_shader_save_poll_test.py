#!/usr/bin/env python3
"""The GPU thread's disk-cache save poll without a render-queue drain (adapt_shader_save_poll), before and after.

Usage: melonx_shader_save_poll_test.py <Core 658 prepared MeloNX tree>
       melonx_shader_save_poll_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the Core 658 preparation, candidate adds the adapter. Static checks bind the mechanism in the preparation
(ProcessFrame runs the save poll before DispatchCalls on the GPU thread; the threaded program's link check is an
InvokeCommand that waits for the render thread; the embedded session forces backend threading; Vulkan saves the SPIR-V
packed at enqueue), that each edited file is the preparation once the adapter's replacements are undone (nothing else
changes), that the new poll path never invokes, and that no backend defines its own PeekLinkStatus. The production
Ryujinx.Graphics.Gpu, Ryujinx.Graphics.Vulkan and Ryujinx.Graphics.OpenGL assemblies (with the GAL) are built with the
adapter. Executed: for each variant a fixture runs the production GAL (ThreadedRenderer, ThreadedProgram, ProgramQueue,
ProgramCheckLinkCommand, SetProgramCommand) built from that tree, with a native backend double, and the real
ShaderCache.ProcessShaderCacheQueue and ProgramToSave from that tree (test/melonx_shader_save_poll). The GPU thread polls
once per loop pass while the render thread is blocked 1500 ms in SetProgram's link wait, and while it is busy 1000 ms in
unrelated queued work: the control poll returns only after the render thread is free, the candidate's returns at once on
every pass, with at most one queued check outstanding, and the program is saved once linked. N already-linked programs that the render thread created and bound are all saved in ONE pass with no round trip
(the status is published where the render thread observes it: ProgramQueue.ProcessQueue, WaitForProgram). A never-bound program is
still saved (no lost save), order is kept and a failed program is dropped unsaved in both. No device.
Writes dist/melonx/shader-save-poll-checks.json.
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
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_shader_save_poll', _HOLD)
import adapt_shader_save_poll  # noqa: E402
from adapt_shader_save_poll import apply, BASELINE  # noqa: E402

GAL = 'src/Ryujinx.Graphics.GAL/'
PROGRAM = GAL + 'Multithreading/Resources/ThreadedProgram.cs'
COMMAND = GAL + 'Multithreading/Commands/Program/ProgramCheckLinkCommand.cs'
INTERFACE = GAL + 'IProgram.cs'
QUEUE = GAL + 'Multithreading/Resources/ProgramQueue.cs'
CACHE = 'src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs'
FIXTURE = ROOT / 'test/melonx_shader_save_poll'
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


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def pipeline_double(interface):
    """No-op members for every IPipeline member of the tree; SetProgram records the program."""
    usings = ''.join(line + '\n' for line in interface.splitlines() if line.startswith('using '))
    body = re.sub(r'^\s*///.*$', '', interface[interface.index('public interface IPipeline'):], flags=re.M)
    body = body[body.index('{') + 1:body.rindex('}')]
    members = []
    for returns, name, parameters in re.findall(r'([\w<>\[\]]+)\s+(\w+)\s*\(([^;]*?)\)\s*;', body, flags=re.S):
        parameters = ' '.join(parameters.split())
        if name == 'SetProgram':
            code = 'OnSetProgram(program);'
        elif returns == 'void':
            code = ''
        else:
            code = 'return default;'
        members.append(f'    public {returns} {name}({parameters}) {{ {code} }}\n')
    check(len(members) == body.count(');') and len(members) >= 50 and any(' SetProgram(IProgram program)' in m for m in members), 'IPipeline members generated')
    return usings + 'using Ryujinx.Graphics.GAL;\n\nsealed partial class PipelineDouble\n{\n' + ''.join(members) + '}\n'


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

# The mechanism, in the preparation.
switch = read(SOURCE, 'src/Ryujinx.HLE/Switch.cs')
frame = member(switch, 'public void ProcessFrame()')
check(frame.index('Gpu.ProcessShaderCacheQueue();') < frame.index('Gpu.Renderer.PreFrame();') < frame.index('Gpu.GPFifo.DispatchCalls();'),
      'ProcessFrame: the save poll runs on every GPU loop pass, before dispatch')
check('Device.ProcessFrame();' in read(SOURCE, 'src/Ryujinx.Library/Window/WindowBase.cs'), 'the GPU loop runs ProcessFrame')
check('physicalMemory.ShaderCache.ProcessShaderCacheQueue();' in member(read(SOURCE, 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'),
      'public void ProcessShaderCacheQueue()'), 'GpuContext forwards to every ShaderCache')
control_cache = read(SOURCE, CACHE)
poll = member(control_cache, 'public void ProcessShaderCacheQueue()')
check('programToSave.HostProgram.CheckProgramLink(false);' in poll and 'break;' in poll, 'control: the head is polled with CheckProgramLink(false)')
enqueue = member(control_cache, 'private void EnqueueProgramToSave(')
check('_context.Capabilities.Api == TargetApi.Vulkan ? ShaderBinarySerializer.Pack(sources) : null' in enqueue,
      'Vulkan: the SPIR-V is packed when the program is queued')
check('programToSave.BinaryCode ?? programToSave.HostProgram.GetBinary()' in poll, 'GetBinary only without BinaryCode')
control_program = read(SOURCE, PROGRAM)
link = member(control_program, 'public unsafe ProgramLinkStatus CheckProgramLink(bool blocking)')
check('_renderer.InvokeCommand();' in link and 'ProgramCheckLinkCommand' in link, 'control: the threaded link check is an invoke')
renderer = read(SOURCE, GAL + 'Multithreading/ThreadedRenderer.cs')
invoke = member(renderer, 'internal void InvokeCommand()')
check('_invokePtr = _lastProducedPtr;' in invoke and '_invokeRun.Wait();' in invoke, 'InvokeCommand waits until the render thread ran it')
check(re.search(r'GraphicsBackend = GraphicsBackend\.Vulkan, BackendThreading = BackendThreading\.On,',
                read(SOURCE, 'src/Ryujinx.Library/EmbeddedSession.cs')) is not None, 'the embedded session forces backend threading')
collection = read(SOURCE, 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs')
vulkan_link = member(collection, 'public ProgramLinkStatus CheckProgramLink(bool blocking)')
check('if (!_compileTask.IsCompleted)' in vulkan_link and 'return ProgramLinkStatus.Incomplete;' in vulkan_link,
      'Vulkan: Incomplete until the compile task (warm-up pipeline) is done')
check('threaded.Programs.WaitForProgram(program);' in read(SOURCE, GAL + 'Multithreading/Commands/SetProgramCommand.cs'),
      'SetProgram waits on the render thread for a program that cannot bind incomplete')

replacements = []
original_once = adapt_shader_save_poll.once
reports, built = {}, []
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-shader-save-poll-') as temporary:
    temporary = Path(temporary).resolve()
    for variant in ('control', 'candidate'):
        work = temporary / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            def recording_once(path, old, new):
                replacements.append((path.relative_to(work).as_posix(), old, new))
                original_once(path, old, new)

            adapt_shader_save_poll.once = recording_once
            try:
                changed = apply(work)
            finally:
                adapt_shader_save_poll.once = original_once
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
                check(read(work, name).count('RewindBox (adapt_shader_save_poll)') >= 1, 'commented: ' + name)
            if FINAL_PREPARATION:
                later = files_edited_later('adapt_shader_save_poll')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

            cache = read(work, CACHE)
            new_poll = member(cache, 'public void ProcessShaderCacheQueue()')
            check('programToSave.HostProgram.PeekLinkStatus();' in new_poll and 'CheckProgramLink' not in new_poll,
                  'candidate: the save poll peeks')
            check(new_poll.replace('PeekLinkStatus()', 'CheckProgramLink(false)').replace(
                '                // RewindBox (adapt_shader_save_poll): a status query that never waits for the render thread; a program\n'
                '                // not known to be linked yet stays at the head and is checked again on a later GPU loop pass.\n', '') == poll,
                  'candidate: order, Success-only save and Failure drop unchanged')
            program = read(work, PROGRAM)
            peek = member(program, 'public unsafe ProgramLinkStatus PeekLinkStatus()')
            check('InvokeCommand' not in peek and 'Base' not in peek and 'Wait' not in peek.replace('Volatile', ''),
                  'candidate: the peek neither invokes, waits nor touches the backend program')
            check('Volatile.Read(ref _publishedLinkStatus)' in peek and 'Interlocked.Exchange(ref _linkCheckQueued, 1) == 0' in peek and
                  '_renderer.QueueCommand();' in peek, 'candidate: published status, one queued check at a time')
            check(member(program, 'public unsafe ProgramLinkStatus CheckProgramLink(bool blocking)') == link,
                  'candidate: CheckProgramLink unchanged for its other callers')
            interface = read(work, INTERFACE)
            check('ProgramLinkStatus PeekLinkStatus() => CheckProgramLink(false);' in interface, 'default member: a non-blocking check')
            run = member(read(work, COMMAND), 'public static void Run(')
            check(run.index('threaded.Programs.EnsureProgramCreated(program);') < run.index('program.Base.CheckProgramLink(command._blocking);') <
                  run.index('program.Compiled = true;') < run.index('ResultBox<ProgramLinkStatus> box = command._result.Get(threaded);') <
                  run.index('program.PublishLinkStatus(result, box == null);'), 'Run: create, check, mark, then publish')
            queue_text = read(work, QUEUE)
            process = member(queue_text, 'public void ProcessQueue()')
            check(process.count('PublishLinkStatus(status, false)') == 2 and process.count('Threaded.PublishLinkStatus(status, false)') == 1 and
                  process.index('program.PublishLinkStatus(status, false);') < process.index('program.Compiled = true;') and
                  process.index('Threaded.PublishLinkStatus(status, false)') < process.index('program.Threaded.Compiled = true;'),
                  'ProcessQueue publishes the status in both retire branches')
            waiting = member(queue_text, 'public void WaitForProgram(ThreadedProgram program)')
            check(waiting.index('WaitForLink(program.Base)') < waiting.index('program.PublishLinkStatus(program.Base.CheckProgramLink(false), false);') <
                  waiting.index('program.Compiled = true;'), 'WaitForProgram publishes the status once the link wait returned')
            for backend in ('src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs', 'src/Ryujinx.Graphics.OpenGL/Program.cs'):
                check('PeekLinkStatus' not in read(work, backend), 'backend keeps the default answer: ' + backend)
            texts = {p.relative_to(work).as_posix(): p.read_text(errors='ignore') for p in (work / 'src').rglob('*.cs')}
            callers = sorted(name for name, text in texts.items() if '.PeekLinkStatus(' in text)
            definitions = sorted(name for name, text in texts.items() if 'ProgramLinkStatus PeekLinkStatus()' in text)
            check(callers == [CACHE] and definitions == sorted([INTERFACE, PROGRAM]),
                  'PeekLinkStatus defined by IProgram and ThreadedProgram, called by the save poll only: ' + str((callers, definitions)))

            for project in ('Ryujinx.Graphics.Gpu', 'Ryujinx.Graphics.Vulkan', 'Ryujinx.Graphics.OpenGL'):
                result = subprocess.run([DOTNET, 'build', str(work / 'src' / project / (project + '.csproj')), '-c', 'Release', '-nologo',
                                         '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                                        env=environment, cwd=work)
                if result.returncode:
                    print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
                check(result.returncode == 0, 'production ' + project + ' builds with the adapter')
                built.append(project)

        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        tree_cache = read(work, CACHE)
        save_queue = (FIXTURE / 'SaveQueue.cs').read_text()
        save_queue = save_queue.replace('/* PROGRAM_TO_SAVE */', member(tree_cache, 'private readonly struct ProgramToSave'))
        save_queue = save_queue.replace('/* PROCESS_SHADER_CACHE_QUEUE */', member(tree_cache, 'public void ProcessShaderCacheQueue()'))
        (fixture / 'SaveQueue.cs').write_text(save_queue)
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
cs, ks = c['blockedInSetProgram'], k['blockedInSetProgram']
check(cs['passesReturnedWhileRenderBlocked'] == 0 and cs['firstPollMs'] >= 1000,
      'control: the poll waits until the render thread leaves SetProgram: ' + str(cs))
check(ks['passesReturnedWhileRenderBlocked'] >= 50 and ks['passes'] - ks['passesReturnedWhileRenderBlocked'] <= 3,
      'candidate: every pass but the last few returns while the render thread is still blocked: ' + str(ks))
check(ks['maxPollMs'] < 250, 'candidate: no poll waits for the render thread: ' + str(ks['maxPollMs']))
check(ks['maxPendingCommandsWhileRenderBlocked'] <= 2, 'candidate: SetProgram plus at most one queued check: ' + str(ks))
check(0 <= ks['savedAfterLinkMs'] < 500 and 0 <= cs['savedAfterLinkMs'] < 500, 'saved promptly once linked, both')
co, ko = c['blockedInOtherWork'], k['blockedInOtherWork']
check(co['passesReturnedWhileRenderBlocked'] == 0 and co['firstPollMs'] >= 700, 'control: the poll drains unrelated render work: ' + str(co))
check(ko['passesReturnedWhileRenderBlocked'] >= 50 and ko['maxPollMs'] < 250 and ko['maxPendingCommandsWhileRenderBlocked'] <= 2,
      'candidate: the GPU thread keeps running while the render thread is busy: ' + str(ko))
check(0 <= ko['savedAfterRenderFreeMs'] < 500, 'candidate: saved once the render thread ran the check')
for variant, report in reports.items():
    check(0 <= report['neverBound']['savedAfterLinkMs'] < 500, variant + ': a never-bound program is saved once linked')
    check(report['orderAndFailure']['saved'] == ['p3', 'p4'], variant + ': order kept, failure dropped')
cb, kb = c['linkedBurst'], k['linkedBurst']
check(kb['savedInFirstPass'] == kb['programs'] == 40 and kb['passes'] == 1, 'candidate: N linked programs saved in one pass: ' + str(kb))
check(kb['maxPollMs'] < 250 and kb['pendingDuringFirstPass'] <= 1,
      'candidate: that pass made no render-thread round trip and queued no check: ' + str(kb))
check(cb['firstPollMs'] >= 600, 'control: the same pass waits for the render thread: ' + str(cb))
check(k['defaultMember'] == 'CheckProgramLink(false)' and c['defaultMember'] is None, 'default member answers as CheckProgramLink(false)')

inputs = ['build-utils/melonx/adapt_shader_save_poll.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_shader_save_poll_test.py',
          'test/melonx_adapter_control.py', 'test/melonx_shader_save_poll/Program.cs', 'test/melonx_shader_save_poll/Backend.cs',
          'test/melonx_shader_save_poll/SaveQueue.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionAssembliesBuilt=built,
               productionGalExecuted=True, nativeBackendDouble=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host threads with a native backend double whose compile ends on a timer; the real Vulkan '
                          'ShaderCollection and MoltenVK compiles are not run. Whether the 1 s syncpoint timeouts of a '
                          'Hogwarts compile burst disappear on an iPhone also depends on the queued 3D increments waiting '
                          'for report submission, and is known only from a device run.')
out = ROOT / 'dist/melonx/shader-save-poll-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
