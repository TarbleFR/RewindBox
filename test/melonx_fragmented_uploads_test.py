#!/usr/bin/env python3
"""Execute production full/partial texture reads with scoped fragmented snapshots.

Usage: python3 test/melonx_fragmented_uploads_test.py <pinned MeloNX checkout> [--slice-composition]
Only CPU guest memory and conversion/native upload endpoints are doubles. The
production read loop, snapshot lifetime and both upload-consumer methods compile.
The optional composition mode retains the fixed upload path in both variants
and changes only MultiRange.Slice. It does not replay the old unpooled variant.
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
assert sys.argv[2:] in ([], ['--slice-composition']), 'Unknown fixture mode'
SLICE_COMPOSITION = bool(sys.argv[2:])
PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == PIN['revision']
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_gpu_allocations import adapt_owner as established_owner
from adapt_upload_lifetime import apply as upload_lifetime
from adapt_fragmented_uploads import apply
from adapt_multirange_slice import apply as apply_slice

GPU = Path('src/Ryujinx.Graphics.Gpu')
OWNER = Path('src/Ryujinx.Common/Memory/MemoryOwner.cs')
PHYSICAL = GPU / 'Memory/PhysicalMemory.cs'
TEXTURE = GPU / 'Image/Texture.cs'
GROUP = GPU / 'Image/TextureGroup.cs'
REGION = GPU / 'Memory/ReadOnlyRegion.cs'
RANGES = [Path('src/Ryujinx.Memory/Range/MemoryRange.cs'), Path('src/Ryujinx.Memory/Range/MultiRange.cs')]
HARNESS = ROOT / 'test/melonx_fragmented_uploads'
SLICE_PATH = Path('src/Ryujinx.Memory/Range/MultiRange.cs')
FINAL_SLICE_SHA256 = 'c945e4d62500263742db07c2c8afbd0c783b1fcfe811179a232ec30ac09e826b'
PRISTINE_SLICE_SHA256 = '70c52a73bba5827126c9eb32fb8d66d8342e33b0fa73a90f96137f65ce29c767'

def method(text, signature):
    start = text.index(signature)
    end = text.index('\n        /// <summary>', start)
    return text[start:end]

reports = []
postimages, extraction, compiled, slice_inputs = {}, {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-fragmented-') as directory:
    for mode in (['baseline', 'candidate'] if SLICE_COMPOSITION else ['control', 'fixed']):
        work = Path(directory) / mode
        for path in [OWNER, PHYSICAL, TEXTURE, GROUP, *RANGES]:
            (work / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, work / path)
        established_owner(work)
        upload_lifetime(work)
        baseline_physical = (work / PHYSICAL).read_text(encoding='utf-8-sig')
        apply(work)
        if SLICE_COMPOSITION:
            assert hashlib.sha256((work / SLICE_PATH).read_bytes()).hexdigest() == PRISTINE_SLICE_SHA256
            if mode == 'candidate':
                apply_slice(work)
                postimages[str(SLICE_PATH)] = hashlib.sha256((work / SLICE_PATH).read_bytes()).hexdigest()
                assert postimages[str(SLICE_PATH)] == FINAL_SLICE_SHA256, 'Compile the exact final Slice'
            slice_inputs[mode] = hashlib.sha256((work / SLICE_PATH).read_bytes()).hexdigest()
        text = (work / PHYSICAL).read_text()
        read = method(baseline_physical, '        public ReadOnlySpan<byte> GetSpan(MultiRange range, bool tracked = false)')
        lease = method(text, '        internal ReadOnlyRegion GetReadOnlyRegion(MultiRange range, bool tracked = false)')
        production_lease = lease
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
        if SLICE_COMPOSITION:
            extraction[mode] = {name: hashlib.sha256(body.encode()).hexdigest() for name, body in
                [('physicalGetSpan', read), ('physicalGetReadOnlyRegion', production_lease),
                 ('textureSynchronizeFull', texture), ('groupSynchronizePartial', group)]}
        (work / 'Consumers.cs').write_text('''using System; using Ryujinx.Graphics.Gpu.Memory;
namespace TestImage { sealed partial class Texture {
''' + texture + '} sealed partial class TextureGroup {\n' + group + '}}\n')
        for name in ['Program.cs', 'Boundary.cs']:
            shutil.copyfile(HARNESS / name, work / name)
        items = [OWNER, REGION, *RANGES, Path('Program.cs'), Path('Boundary.cs'), Path('Consumers.cs'), Path('Physical.cs')]
        if SLICE_COMPOSITION:
            # Observe only doubled conversion boundaries. Production method bodies
            # remain exact; varying each physical fragment makes wrong slices visible.
            substitutions = {
                'Program.cs': [
                    ('(byte)(i * 17 + 3)', '(byte)(i * 17 + (i >> 19) * 31 + 3)'),
                    ('physicalDeviceTested = false }',
                     'physicalDeviceTested = false, payloadDigest = SliceCompositionProbe.Digest, '
                     'payloadCalls = SliceCompositionProbe.Calls, payloadBytes = SliceCompositionProbe.Bytes }'),
                ],
                'Boundary.cs': [
                    ('            Conversions++;',
                     '            Conversions++;\n            SliceCompositionProbe.Record(data, -1);'),
                    ('            if (FailConversion) throw new InvalidOperationException("partial conversion failure");',
                     '            if (FailConversion) throw new InvalidOperationException("partial conversion failure");\n'
                     '            SliceCompositionProbe.Record(data, level);'),
                ],
            }
            for name, changes in substitutions.items():
                path = work / name
                text = path.read_text()
                for before, after in changes:
                    assert text.count(before) == 1, before
                    text = text.replace(before, after)
                path.write_text(text)
            shutil.copyfile(ROOT / 'test/melonx_fragmented_uploads_slice/CompositionProbe.cs', work / 'CompositionProbe.cs')
            items.append(Path('CompositionProbe.cs'))
            compiled[mode] = {str(path): hashlib.sha256((work / path).read_bytes()).hexdigest() for path in items}
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>enable</Nullable>
<EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup><ItemGroup>
''' + ''.join(f'<Compile Include="{path}"/>\n' for path in items) + '</ItemGroup></Project>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'],
            'rollForward': 'disable' if SLICE_COMPOSITION else 'latestPatch'}}))
        subprocess.run(['dotnet', 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'],
                       cwd=work, check=True, timeout=120)
        run = subprocess.run(['dotnet', 'bin/Release/net10.0/Probe.dll', 'fixed' if SLICE_COMPOSITION else mode], cwd=work,
                             capture_output=True, text=True, timeout=60)
        if run.returncode:
            print(run.stdout, run.stderr)
            run.check_returncode()
        report = json.loads(run.stdout.strip().splitlines()[-1])
        if SLICE_COMPOSITION:
            report['sliceVariant'] = mode
        reports.append(report)
    if SLICE_COMPOSITION:
        before, after = reports
        for field in ('passed', 'checks', 'fragmentedUploads', 'rents', 'returns',
                      'payloadDigest', 'payloadCalls', 'payloadBytes'):
            assert before[field] == after[field], (field, before[field], after[field])
        assert before['payloadCalls'] > 0 and before['payloadBytes'] > 0
        assert after['allocatedBytes'] < before['allocatedBytes'], (before, after)
        assert extraction['baseline'] == extraction['candidate'], 'Only Slice may change in production consumers'
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
    if SLICE_COMPOSITION:
        evidence['inputs'].update(hashes(ROOT, [Path('build-utils/melonx/adapt_multirange_slice.py'),
            Path('test/melonx_fragmented_upload_slice_test.py'),
            Path('test/melonx_fragmented_uploads_slice/CompositionProbe.cs')]))
        evidence.update(finalSliceCompiledWithProductionConsumers=True, baselineRetainsHistoricalSlice=True,
                        productionConsumerBodiesUnchanged=True, postimages=postimages, extraction=extraction,
                        compiledSources=compiled, compiledMultiRangeSha256=slice_inputs,
                        conversionPayloadBoundaryObserved=True, historicalUnpooledVariantReplayed=False,
                        dotnet=PIN['dotnet'])
    output = ROOT / 'dist/melonx' / ('fragmented-upload-slice-checks.json' if SLICE_COMPOSITION else 'fragmented-upload-checks.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
    print(json.dumps(evidence, sort_keys=True))
