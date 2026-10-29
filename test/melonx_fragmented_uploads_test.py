#!/usr/bin/env python3
"""Execute production full/partial texture reads with scoped fragmented snapshots.

Usage: python3 test/melonx_fragmented_uploads_test.py <pinned MeloNX checkout>
Only CPU guest memory and conversion/native upload endpoints are doubles. The
production read loop, snapshot lifetime and both upload-consumer methods compile.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == PIN['revision']
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_gpu_allocations import adapt_owner as established_owner
from adapt_upload_lifetime import apply as upload_lifetime
from adapt_fragmented_uploads import apply

GPU = Path('src/Ryujinx.Graphics.Gpu')
OWNER = Path('src/Ryujinx.Common/Memory/MemoryOwner.cs')
PHYSICAL = GPU / 'Memory/PhysicalMemory.cs'
TEXTURE = GPU / 'Image/Texture.cs'
GROUP = GPU / 'Image/TextureGroup.cs'
REGION = GPU / 'Memory/ReadOnlyRegion.cs'
RANGES = [Path('src/Ryujinx.Memory/Range/MemoryRange.cs'), Path('src/Ryujinx.Memory/Range/MultiRange.cs')]
HARNESS = ROOT / 'test/melonx_fragmented_uploads'

def method(text, signature):
    start = text.index(signature)
    end = text.index('\n        /// <summary>', start)
    return text[start:end]

reports = []
with tempfile.TemporaryDirectory(prefix='melonx-fragmented-') as directory:
    for mode in ['control', 'fixed']:
        work = Path(directory) / mode
        for path in [OWNER, PHYSICAL, TEXTURE, GROUP, *RANGES]:
            (work / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, work / path)
        established_owner(work)
        upload_lifetime(work)
        baseline_physical = (work / PHYSICAL).read_text(encoding='utf-8-sig')
        apply(work)
        text = (work / PHYSICAL).read_text()
        read = method(baseline_physical, '        public ReadOnlySpan<byte> GetSpan(MultiRange range, bool tracked = false)')
        lease = method(text, '        internal ReadOnlyRegion GetReadOnlyRegion(MultiRange range, bool tracked = false)')
        if mode == 'control':
            lease = '''        internal ReadOnlyRegion GetReadOnlyRegion(MultiRange range, bool tracked = false)
        { return new ReadOnlyRegion(GetSpan(range, tracked)); }
'''
        else:
            needle = 'MemoryOwner<byte>.Rent('
            assert lease.count(needle) == 1
            lease = lease.replace(needle, 'Tracking.Rent(')
            assert lease.count('owner.Dispose();') == 1
            lease = lease.replace('owner.Dispose();', 'Tracking.Dispose(owner);')
        (work / 'Physical.cs').write_text('''using System; using Ryujinx.Common.Memory; using Ryujinx.Memory.Range;
namespace Ryujinx.Graphics.Gpu.Memory {
static class MemoryManager { public const ulong PteUnmapped = ulong.MaxValue; }
sealed class PhysicalMemory(FakeCpuMemory memory) {
readonly FakeCpuMemory _cpuMemory = memory;
''' + read + lease + '}}\n')
        text = (work / REGION).read_text()
        text = text.replace('public void Dispose() => _owner?.Dispose();', 'public void Dispose() => Tracking.Dispose(_owner);')
        (work / REGION).write_text(text)
        texture = method((work / TEXTURE).read_text(), '        public void SynchronizeFull()')
        group = method((work / GROUP).read_text(), '        private void SynchronizePartial(int baseHandle, int regionCount)')
        (work / 'Consumers.cs').write_text('''using System; using Ryujinx.Graphics.Gpu.Memory;
namespace TestImage { sealed partial class Texture {
''' + texture + '} sealed partial class TextureGroup {\n' + group + '}}\n')
        for name in ['Program.cs', 'Boundary.cs']:
            shutil.copyfile(HARNESS / name, work / name)
        items = [OWNER, REGION, *RANGES, Path('Program.cs'), Path('Boundary.cs'), Path('Consumers.cs'), Path('Physical.cs')]
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>enable</Nullable>
<EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup><ItemGroup>
''' + ''.join(f'<Compile Include="{path}"/>\n' for path in items) + '</ItemGroup></Project>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'latestPatch'}}))
        subprocess.run(['dotnet', 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'],
                       cwd=work, check=True, timeout=120)
        run = subprocess.run(['dotnet', 'bin/Release/net10.0/Probe.dll', mode], cwd=work,
                             capture_output=True, text=True, timeout=60)
        if run.returncode:
            print(run.stdout, run.stderr)
            run.check_returncode()
        reports.append(json.loads(run.stdout.strip().splitlines()[-1]))
    def hashes(base, paths):
        return {str(path): hashlib.sha256((base / path).read_bytes()).hexdigest() for path in paths}
    evidence = {'result': 'passed', 'reports': reports, 'physicalDeviceTested': False,
                'upstreamRevision': PIN['revision'],
                'inputs': hashes(ROOT, [Path('build-utils/melonx/adapt_gpu_allocations.py'),
                    Path('build-utils/melonx/adapt_upload_lifetime.py'), Path('build-utils/melonx/adapt_fragmented_uploads.py'),
                    Path('build-utils/melonx/adapt_session.py'), Path('build-utils/melonx/source.json'),
                    Path('test/melonx_fragmented_uploads_test.py'),
                    *[path.relative_to(ROOT) for path in sorted(HARNESS.glob('*.cs'))]]),
                'upstreamInputs': hashes(SOURCE, [OWNER, PHYSICAL, TEXTURE, GROUP, *RANGES])}
    output = ROOT / 'dist/melonx/fragmented-upload-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
    print(json.dumps(evidence, sort_keys=True))
