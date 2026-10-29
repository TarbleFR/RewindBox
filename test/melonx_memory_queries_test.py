#!/usr/bin/env python3
"""Compare production contiguous-range query methods over mapped/unmapped page tables.

The production method body is compiled twice. Only its page-table boundary is a
double, which counts lookups. This checks exact results, not iPhone frame rate.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_memory_queries import apply

SOURCE = Path(sys.argv[1]).resolve()
PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == PIN['revision']
PATH = Path('src/Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs')
with tempfile.TemporaryDirectory(prefix='melonx-memory-query-') as directory:
    work = Path(directory)
    (work / PATH).parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / PATH, work / PATH)
    baseline = (work / PATH).read_text(encoding='utf-8-sig')
    apply(work)
    candidate = (work / PATH).read_text()
    start = '        private bool IsContiguous(ulong va, int size)'
    def method(text):
        offset = text.index(start)
        end = text.index('\n        /// <summary>', offset)
        return text[offset:end].replace('private bool IsContiguous', 'public bool IsContiguous')
    def wrapper(name, body):
        return f'''class {name}
{{
    const ulong PageSize = 4096, PageMask = 4095, PteUnmapped = ulong.MaxValue;
    public ulong[] Table = new ulong[512];
    public int Reads;
    bool ValidateAddress(ulong va) => va < 512UL * PageSize;
    ulong GetPte(ulong va) {{ Reads++; return va < 512UL * PageSize ? Table[va / PageSize] : PteUnmapped; }}
{body}
}}
'''
    (work / 'Program.cs').write_text('''using System;
using System.Text.Json;
''' + wrapper('Control', method(baseline)) + wrapper('Candidate', method(candidate)) + '''
class Program
{
    static void Main()
    {
        var a = new Control();
        var b = new Candidate();
        var random = new Random(1701);
        int checks = 0;
        for (int round = 0; round < 1000; round++)
        {
            for (int page = 0; page < a.Table.Length; page++)
            {
                ulong value = (round % 5) switch
                {
                    0 => 0x1234000000000000UL + (ulong)page * 4096,
                    1 => ulong.MaxValue,
                    2 => (ulong)random.Next(32) * 4096,
                    3 => page < 256 ? 0x100000UL + (ulong)page * 4096 : ulong.MaxValue,
                    _ => (ulong)(page / 4) * 65536 + (ulong)(page % 4) * 4096,
                };
                a.Table[page] = b.Table[page] = value;
            }
            for (int query = 0; query < 100; query++)
            {
                ulong va = (ulong)random.Next(512 * 4096 + 8192);
                int size = random.Next(1024 * 1024);
                bool control = a.IsContiguous(va, size), candidate = b.IsContiguous(va, size);
                if (control != candidate) throw new Exception($"range differs {round} {va:x} {size}");
                checks++;
            }
        }
        for (int page = 0; page < a.Table.Length; page++) a.Table[page] = b.Table[page] = (ulong)page * 4096;
        a.Reads = b.Reads = 0;
        if (!a.IsContiguous(0, 512 * 4096) || !b.IsContiguous(0, 512 * 4096)) throw new Exception("contiguous result");
        if (a.Reads != 1023 || b.Reads != 512) throw new Exception("lookup count");
        // Zero, partial-page, invalid-start and end-boundary semantics remain identical.
        foreach (ulong address in new ulong[] { 0, 1, 4095, 4096, 511 * 4096, 512 * 4096, ulong.MaxValue })
        foreach (int size in new[] { 0, 1, 4095, 4096, 4097 })
        {
            if (a.IsContiguous(address, size) != b.IsContiguous(address, size)) throw new Exception("boundary result");
            checks++;
        }
        Console.WriteLine(JsonSerializer.Serialize(new { passed = true, checks, contiguousPages = 512,
            controlReads = 1023, candidateReads = 512 }));
    }
}
''')
    (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<EnableDefaultCompileItems>false</EnableDefaultCompileItems>
</PropertyGroup><ItemGroup><Compile Include="Program.cs"/></ItemGroup></Project>''')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'latestPatch'}}))
    subprocess.run(['dotnet', 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'],
                   cwd=work, check=True, timeout=120)
    subprocess.run(['dotnet', 'bin/Release/net10.0/Probe.dll'], cwd=work, check=True, timeout=60)
