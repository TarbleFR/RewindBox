#!/usr/bin/env python3
"""adapt_guest_break_context on the final preparation, against its predecessor as control.

Usage: melonx_guest_break_context_test.py <predecessor preparation> --candidate-source <final preparation>

IPA 767, Super Smash Bros. Ultimate (pid 33274): the game called svcBreak after 29 minutes and the process ended; the Core
journal holds only "The guest program broke execution!" (docs/melonx-ipa767-ssbu-break-2026-11-17.md).

Static: only Syscall.cs changes, its two replacements applied once to the control give the final file and reverse to it;
in Break the journal line comes after the Exiting check and before the error line, TerminateCurrentProcess and the
exception, which are unchanged and in their order; the class (between its markers) writes no guest memory, takes no
lock, changes no state and reads only X1 and X2 of the general-purpose registers.
Built: the candidate's production Ryujinx.HLE.
Executed (test/melonx_guest_break_context/Program.cs, built as Ryujinx.Tests against that Ryujinx.HLE, with the real
KThread, KProcess, HleProcessDebugger, a real software address space and the real journal): the line for a break (reason,
kind, info address, size, the guest thread id and name, FP, LR, SP and PC as module offsets, the two guest frames, no
other register); with a 4-byte info, the bytes read as result 2002-0001, written through the journal whole; 64 and 256
bytes in groups of four; nothing read for size 0, past 256, unmapped or crossing the end of a mapping; the kinds; no
thread; a broken thread object contained part by part; 34 stack lines and 3600 characters at most.
No device. Writes dist/melonx/guest-break-context-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
import adapt_guest_break_context as adapter  # noqa: E402

FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_guest_break_context', _HOLD)
DOTNET = os.environ.get('DOTNET', 'dotnet')
SYSCALL = adapter.SYSCALL
FIXTURE = 'test/melonx_guest_break_context/Program.cs'
BEGIN, END = '    // RewindBox (adapt_guest_break_context) begin\n', '    // RewindBox (adapt_guest_break_context) end\n'
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


check(FINAL_PREPARATION, 'the candidate is the final preparation containing the adapter')
for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'control is the predecessor preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-guest-break-') as temporary:
    work = Path(temporary).resolve() / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)
    changed = adapter.apply(work)
    check([str(p.relative_to(work)) for p in changed] == [SYSCALL], 'the adapter changes Syscall.cs only')
    final = (FINAL_SOURCE / SYSCALL).read_text(encoding='utf-8-sig')
    check((work / SYSCALL).read_text(encoding='utf-8-sig') == final, 'the control plus the adapter is the final Syscall.cs')
    control_text = (SOURCE / SYSCALL).read_text(encoding='utf-8-sig')
    reverted = final
    for _, old, new in reversed(adapter.PAIRS):
        check(reverted.count(new) == 1 and control_text.count(old) == 1, 'each replacement once')
        reverted = reverted.replace(new, old)
    check(reverted == control_text, 'the replacements reverse to the control')

    brk = member(final, 'public void Break(ulong reason)')
    control_brk = member(control_text, 'public void Break(ulong reason)')
    line = 'EmbeddedLaunchDiagnostics.Record("guestBreak", "context", detail: GuestBreakContext.Describe(currentThread, reason, 250));'
    order = ['currentThread.PrintGuestStackTrace();', 'currentThread.PrintGuestRegisterPrintout();',
             'if (currentThread.Owner.State == ProcessState.Exiting)', line,
             'Logger.Error?.Print(LogClass.KernelSvc, "The guest program broke execution!");', 'Logger.Flush();',
             'currentThread.Owner.TerminateCurrentProcess();', 'throw new GuestBrokeExecutionException();']
    check(brk.count(line) == 1 and all(brk.count(s) == 1 for s in order) and
          [brk.index(s) for s in order] == sorted(brk.index(s) for s in order) and
          brk.index(line) < brk.index('else') and all(control_brk.count(s) == 1 for s in order if s != line),
          'Break journals the context after the Exiting check, before the error line, the termination and the exception')
    cls = final[final.index(BEGIN):final.index(END) + len(END)]
    check(not re.search(r'\.Write<|(?<!Append)\.Write\(|SetActivity|Pause|Map\(|Unmap\(|Reprotect|lock \(|GC\.', cls) and
          re.findall(r'GetX\((\d+)\)', cls) == ['1', '2'] and 'GetGuestRegisterPrintout' in cls and
          all(register in cls for register in ('"FP:"', '"LR:"', '"SP:"', '"PC:"')) and 'IsRangeMapped(info, size)' in cls and
          'MaxInfoBytes = 0x100' in cls and 'MaxLength = 3600' in cls and 'MaxFrameLines = 34' in cls,
          'the context writes no guest memory, takes no lock, reads X1 and X2 only and is bounded')

    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.HLE/Ryujinx.HLE.csproj'), '-c', 'Release', '-nologo',
                             '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=3600, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.HLE builds with the adapter')

    fixture = work / 'src/GuestBreakFixture'
    fixture.mkdir()
    shutil.copyfile(ROOT / FIXTURE, fixture / 'Program.cs')
    (fixture / 'GuestBreakFixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><AssemblyName>Ryujinx.Tests</AssemblyName>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
        '<NoWarn>CS0067;CS0414;CS0649;CS8321;CA1416</NoWarn>'
        '</PropertyGroup><ItemGroup><ProjectReference Include="../Ryujinx.HLE/Ryujinx.HLE.csproj" /></ItemGroup></Project>\n')
    build = subprocess.run([DOTNET, 'build', str(fixture / 'GuestBreakFixture.csproj'), '-c', 'Release', '-nologo', '-m:1',
                            '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800, env=environment, cwd=work)
    if build.returncode:
        print(build.stdout[-6000:], build.stderr[-3000:], flush=True)
    check(build.returncode == 0, 'fixture builds against the production Ryujinx.HLE')
    journal = work / 'journal' / 'MeloNX-core.log'
    journal.parent.mkdir()
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Ryujinx.Tests.dll'), str(journal)], capture_output=True,
                         text=True, timeout=300, env=environment)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-3000:], flush=True)
    check(run.returncode == 0, 'fixture runs')
    report = json.loads(next(l for l in run.stdout.splitlines() if l.startswith('{')))

registers = report['registers']
for expected in ('guestBreakContext; reason=0x0 (Panic); info=0x0000000010005000; size=0x10000510; guestThread=72; guestThreadName=MainThread\n',
                 '\ninfo bytes: not read (size)\n',
                 '\nregisters at the break (FP LR SP PC):\nFP: 0x0000000010001000 (main:0x1000) =>',
                 '\nLR: 0x0000000010000404 (main:0x0404) =>', '\nSP: 0x0000000010001800 (main:0x1800) =>',
                 '\nPC: 0x0000000010000400 (main:0x0400) =>', '\nguest stack:\nProcess: Fixture, PID: 81\nThread ID: 72 (MainThread)\n',
                 '\n0x0000000010000444 main:0x0444', '\n0x0000000010000888 main:0x0888'):
    check(expected in registers, 'break context holds ' + repr(expected) + ': ' + registers)
check(not re.search(r'X\[\d\d\]|0x00000000100005[0-9a-f]{2}', registers), 'no other general-purpose register in the line')
check(registers.count('\n0x00000000100') == 2 and len(registers) <= 3600 and '[redacted' not in registers,
      'two guest frames, bounded, nothing redacted')
text = report['result4']
# The fixture has no page table: the printout's lookup of a value outside the images (the reason 0, the size 4) fails
# and is contained; the info bytes and the stack are kept.
for expected in ('guestBreakContext; reason=0x0 (Panic); info=0x0000000010005000; size=0x4; guestThread=72; guestThreadName=MainThread\n',
                 '\ninfo bytes: 02020000 (as a result: 0x00000202, 2002-0001)\n',
                 '\nregisters at the break (FP LR SP PC):\n(unavailable: NullReferenceException)\nguest stack:\n',
                 '\n0x0000000010000444 main:0x0444', '\n0x0000000010000888 main:0x0888'):
    check(expected in text, 'break context holds ' + repr(expected) + ': ' + text)
check(report['safeUnchanged'] and report['journal'] == 'guestBreak/context/' + text, 'the journal writes the line whole')
b64 = report['bytes64']
check(b64.startswith('guestBreakContext; reason=0x1 (Assert); info=0x0000000010005000; size=0x40;') and
      '\ninfo bytes: 02020000 010000a0 020000a0 ' in b64 and 'as a result' not in b64 and
      len(re.search(r'\ninfo bytes: ([0-9a-f ]+)\n', b64).group(1).split()) == 16, '64 bytes in groups of four: ' + b64)
check(report['bytes256'] == 256 * 2 + 63, '256 bytes read: ' + str(report['bytes256']))
check(report['tooLarge'] == 'not read (size)' and report['zeroSize'] == 'not read (size)' and
      report['unmapped'] == 'not read (unmapped)' and report['straddling'] == 'not read (unmapped)', 'bounded reads: ' + str(report))
check(report['kinds'] == 'Panic,Assert,User,PreLoadDll,PostLoadDll,PreUnloadDll,PostUnloadDll,CppException,unknown' and
      report['notification'] == 'User', 'kinds')
check(report['noThread'] == 'guestBreakContext; reason=0x7 (CppException); unavailable=no guest thread', 'no thread: ' + report['noThread'])
broken = report['broken']
check(broken.startswith('guestBreakContext; reason=0x0 (Panic); info=0x0000000010005000; size=0x4;') and
      broken.count('(unavailable: NullReferenceException)') >= 3 and '[redacted' not in broken,
      'a broken thread object is contained part by part: ' + broken)
check(report['boundedLength'] <= 3600 and report['boundedEndsWithMore'] and not report['boundedKeepsX0'] and
      report["boundedFrameLines"] == 5 + 34 + 1, 'at most 34 stack lines, X registers dropped: ' + str(report['boundedFrameLines']))
check(report['hugeLength'] == 3600, 'text cut at 3600 characters')

inputs = ['build-utils/melonx/adapt_guest_break_context.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_adapter_control.py',
          'test/melonx_guest_break_context_test.py', FIXTURE]
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE},
               sdk=sdk, guestBreakContext=dict(executed=True, sample=registers, resultSample=text), physicalDeviceTested=False,
               productionHleAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='JIT runtime on Linux, not NativeAOT on iOS; the guest objects are real classes built without a '
                          'kernel (fields set) and no page table, so the register printout resolves only values inside the images; Break '
                          'itself is checked in the source, not executed (it ends the process)')
out = ROOT / 'dist/melonx/guest-break-context-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
