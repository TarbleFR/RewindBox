#!/usr/bin/env python3
"""Guest threads at a host pause (adapt_pause_guest_threads) on the real prepared engine. Diagnostics only.

Usage: melonx_pause_guest_threads_test.py <Core 642 prepared MeloNX tree>
       melonx_pause_guest_threads_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the prepared tree and builds the production Ryujinx.HLE assembly for the control and
the candidate. Static checks bind that TogglePauseEmulation is unchanged but one call made before the application is
suspended, and that the record neither enters nor leaves the critical section, suspends, resumes, reschedules nor writes
a thread. The real NoteGuestThreadsAtPause and KProcess.SnapshotThreads run with doubles of the kernel types
(test/melonx_pause_guest_threads/Program.cs): a thread able to run that no core ran for 12 s is named, waits are told
apart (synchronization object, condition variable, arbiter, other), at most 3 records of 64 threads, no thread written,
the critical section never entered. No device. Writes dist/melonx/pause-guest-threads-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_pause_guest_threads', _HOLD)
from adapt_pause_guest_threads import apply, BASELINE  # noqa: E402

HORIZON = 'src/Ryujinx.HLE/HOS/Horizon.cs'
PROCESS = 'src/Ryujinx.HLE/HOS/Kernel/Process/KProcess.cs'
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


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 642 preparation: ' + name)
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
texts = {}
with tempfile.TemporaryDirectory(prefix='melonx-pause-threads-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                for name in BASELINE:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.HLE/Ryujinx.HLE.csproj'), '-c', 'Release', '-nologo',
                                 '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.HLE assembly builds')

    control, candidate = texts['control'], texts['candidate']
    toggle_c = member(control[HORIZON], 'public void TogglePauseEmulation(bool pause)')
    toggle_k = member(candidate[HORIZON], 'public void TogglePauseEmulation(bool pause)')
    inserted = '''                        if (pause && !IsPaused)
                        {
                            // RewindBox (adapt_pause_guest_threads): diagnostics only, before the threads are suspended.
                            NoteGuestThreadsAtPause(process);
                        }

'''
    check(toggle_k.replace(inserted, '') == toggle_c and toggle_k.count('NoteGuestThreadsAtPause(process);') == 1,
          'TogglePauseEmulation unchanged but one call')
    check(toggle_k.index('NoteGuestThreadsAtPause(process);') < toggle_k.index('process.SetActivity(pause);'), 'recorded before the suspension')
    start = candidate[HORIZON].index('        // RewindBox (adapt_pause_guest_threads): the first host pauses')
    record = candidate[HORIZON][start:candidate[HORIZON].index('        internal IDebuggableProcess DebugGetApplicationProcessDebugInterface()')]
    check(not re.search(r'CriticalSection\.(Enter|Leave)|SetActivity|Suspend\(|Resume\(|Reschedule|SelectThread|'
                        r'thread\.\w+\s*=[^=]|\.Signal\(|TickSource|AudioDeviceDriver', record), 'record changes no state')
    check('lock (KernelContext.CriticalSection.Lock)' in record and 'PauseRecordLimit = 3;' in record and
          'PauseRecordThreadLimit = 64;' in record, 'monitor only, bounded')
    snapshot = member(candidate[PROCESS], 'internal KThread[] SnapshotThreads()')
    check('lock (_threadingLock)' in snapshot and '_threads.CopyTo(threads, 0);' in snapshot, 'thread list copied under its lock')
    check(candidate[PROCESS].replace(snapshot + '\n\n', '').replace(
        '        // RewindBox (adapt_pause_guest_threads): a copy of this process\'s thread list for the host-pause record.\n', '')
          == control[PROCESS], 'KProcess unchanged but the copy')

    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    program = (ROOT / 'test/melonx_pause_guest_threads/Program.cs').read_text()
    (fixture / 'Program.cs').write_text(program.replace('//__SNAPSHOT__\n', snapshot + '\n').replace('//__RECORD__\n', record))
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0414;CS0649</NoWarn></PropertyGroup></Project>\n')
    for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                    [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    print(json.dumps(report)[:3000], flush=True)

records = report['records']
check(len(records) == 3 and report['lines'] == 3 * 64, 'three records of at most 64 threads')
check(report['writes'] == 0, 'no thread written')
first = records[0]
check(first.startswith('guestThreads hostPause 1 78 threads: able to run 4 (on a guest core 1), waiting 60, other 0; '), first)
check('able to run but not run for 500 ms or more: <AK::BankManager> (12000 ms, prio 44, core 2); longest waits: ' in first and
      '<Paused>' not in first.split('longest waits')[0] and '<TaskGraphThreadHP 2>' not in first, 'starved thread named, others not: ' + first)
check('<AK::IOThread> 15000 ms sync wait on KEvent; <PoolThread 1> 3000 ms mutex/condition variable 0x8000; '
      '<RHIThread> 900 ms address arbiter; <FAsyncLoadingThread> 400 ms other wait' in first, 'waits told apart: ' + first)
lines = report['firstLines']
check(lines[0].startswith('Host pause #1 guest thread 1/78: <MainThread> id 7 prio 28/28 core 0') and
      lines[0].endswith('Running; -; running on a guest core'), lines[0])
check(lines[1].endswith('Running; -; last ran 12000 ms ago') and 'force-pause ProcessPauseFlag' in lines[7], 'per-thread lines')

inputs = ['build-utils/melonx/adapt_pause_guest_threads.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_pause_guest_threads_test.py', 'test/melonx_pause_guest_threads/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core642Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               report=report, sdk=sdk, physicalDeviceTested=False, productionHleAssemblyBuilt=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Diagnostics only; which guest thread holds the black launch is known only from a device run '
                          'that pauses during it.')
out = ROOT / 'dist/melonx/pause-guest-threads-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
