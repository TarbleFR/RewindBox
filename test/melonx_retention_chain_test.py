#!/usr/bin/env python3
"""The retention chain journal of a closed session (adapt_retention_chain): journal only, weak references only.

Usage: melonx_retention_chain_test.py <Core 705 prepared MeloNX tree>
       melonx_retention_chain_test.py <control> --candidate-source <final preparation containing the adapter>

Static checks: only the adapter's replacements, fail closed; the capture runs in WindowBase's guest stop after the
controls are withdrawn and before Horizon.Dispose (which clears the process list), the kernel parts are taken under the
process thread lock; every added reference to a session part is a WeakReference; no collection, no session state change
and no field of a session type are added; the close line follows the sessionRetention line after the final collection;
the first-frame line follows the first-frame compaction and drops the references. The production Ryujinx.Library
(with Ryujinx.HLE) builds with the adapter. Executed: the production RecordRetentionChain with its fields, on real weak
references and threads (test/melonx_retention_chain): a kept part, a released part, a running host thread, a finished
one still referenced and a finished one released: the close line counts them, the first-frame line repeats them and a
third call writes nothing. No device. Writes dist/melonx/retention-chain-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_retention_chain', _HOLD)
import adapt_retention_chain as adapter  # noqa: E402
from adapt_retention_chain import apply, BASELINE, LIBRARY, MEMORY, WINDOW, HORIZON, PROCESS  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
TAG = 'RewindBox (adapt_retention_chain)'
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


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the pinned preparation: ' + name)

window_text = read(SOURCE, WINDOW)
check(window_text.index('Library.WithdrawEmbeddedControls();') < window_text.index('Device.System.Dispose();'),
      'the guest stop withdraws the controls, then terminates the guest (Horizon.Dispose)')
horizon_text = read(SOURCE, HORIZON)
check('KernelContext.Processes.Clear();' in member(horizon_text, 'protected virtual void Dispose(bool disposing)'),
      'Horizon.Dispose clears the process list: the capture must run before it')

replacements = []
original_once = adapter.once
with tempfile.TemporaryDirectory(prefix='melonx-retention-chain-') as temporary:
    temporary = Path(temporary).resolve()
    work = temporary / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)

    def recording_once(path, old, new):
        replacements.append((path.relative_to(work).as_posix(), old, new))
        original_once(path, old, new)

    adapter.once = recording_once
    try:
        changed = apply(work)
    finally:
        adapter.once = original_once
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
    added = ''
    for name in BASELINE:
        undone = read(work, name)
        for path, old, new in reversed(replacements):
            if path == name:
                check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
                undone = undone.replace(new, old)
                added += new.replace(old.strip('\n'), '') if old.strip() in new else new
        check(undone == read(SOURCE, name), name + ' is the preparation but the adapter\'s replacements')
        check(read(work, name).count(TAG) >= 1, 'commented: ' + name)
    if FINAL_PREPARATION:
        later = files_edited_later('adapt_retention_chain')
        for name in BASELINE:
            if name not in later:
                check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

    new_window = read(work, WINDOW)
    check(new_window.index('Library.WithdrawEmbeddedControls();') < new_window.index('Library.NoteSessionParts(Device, this);') <
          new_window.index('Device.System.Dispose();'), 'capture after the controls are withdrawn, before the guest is terminated')
    check(re.search(r'GC\.Collect\s*\(', added) is None and 'GC.WaitForPendingFinalizers' not in added, 'no collection added')
    references = re.findall(r'parts\.Add\(\((.*?)\)\);', added)
    check(references and all('new WeakReference(' in r for r in references), 'every captured part is a weak reference: ' + str(references))
    check(re.search(r'private static (Ryujinx\.HLE\.Switch|WindowBase|Horizon|KernelContext|KProcess|KThread)\b', added) is None,
          'no field of a session type')
    library = read(work, LIBRARY)
    record = member(library, 'internal static void RecordRetentionChain(string when)')
    check('_closingParts = null;' in record and 'part.Target' in record and 'Dispose' not in record,
          'the report reads targets only and drops the references after the first-frame line')
    check(library.index('RecordSessionRetention();\n            // RewindBox (adapt_retention_chain)') > library.index('GC.Collect(2, GCCollectionMode.Aggressive'),
          'the close line follows the final collection and the sessionRetention line')
    memory = member(read(work, MEMORY), 'internal static void AfterFirstFrame()')
    check(memory.index('Compact("firstFrame");') < memory.index('Library.RecordRetentionChain("nextFirstFrame");'),
          'the first-frame line follows the first-frame compaction')
    threads = member(read(work, PROCESS), 'public KThread[] RetentionThreads()')
    check('lock (_threadingLock)' in threads and '_threads.CopyTo(threads, 0);' in threads, 'thread snapshot under the process thread lock')
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo',
                             '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Library (with Ryujinx.HLE) builds with the adapter')

    fixture = temporary / 'fixture'
    fixture.mkdir()
    fields = library[library.index('        private static List<(string Kind, WeakReference Part)> _closingParts;'):
                     library.index('        [MethodImpl(MethodImplOptions.NoInlining)]\n        internal static void NoteSessionParts(')]
    (fixture / 'Production.cs').write_text('using System;\nusing System.Collections.Generic;\nusing System.Text;\n'
                                           'namespace Ryujinx.Library {\n    partial class Library {\n' + fields + record + '\n    }\n}\n')
    shutil.copyfile(ROOT / 'test/melonx_retention_chain/Program.cs', fixture / 'Program.cs')
    (fixture / 'Fixture.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
                                            '<TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit>'
                                            '</PropertyGroup></Project>\n')
    for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                    [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=600, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-4000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, 'fixture: ' + ' '.join(command[1:3]))
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    lines = report['lines']
    check(len(lines) == 2 and lines[0].startswith('retentionChain close after the final collection (full collections since the close: ') and
          lines[1].startswith("retentionChain nextFirstFrame at the next session's first frame"), 'two lines, then nothing: ' + str(lines))
    for line in lines:
        check('still reachable: horizon 0/1; kthread 1/2; window 1/1; host threads 2/3 (running 1: HLE.GuestThread.7)' in line and
              line.endswith('MB (adapt_retention_chain)'), 'parts counted per kind, running host threads named: ' + line)
    check(report['kept'], 'the fixture kept its live parts (the weak references did not)')

inputs = ['build-utils/melonx/adapt_retention_chain.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_retention_chain_test.py',
          'test/melonx_adapter_control.py', 'test/melonx_retention_chain/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core705Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(journalOnly=True, weakReferencesOnly=True, linesPerSession=2, fixtureLines=lines),
               sdk=sdk, physicalDeviceTested=False, productionLibraryBuilt=True, productionReportExecuted=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Journal only. The capture (SessionPartsDiagnostics, KProcess.RetentionThreads) is checked statically and '
                          'built, not executed on a guest; which part holds a closed Hogwarts session is known only from a device run.')
out = ROOT / 'dist/melonx/retention-chain-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, lines=lines)))
