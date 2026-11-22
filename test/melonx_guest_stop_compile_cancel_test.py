#!/usr/bin/env python3
"""Cancel the queued compiles when the guest stops (adapt_guest_stop_compile_cancel), before and after, real engine code.

Usage: melonx_guest_stop_compile_cancel_test.py <final preparation containing the adapter>
       melonx_guest_stop_compile_cancel_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control), candidate is the adapter applied to it,
which must be the final preparation byte for byte. For each, the production Vulkan assembly is built, and the real
BackgroundCompilationScheduler, the real ShaderCollection warm-up methods, the real wait of ShaderCollection.Dispose
(from CancelPendingWarmUp to the first module release), the real VulkanRenderer.BeginTeardown and, in the candidate,
the real VulkanRenderer.CancelCompilesAtGuestStop run with doubles (test/melonx_guest_stop_compile_cancel).

The case is a close of IPA 816-820: every pipeline thread is inside a compile, 150 programs compiled during play have
their warm-up pipeline queued (20 ms each), 50 programs of the disk cache still wait for their shader module (10 ms
each) and 20 programs have a play-time pipeline queued. The guest stops, then the render loop's drain disposes the 220
programs. The control compiles the queue during the drain; the candidate cancels it when the guest stops, without
waiting for the running compiles, compiles nothing during the drain, logs no failure, still joins the threads at the
GPU release before the cache is saved, and refuses work scheduled afterwards. Static checks bind where the call sits
and that the cancellation neither joins nor touches the render thread's program set. The candidate's Ryujinx.Library
is built too. No device: the close time on an iPhone is known only from the "teardown" lines of a device run.
Writes dist/melonx/guest-stop-compile-cancel-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_guest_stop_compile_cancel', _HOLD)
from adapt_guest_stop_compile_cancel import apply, BASELINE  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
SCHEDULER = VULKAN + 'BackgroundCompilationScheduler.cs'
RENDERER = VULKAN + 'VulkanRenderer.cs'
WINDOW = 'src/Ryujinx.Library/Window/WindowBase.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_guest_stop_compile_cancel'
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
with tempfile.TemporaryDirectory(prefix='melonx-guest-stop-compile-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            later = files_edited_later('adapt_guest_stop_compile_cancel')
            for name in BASELINE:
                if name not in later:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        project = 'src/Ryujinx.Library/Ryujinx.Library.csproj' if variant == 'candidate' else VULKAN + 'Ryujinx.Graphics.Vulkan.csproj'
        result = subprocess.run([DOTNET, 'build', str(work / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                                capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production assembly builds: ' + project)

        collection = (work / (VULKAN + 'ShaderCollection.cs')).read_text(encoding='utf-8-sig')
        renderer = (work / RENDERER).read_text(encoding='utf-8-sig')
        texts[variant] = dict(collection=collection, renderer=renderer, scheduler=(work / SCHEDULER).read_text(encoding='utf-8-sig'),
                              window=(work / WINDOW).read_text(encoding='utf-8-sig'))
        methods = '\n'.join(member(collection, s) for s in (
            'private async Task BackgroundCompilation()', 'private async Task<bool> WaitForShaderModuleCompilation()',
            'public void PromoteBackgroundCompilation()', 'private Task RunBackgroundPipelineCompile(',
            'private void LogBackgroundPipelineFailure(', 'public void CancelPendingWarmUp()',
            'private static bool CancelledByTeardown('))
        dispose = member(collection, 'protected virtual void Dispose(bool disposing)')
        wait = dispose[dispose.index('                CancelPendingWarmUp();'):dispose.index('                for (int i = 0; i < _shaders.Length; i++)')]
        check('_compileTask.Wait();' in wait and 'PromoteBackgroundCompilation();' in wait and 'WaitForBackgroundPipelineQueue();' in wait,
              variant + ': the disposal promotes and waits for the program\'s compiles')
        renderer_methods = member(renderer, 'public void BeginTeardown()')
        call = 'return false;'
        if 'public bool CancelCompilesAtGuestStop(' in renderer:
            renderer_methods += '\n' + member(renderer, 'public bool CancelCompilesAtGuestStop(')
            call = 'return CancelCompilesAtGuestStop(out shaderModules, out pipelines);'
        check(('CancelCompilesAtGuestStop' in renderer) == (variant == 'candidate'), variant + ': guest-stop cancellation only in the candidate')
        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        template = (FIXTURE / 'Double.cs').read_text()
        for mark, code in (('/* SHADER_METHODS */', methods), ('/* DISPOSE_WAIT */', wait), ('/* RENDERER_METHODS */', renderer_methods),
                           ('/* GUEST_STOP_CALL */', call)):
            check(template.count(mark) == 1, 'fixture mark ' + mark)
            template = template.replace(mark, code)
        (fixture / 'Double.cs').write_text(template)
        shutil.copyfile(work / SCHEDULER, fixture / 'BackgroundCompilationScheduler.cs')
        program = (FIXTURE / 'Program.cs').read_text()
        if variant == 'control':
            program = program.replace('        scheduler.CancelPending();\n', '')
        (fixture / 'Program.cs').write_text(program)
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
threads = c['workers'] + 1
check(c['programs'] == k['programs'] == 220, 'the same 220 programs')
check(c['cancelled'] is False and c['compiledDuringDrain'] == 170 and c['modulesDuringDrain'] == 50,
      'control: the drain compiles every queued pipeline and module: ' + str((c['compiledDuringDrain'], c['modulesDuringDrain'])))
check(c['drainMs'] >= 0.8 * 170 * 20 / threads, 'control: the drain lasts as long as the queue: ' + str(c['drainMs']))
check(k['cancelled'] is True and k['compiledDuringDrain'] == 0 and k['modulesDuringDrain'] == 0,
      'candidate: nothing compiled during the drain: ' + str((k['compiledDuringDrain'], k['modulesDuringDrain'])))
check(k['drainMs'] < 500 and k['drainMs'] * 4 < c['drainMs'], 'candidate: the drain does not wait for the queue: ' + str(k['drainMs']))
check(k['guestStopMs'] < 200 and k['runningWhenStopReturned'] is True, 'candidate: the cancellation does not wait for running compiles')
check(k['cancelledPipelines'] == 170 and k['cancelledModules'] == 50, 'candidate: 170 pipelines and 50 modules cancelled: ' +
      str((k['cancelledPipelines'], k['cancelledModules'])))
check(k['reportedPipelines'] == 170 and k['reportedModules'] == 50, 'candidate: the GPU release reports the counts of the guest stop')
check(c['reportedPipelines'] == 0 and c['reportedModules'] == 0, 'control: nothing left to cancel at the GPU release, as on the device')
check(c['blockersCompleted'] and k['blockersCompleted'] and c['blockersStarted'] == k['blockersStarted'] == c['blockers'] == 2 * c['workers'] + 1 and
      c['blockersEnded'] == k['blockersEnded'] == c['blockers'],
      'the compiles a thread was running complete normally')
check(c['saves'] == k['saves'] == 1 and not c['savedWhileCompiling'] and not k['savedWhileCompiling'],
      'the cache is saved once, after the threads are joined')
check(k['lateRefused'] is True and k['lateRan'] == 0, 'candidate: work scheduled after the guest stopped is refused')
check(c['lateRefused'] is True and c['lateRan'] == 2, 'control: the queue still accepted work during the drain')
check(k['failureLines'] == 0 and k['rendererFailures'] == 0, 'candidate: a cancellation is neither logged nor recorded as a failure')
check(c['failureLines'] == 0 and c['rendererFailures'] == 0, 'control: no failure')
check(k['failedPrograms'] == 50 and c['failedPrograms'] == 0, 'candidate: only the programs whose module was cancelled are not linked')
check(sum(1 for line in k['journal'] if line.startswith('teardown compilesCancelled ')) == 1 and
      sum(1 for line in c['journal'] if line.startswith('teardown compilesCancelled ')) == 1, 'one GPU release line each')
line = next(line for line in k['journal'] if line.startswith('teardown compilesCancelled '))
check('shader modules 50, pipelines 170;' in line, 'candidate release line carries the guest-stop counts: ' + line)

ck, kk = texts['control'], texts['candidate']
check(ck['collection'] == kk['collection'], 'ShaderCollection unchanged')
scheduler = kk['scheduler']
queue_cancel = member(scheduler, '            public void CancelPending()')
queue_dispose = member(scheduler, '            public void Dispose()')
check('Join' not in queue_cancel and 'thread.Join();' in queue_dispose and queue_dispose.index('CancelPending();') < queue_dispose.index('thread.Join();'),
      'the cancellation never joins; Dispose cancels, then joins')
check('if (_joined)' in queue_dispose and '_joined = true;' in queue_dispose, 'Dispose joins once, also after a cancellation')
check(queue_cancel.replace('public void CancelPending()', 'public void Dispose()').split('// RewindBox (adapt_guest_stop_compile_cancel)')[0] == '' or
      'Drain(_demandQueue, pending);' in queue_cancel and 'Drain(_highPriorityQueue, pending);' in queue_cancel and
      'Drain(_lowPriorityQueue, pending);' in queue_cancel and '_scheduled.Clear();' in queue_cancel and 'Monitor.PulseAll(_queueLock);' in queue_cancel,
      'every queue is cancelled and the waiting threads are woken')
old_dispose = member(ck['scheduler'], '            public void Dispose()')
joined = queue_cancel[queue_cancel.index('            public void CancelPending()'):].replace('public void CancelPending()', 'public void Dispose()')
tail = old_dispose[old_dispose.index('\n                foreach (Thread thread in _threads)'):]
check(joined.rstrip()[:-1].rstrip() + '\n' + tail == old_dispose, 'CancelPending is the former Dispose without its join')
guest_stop = member(kk['renderer'], 'public bool CancelCompilesAtGuestStop(')
check('Shaders' not in guest_stop.replace('BackgroundCompilationScheduler', '').replace('CancelledShaderCompiles', '') and
      'Dispose' not in guest_stop and 'scheduler.CancelPending();' in guest_stop, 'the guest-stop cancellation touches the scheduler only')
check(member(ck['renderer'], 'public void BeginTeardown()') == member(kk['renderer'], 'public void BeginTeardown()'), 'BeginTeardown unchanged')
check(member(ck['renderer'], 'public unsafe void Dispose()') == member(kk['renderer'], 'public unsafe void Dispose()'), 'VulkanRenderer.Dispose unchanged')
window = kk['window']
i = window.index
check(window.count('CancelRendererCompilesAtGuestStop();') == 1, 'one call')
check(i('"guestStop"') < i('Device.System.Dispose();') < i('CancelRendererCompilesAtGuestStop(); //') < i('"guestStopped"') <
      i('"gpuRelease"') < i('BeginRendererTeardown();\n                    Device.DisposeGpu();'),
      'cancelled right after the guest is terminated, before the drain is waited for; the GPU release is unchanged')
helper = member(window, 'private void CancelRendererCompilesAtGuestStop()')
check('try' in helper and 'catch (Exception error)' in helper and '"guestCompilesCancelled"' in helper and '"guestCompileCancelFailed"' in helper,
      'a failure of the cancellation is journalled and leaves the close as it was')
stripped = window.replace(helper + '\n\n', '', 1).replace('                CancelRendererCompilesAtGuestStop(); // RewindBox (adapt_guest_stop_compile_cancel)\n', '', 1)
start = stripped.index('        // RewindBox (adapt_guest_stop_compile_cancel): the guest is terminated; the compiles still queued')
end = stripped.index('        private void BeginRendererTeardown()')
check(stripped[:start] + stripped[end:] == ck['window'], 'WindowBase unchanged but the call and its helper')

inputs = ['build-utils/melonx/adapt_guest_stop_compile_cancel.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_guest_stop_compile_cancel_test.py', 'test/melonx_guest_stop_compile_cancel/Double.cs',
          'test/melonx_guest_stop_compile_cancel/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionLibraryBuilt=True, nativePipelineDouble=True,
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host scheduler, program disposal waits and teardown order with 20 ms and 10 ms compile doubles; the '
                          'close time on an iPhone is known only from the teardown lines of a device run.')
out = ROOT / 'dist/melonx/guest-stop-compile-cancel-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
