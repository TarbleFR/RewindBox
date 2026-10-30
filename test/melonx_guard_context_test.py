#!/usr/bin/env python3
"""Execute fatal guard context against exact production methods and explicit adapters."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_guard_context import apply

NAMES = ['src/Ryujinx.Cpu/LightningJit/NativeInterface.cs',
         'src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs']

with tempfile.TemporaryDirectory(prefix='melonx-guard-context-') as tmp:
    workspace = Path(tmp)
    source = workspace / 'source'
    for name in NAMES:
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, destination)
    before = {name: (source / name).read_text() for name in NAMES}
    changed = apply(source)
    assert len(changed) == 2
    after = {name: (source / name).read_text() for name in NAMES}
    # All mapping, guard conditions and return values remain byte-identical.
    assert after[NAMES[1]].replace('; {LightningJit.NativeInterface.DescribeLastGuestDispatch()}', '') == before[NAMES[1]]
    start = after[NAMES[0]].index('        internal static string DescribeLastGuestDispatch()')
    end = after[NAMES[0]].index('        public static void RegisterThread(', start)
    assert after[NAMES[0]][:start] + after[NAMES[0]][end:] == before[NAMES[0]]
    guard = after[NAMES[1]]
    begin = guard.index('        private ulong VirtualMemoryEvent(')
    end = guard.index('\n        private void Dispose(', begin)
    body = guard[begin:end]
    assert body.count('throw new InvalidMemoryRegionException(') == 1
    (workspace / 'GuardProbe.cs').write_text('''using System;
using System.Collections.Generic;
using Ryujinx.Memory;
using LightningJit = Ryujinx.Cpu.LightningJit;
class GuardProbe {
    private const int PageSize = 4096;
    private readonly ulong _hostPageSize = 16384;
    private readonly Block _nativePageTable = new();
    private class Block { public ulong Size = 0x40004000; public nint Pointer = (nint)0x100000000; }
    public readonly List<ulong> Commitments = new();
    private void EnsureCommitment(ulong va) => Commitments.Add(va);
    public ulong Run(ulong address, ulong size, bool write) => VirtualMemoryEvent(address, size, write);
''' + body + '\n}\n')
    shutil.copyfile(source / NAMES[0], workspace / 'NativeInterface.cs')
    shutil.copyfile(ROOT / 'test/melonx_guard_context/Program.cs', workspace / 'Program.cs')
    (workspace / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit></PropertyGroup><ItemGroup><Compile Remove="source/**/*.cs" /></ItemGroup></Project>''')
    (workspace / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
    result = subprocess.run(['dotnet', 'run', '--project', str(workspace), '-c', 'Release', '-v', 'q'],
                            capture_output=True, text=True, timeout=180)
    if result.returncode:
        print(result.stdout, result.stderr)
        result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    report.update(inputs={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [Path(__file__), ROOT / 'test/melonx_guard_context/Program.cs',
                                       ROOT / 'build-utils/melonx/adapt_guard_context.py']},
                  preimages={name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in NAMES},
                  postimages={name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in NAMES})
    output = ROOT / 'dist/melonx/guard-context-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
