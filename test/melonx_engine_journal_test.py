#!/usr/bin/env python3
"""Execute the engine journal's repeat bound and unhandled-exception record.

Only synthetic diagnostics are used; no guest runs. The production
EmbeddedLaunchDiagnostics.cs is compiled as is, and the probe forwards engine
logs and unhandled exceptions exactly as EmbeddedRuntime.cs does (both lines
are checked in the source). The crash probe also runs as NativeAOT, the
runtime the iPhone engine uses, where the Linux toolchain is available.
The control is the delivered 562 journal: a repeated text is written once per
occurrence and an unhandled exception leaves nothing in app.log.
"""
import argparse, hashlib, json, os, shutil, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '9b40129fa188f8e2aa6a35c94abea005406062d3'
JOURNAL = 'native/melonx/EmbeddedLaunchDiagnostics.cs'
RUNTIME = 'native/melonx/EmbeddedRuntime.cs'
SECRET = 'a' * 64
CEILING = 5 * 1024 * 1024

runtime = (ROOT / RUNTIME).read_text()
assert 'EmbeddedLaunchDiagnostics.RecordEngine(entry.Level == LogLevel.Error, entry.Message);' in runtime
assert 'AppDomain.CurrentDomain.UnhandledException += (_, e) => EmbeddedLaunchDiagnostics.RecordCrash(e.ExceptionObject);' in runtime
# Registered once per process, with the engine log subscription.
subscribe = runtime[runtime.index('private static void EmbeddedSubscribeDiagnostics()'):runtime.index('[UnmanagedCallersOnly(EntryPoint = "neostation_melonx_diagnostics_abi")]')]
assert 'if (EmbeddedLogSubscribed) return;' in subscribe and 'RecordCrash' in subscribe

PROGRAM = r'''using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using Ryujinx.Common;

string path = Path.GetFullPath(args[1]);
EmbeddedLaunchDiagnostics.ConfigureJournal(path);
var engine = typeof(EmbeddedLaunchDiagnostics).GetMethod("RecordEngine")?.CreateDelegate<Action<bool, string>>();
var crash = typeof(EmbeddedLaunchDiagnostics).GetMethod("RecordCrash")?.CreateDelegate<Action<object>>();
// EmbeddedRuntime's forwarding; the 562 engine called Record and had no handler.
void Forward(bool error, string message)
{
    if (engine != null) engine(error, message);
    else EmbeddedLaunchDiagnostics.Record(EmbeddedLaunchDiagnostics.Stage, error ? "engineError" : "engineWarning", detail: message);
}
switch (args[0])
{
    case "repeat":
        EmbeddedLaunchDiagnostics.Begin();
        for (int i = 0; i < 1000; i++) Forward(true, "Gpu GetInfo: Invalid texture format 0x25A5A (sRGB: True).");
        for (int i = 0; i < 3; i++) Forward(false, "ServiceBsd WriteBsdResult: Operation failed with error EBADF.");
        // Eight threads, one text: counts are taken under the journal gate.
        var threads = Enumerable.Range(0, 8).Select(_ => new Thread(() =>
        {
            for (int i = 0; i < 1000; i++) Forward(false, "Gpu TryGetGraphicsPipeline: concurrent");
        })).ToArray();
        foreach (var thread in threads) thread.Start();
        foreach (var thread in threads) thread.Join();
        // More distinct texts than are tracked: each first occurrence is kept.
        for (int i = 0; i < 1100; i++) Forward(false, "distinct " + i);
        // A new game restarts the counts.
        EmbeddedLaunchDiagnostics.Begin();
        Forward(true, "Gpu GetInfo: Invalid texture format 0x25A5A (sRGB: True).");
        var tracked = typeof(EmbeddedLaunchDiagnostics).GetField("EngineRepeats", BindingFlags.NonPublic | BindingFlags.Static)?.GetValue(null);
        Console.WriteLine("{\"tracked\": " + ((tracked as System.Collections.ICollection)?.Count ?? -1) + "}");
        break;
    case "crash":
        if (crash != null) AppDomain.CurrentDomain.UnhandledException += (_, e) => crash(e.ExceptionObject);
        var worker = new Thread(() => throw new InvalidOperationException("synthetic engine crash " + new string('a', 64)));
        worker.Start();
        worker.Join();
        break;
}
'''


