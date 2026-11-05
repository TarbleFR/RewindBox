#!/usr/bin/env python3
"""Guest thread, control registers and guest stack after a guest memory fault crash (adapt_guest_fault_context).

Usage: melonx_guest_fault_context_test.py <Core 658 prepared MeloNX tree>
       melonx_guest_fault_context_test.py <control> --candidate-source <final preparation containing the change>

Control is the Core 658 preparation (its EmbeddedRuntime.cs is native/melonx/EmbeddedRuntime.cs as delivered);
candidate adds the adapter (KernelStatic.cs) and this checkout's native/melonx/EmbeddedRuntime.cs. Static: KernelStatic
is the control plus the GuestFaultContext class only, EmbeddedRuntime the control plus the second UnhandledException
handler only (the RecordCrash subscription kept first). For each side the production Ryujinx.Library builds (with
Ryujinx.HLE). Behaviour: a fixture built as Ryujinx.Tests against that side's production Ryujinx.HLE copies that side's
real UnhandledException subscriptions and runs them with the real journal and the real KThread / KProcess /
HleProcessDebugger code over a real software address space (AddressSpaceManager) holding a guest frame chain, TLS and
thread name; an exception is left unhandled on a thread and the process ends (JIT runtime). The control writes one crash
line in every case; the candidate adds a second line (guest thread id and name, FP/LR/SP/PC as module offsets, the
guest frames, no general-purpose register) only for an InvalidMemoryRegionException (or one wrapped in it) on a guest
thread, keeps one line for a host thread or another exception, contains a broken guest object, and bounds the capture
to 250 ms and 3600 characters. Writes dist/melonx/guest-fault-context-checks.json. No device.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_guest_fault_context', _HOLD)
from adapt_guest_fault_context import apply, BASELINE, CONTEXT_CLASS  # noqa: E402

KERNEL = 'src/Ryujinx.HLE/HOS/Kernel/KernelStatic.cs'
RUNTIME = 'src/Ryujinx.Library/EmbeddedRuntime.cs'
NATIVE_RUNTIME = 'native/melonx/EmbeddedRuntime.cs'
RUNTIME_BASELINE = '97737b97bb425d1310aea4bc119821def33750aee3539573a9dff2cb573e71f1'  # Core 658 (= native as delivered)
FIXTURE = 'test/melonx_guest_fault_context/Program.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
ENVIRONMENT = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
SUBSCRIPTION_ADDED = '''        // RewindBox (adapt_guest_fault_context): after the crash line, a guest memory fault on a guest thread adds the
        // thread's name, control registers and guest stack (at most 250 ms and 3600 characters; nothing otherwise).
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            string guest = Ryujinx.HLE.HOS.Kernel.GuestFaultContext.Describe(e.ExceptionObject, 250);
            if (guest != null) EmbeddedLaunchDiagnostics.RecordCrash(guest);
        };
'''
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


for name, expected in BASELINE.items():
    check(sha(SOURCE / name) == expected, 'not the Core 658 preparation: ' + name)
if FINAL_PREPARATION and sha(SOURCE / RUNTIME) != RUNTIME_BASELINE:
    # Core gate form (Core 661): control_source reverses only the adapter's KernelStatic edits; EmbeddedRuntime.cs is a
    # native source prepare_embedded.py copies, so the control copy still holds this checkout's handler. The Core 658
    # file is this checkout's native runtime without the added subscription (checked against RUNTIME_BASELINE).
    native_runtime = (ROOT / NATIVE_RUNTIME).read_text(encoding='utf-8')
    check(native_runtime.count(SUBSCRIPTION_ADDED) == 1, 'the native runtime holds the added subscription once')
    (SOURCE / RUNTIME).write_text(native_runtime.replace(SUBSCRIPTION_ADDED, '', 1), encoding='utf-8')
check(sha(SOURCE / RUNTIME) == RUNTIME_BASELINE, 'not the Core 658 EmbeddedRuntime.cs')
if FINAL_PREPARATION:
    check((FINAL_SOURCE / RUNTIME).read_bytes() == (ROOT / NATIVE_RUNTIME).read_bytes(), 'final preparation holds this EmbeddedRuntime.cs')

texts, reports, crashes = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-guest-fault-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            shutil.copyfile(ROOT / NATIVE_RUNTIME, work / RUNTIME)
            if FINAL_PREPARATION:
                for name in BASELINE:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in (KERNEL, RUNTIME)}
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo',
                                 '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=ENVIRONMENT, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.Library (with Ryujinx.HLE) builds')
        print(variant + ': production Ryujinx.Library built', flush=True)

        # The side's real subscriptions, from its EmbeddedRuntime.cs.
        subscribe = member(texts[variant][RUNTIME], 'private static void EmbeddedSubscribeDiagnostics()')
        first = subscribe.index('        AppDomain.CurrentDomain.UnhandledException')
        subscription = subscribe[first:subscribe.rindex('    }')]
        fixture = work / 'src/GuestFaultFixture'
        fixture.mkdir()
        (fixture / 'Program.cs').write_text((ROOT / FIXTURE).read_text().replace('        //__SUBSCRIPTION__\n', subscription))
        (fixture / 'GuestFaultFixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><AssemblyName>Ryujinx.Tests</AssemblyName>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
            '<NoWarn>CS0067;CS0414;CS0649;CS8321;CA1416</NoWarn>'
            + ('<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if variant == 'candidate' else '') +
            '</PropertyGroup><ItemGroup><ProjectReference Include="../Ryujinx.HLE/Ryujinx.HLE.csproj" /></ItemGroup></Project>\n')
        result = subprocess.run([DOTNET, 'build', str(fixture / 'GuestFaultFixture.csproj'), '-c', 'Release', '-nologo', '-m:1',
                                 '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800, env=ENVIRONMENT, cwd=work)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ' fixture builds against the production Ryujinx.HLE')
        program = fixture / 'bin/Release/net10.0/Ryujinx.Tests.dll'
        crashes[variant] = {}
        for mode in ('guest', 'host', 'other', 'nested', 'broken'):
            journal = work / ('journal-' + mode) / 'MeloNX-core.log'
            journal.parent.mkdir()
            run = subprocess.run([DOTNET, str(program), mode, str(journal)], capture_output=True, text=True, timeout=300, env=ENVIRONMENT)
            rows = []
            for line in journal.read_text().splitlines() if journal.exists() else []:
                row = json.loads(line[line.index('{'):])
                if row['stage'] == 'crash':
                    rows.append(row)
            crashes[variant][mode] = dict(exitCode=run.returncode, rows=rows)
        if variant == 'candidate':
            journal = work / 'journal-unit' / 'MeloNX-core.log'
            journal.parent.mkdir()
            run = subprocess.run([DOTNET, str(program), 'unit', str(journal)], capture_output=True, text=True, timeout=300, env=ENVIRONMENT)
            if run.returncode:
                print(run.stdout[-4000:], run.stderr[-3000:], flush=True)
            check(run.returncode == 0, 'candidate unit mode runs')
            reports['unit'] = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))

# Static: one class added to KernelStatic, one handler added after the RecordCrash subscription.
control, candidate = texts['control'], texts['candidate']
kernel = candidate[KERNEL]
check(kernel.count(CONTEXT_CLASS) == 1 and kernel.replace(CONTEXT_CLASS, '', 1) == control[KERNEL], 'KernelStatic unchanged but GuestFaultContext')
check(not re.search(r'\.Write<|(?<!Volatile)\.Write\(|SetActivity|Pause|Map\(|Unmap\(|Reprotect|lock \(', CONTEXT_CLASS),
      'GuestFaultContext writes no guest memory, changes no mapping or thread state and takes no lock')
check('GetX(' not in CONTEXT_CLASS and 'GetGuestRegisterPrintout' in CONTEXT_CLASS and
      all(register in CONTEXT_CLASS for register in ('"FP:"', '"LR:"', '"SP:"', '"PC:"')), 'only FP, LR, SP and PC kept')
runtime = candidate[RUNTIME]
crash_line = '        AppDomain.CurrentDomain.UnhandledException += (_, e) => EmbeddedLaunchDiagnostics.RecordCrash(e.ExceptionObject);\n'
check(runtime.count(SUBSCRIPTION_ADDED) == 1 and runtime.replace(SUBSCRIPTION_ADDED, '', 1) == control[RUNTIME] and
      runtime.index(crash_line) + len(crash_line) == runtime.index(SUBSCRIPTION_ADDED),
      'EmbeddedRuntime unchanged but the second handler, right after the RecordCrash subscription')

# Behaviour.
c, k = crashes['control'], crashes['candidate']
first_line = lambda row: row['diagnostic'].split('\n')[0]
for mode in c:
    check(c[mode]['exitCode'] != 0 and k[mode]['exitCode'] != 0, mode + ': the process still ends')
    check(len(c[mode]['rows']) == 1 and c[mode]['rows'][0]['status'] == 'unhandledException', mode + ': control writes one crash line')
    check(len(k[mode]['rows']) >= 1 and first_line(k[mode]['rows'][0]) == first_line(c[mode]['rows'][0]) and
          k[mode]['rows'][0]['status'] == 'unhandledException', mode + ': candidate writes the same crash line first')
for mode in ('host', 'other'):
    check(len(k[mode]['rows']) == 1, mode + ': nothing added for a host thread or another exception')
for mode in ('guest', 'nested', 'broken'):
    rows = k[mode]['rows']
    check(len(rows) == 2 and rows[1]['status'] == 'unhandledException' and rows[1]['sequence'] > rows[0]['sequence'] and
          rows[1]['diagnostic'].startswith('guestFaultContext; guestThread=80; guestThreadName='), mode + ': one guest context line after the crash line')
guest = k['guest']['rows'][1]['diagnostic']
for expected in ('guestThreadName=FHeartBeatThread;', '\nFP: 0x0000000010001000 (main:0x1000) =>',
                 '\nLR: 0x0000000010000404 (main:0x0404) =>', '\nSP: 0x0000000010001800 (main:0x1800) =>',
                 '\nPC: 0x0000000010000400 (main:0x0400) =>', '\nguest stack:\nProcess: Fixture, PID: 81\nThread ID: 80 (FHeartBeatThread)\n',
                 '\n0x0000000010000444 main:0x0444', '\n0x0000000010000888 main:0x0888'):
    check(expected in guest, 'guest context holds ' + repr(expected) + ': ' + guest)
check(not re.search(r'X\[\d\d\]|0x00000000100005[0-9a-f]{2}', guest), 'no general-purpose register in the journal')
check(guest.count('\n0x00000000100') == 2 and len(guest) <= 3600 and '[redacted' not in guest, 'two guest frames, bounded, nothing redacted')
check(k['nested']['rows'][1]['diagnostic'] == guest, 'an InvalidMemoryRegionException wrapped in another is described the same way')
broken = k['broken']['rows'][1]['diagnostic']
check(broken.count('\n(unavailable: NullReferenceException)') == 2 and '[redacted' not in broken,
      'a broken guest object is contained part by part: ' + broken)
unit = reports['unit']
check(unit['nullForObject'] and unit['nullForOther'] and unit['nullOnHostThread'] and unit['nestedDetected'], 'Describe only for a guest memory fault on a guest thread')
check(unit['timeoutText'] == 'guestFaultContext; unavailable=timeout after 250 ms' and unit['timeoutMs'] < 1500,
      'a stuck capture is abandoned after the budget: ' + str(unit['timeoutMs']) + ' ms')
check(unit['throwText'] == 'guestFaultContext; unavailable=InvalidMemoryRegionException', 'a failing capture is contained')
check(unit['direct'] == guest and unit['directSafeUnchanged'], 'the journal\'s redactor keeps the context text whole')
check(unit['boundedLength'] <= 3600 and unit['boundedEndsWithMore'] and not unit['boundedKeepsX0'] and unit['boundedFrameLines'] == 3 + 34 + 1,
      'at most 34 stack lines (header and 32 frames), X registers dropped')
check(unit['hugeLength'] == 3600, 'text cut at 3600 characters')

inputs = ['build-utils/melonx/adapt_guest_fault_context.py', 'build-utils/melonx/adapt_session.py', NATIVE_RUNTIME,
          'test/melonx_guest_fault_context_test.py', FIXTURE, 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               sourceBaseline=dict(BASELINE, **{RUNTIME: RUNTIME_BASELINE}),
               postimages={p: sha(FINAL_SOURCE / p) for p in [*BASELINE, RUNTIME]} if FINAL_PREPARATION else {},
               sdk=sdk, physicalDeviceTested=False, productionLibraryBuilt=True, productionHleAssemblyBuilt=True,
               guestContextSample=guest, unit=unit,
               crashLines={side: {mode: len(v['rows']) for mode, v in crashes[side].items()} for side in crashes},
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='JIT runtime on Linux, not NativeAOT on iOS: the device crash handler runs on the faulting guest thread '
                          'only if NativeAOT raises UnhandledException there (the delivered crash lines show it does). The guest '
                          'objects are real classes built without a kernel (fields set); register values are those of the last '
                          'guest dispatch, stale inside a JIT block, so PC names the last dispatched block, not the faulting '
                          'instruction. X0-X28 are not journaled by rule.')
out = ROOT / 'dist/melonx/guest-fault-context-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