def build(work: Path, journal: str, aot: bool) -> list:
    project = work / 'probe'
    project.mkdir(parents=True)
    (project / 'Journal.cs').write_text(journal)
    (project / 'Program.cs').write_text(PROGRAM)
    (project / 'Probe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><InvariantGlobalization>true</InvariantGlobalization>{'<PublishAot>true</PublishAot>' if aot else ''}
</PropertyGroup></Project>''')
    if aot:
        machine = {'x86_64': 'x64', 'amd64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}[os.uname().machine.lower()]
        rid = ('osx-' if os.uname().sysname == 'Darwin' else 'linux-') + machine
        subprocess.run(['dotnet', 'publish', str(project), '-c', 'Release', '-r', rid, '--nologo', '-v:q',
                        '-o', str(work / 'aot')], check=True, timeout=900)
        return [str(work / 'aot/Probe')]
    subprocess.run(['dotnet', 'build', str(project), '-c', 'Release', '--nologo', '-v:q'], check=True, timeout=600)
    return ['dotnet', str(project / 'bin/Release/net10.0/Probe.dll')]


def records(path: Path):
    rows = []
    for line in path.read_bytes().decode('utf-8', 'replace').splitlines():
        if line.startswith('[MeloNX:core] '):
            rows.append(json.loads(line[len('[MeloNX:core] '):]))
    return rows


def repeat(work: Path, probe: list):
    path = work / 'repeat/app.log'
    path.parent.mkdir()
    out = subprocess.run([*probe, 'repeat', str(path)], check=True, capture_output=True, text=True).stdout
    rows = records(path)
    by = lambda text: [r['diagnostic'] for r in rows if r['diagnostic'].startswith(text)]
    return dict(texture=by('Gpu GetInfo'), socket=by('ServiceBsd'), concurrent=by('Gpu TryGetGraphicsPipeline'),
                distinct=len(by('distinct ')), total=len(rows), statuses=sorted({r['status'] for r in rows}),
                tracked=json.loads(out.strip().splitlines()[-1])['tracked'])


def crash(work: Path, probe: list):
    path = work / 'crash/app.log'
    path.parent.mkdir()
    # Past the ceiling the journal stops, as it did on the device after 11:37.
    with path.open('wb') as journal:
        journal.write(b'frontend line\n' * (CEILING // 14 + 1))
    size = path.stat().st_size
    child = subprocess.run([*probe, 'crash', str(path)], capture_output=True, text=True, timeout=120)
    rows = [r for r in records(path) if r['stage'] == 'crash']
    text = path.read_bytes()
    return dict(exitCode=child.returncode, grew=path.stat().st_size - size, crashRecords=rows,
                secretWritten=SECRET.encode() in text, stderr=child.stderr[-600:])


def check(old, new, aot):
    failures = []

    def expect(condition, message):
        if not condition:
            failures.append(message)

    o, n = old['repeat'], new['repeat']
    texture = 'Gpu GetInfo: Invalid texture format 0x25A5A (sRGB: True).'
    expect(len(o['texture']) == 1001 and len(o['concurrent']) == 8000, f'562: every occurrence written: {len(o["texture"])}, {len(o["concurrent"])}')
    powers = [16, 32, 64, 128, 256, 512]
    expect(n['texture'] == [texture] * 8 + [f'{texture} (repeated {p} times)' for p in powers] + [texture],
           f'fixed: 8 occurrences, then powers of two, restarted by Begin: {n["texture"]}')
    expect(n['socket'] == ['ServiceBsd WriteBsdResult: Operation failed with error EBADF.'] * 3, f'fixed: rare text kept: {n["socket"]}')
    concurrent = ['Gpu TryGetGraphicsPipeline: concurrent'] * 8 + [f'Gpu TryGetGraphicsPipeline: concurrent (repeated {1 << k} times)' for k in range(4, 13)]
    expect(sorted(n['concurrent']) == sorted(concurrent), f'fixed: concurrent counts exact: {n["concurrent"]}')
    expect(n['distinct'] == 1100 and 0 <= n['tracked'] <= 1024, f'fixed: every new text kept, tracking bounded: {n["distinct"]}, {n["tracked"]}')
    expect(n['statuses'] == ['engineError', 'engineWarning'], n['statuses'])

    o, n = old['crash'], new['crash']
    expect(o['exitCode'] != 0 and not o['crashRecords'] and o['grew'] == 0, f'562: the crash leaves nothing in app.log: {o}')
    for name, result in [('JIT', n)] + ([('NativeAOT', aot)] if aot else []):
        rows = result['crashRecords']
        expect(result['exitCode'] != 0 and len(rows) == 1, f'{name}: the process still ends, one crash record: {result}')
        if rows:
            expect(rows[0]['status'] == 'unhandledException' and
                   rows[0]['diagnostic'].startswith('System.InvalidOperationException: synthetic engine crash'),
                   f'{name}: the exception type and message are written: {rows[0]}')
        expect(not result['secretWritten'], f'{name}: key-like values redacted')
    return failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-aot', action='store_true', help='skip the NativeAOT crash probe (no native toolchain)')
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='melonx-engine-journal-') as temporary:
        work = Path(temporary).resolve()
        baseline = subprocess.check_output(['git', 'show', f'{BASELINE}:{JOURNAL}'], cwd=ROOT, text=True)
        old_probe = build(work / 'old', baseline, False)
        new_probe = build(work / 'new', (ROOT / JOURNAL).read_text(), False)
        old = dict(repeat=repeat(work / 'old', old_probe), crash=crash(work / 'old', old_probe))
        new = dict(repeat=repeat(work / 'new', new_probe), crash=crash(work / 'new', new_probe))
        aot = None
        if not options.no_aot:
            aot_probe = build(work / 'aot', (ROOT / JOURNAL).read_text(), True)
            aot = crash(work / 'aot', aot_probe)
    failures = check(old, new, aot)
    summary = dict(result='failed' if failures else 'passed', failures=failures, nativeAot=aot is not None,
                   physicalDeviceTested=False,
                   old=dict(textureLines=len(old['repeat']['texture']), concurrentLines=len(old['repeat']['concurrent']),
                            crashRecords=len(old['crash']['crashRecords'])),
                   new=dict(textureLines=len(new['repeat']['texture']), concurrentLines=len(new['repeat']['concurrent']),
                            crash=new['crash']['crashRecords'][:1], aotCrash=(aot or {}).get('crashRecords', [])[:1]),
                   inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                           for p in (JOURNAL, RUNTIME, 'test/melonx_engine_journal_test.py')})
    out = ROOT / 'dist/melonx/engine-journal-checks.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + '\n')
    if failures:
        print('\n'.join(failures))
        raise SystemExit(1)
    print(f"PASS engine journal: 1001 repeated texts -> {len(new['repeat']['texture'])} lines (562: 1001); "
          f"8000 concurrent -> {len(new['repeat']['concurrent'])} (562: 8000); unhandled exception written past the "
          f"ceiling ({'JIT and NativeAOT' if aot else 'JIT'}; 562: nothing).")
