#!/usr/bin/env python3
"""Manual .NET 10 regression probe for the prepared Vulkan sources and the session coordinator."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'test'), str(ROOT / 'build-utils/melonx')]
from adapt_buffer_mirror_windows import BASELINE, GPU
from adapt_descriptor_pool_lifetime import MANAGER
from adapt_descriptor_updates import method
from melonx_adapter_control import control_source

SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
HOLD = []
BEFORE, bound = control_source(SOURCE, 'adapt_buffer_mirror_windows', HOLD)
assert bound
POOL_BEFORE, pool_bound = control_source(SOURCE, 'adapt_descriptor_pool_lifetime', HOLD)
assert pool_bound
COORDINATOR = 'src/Ryujinx.Library/EmbeddedSessionCoordinator.cs'
FIXTURE = ROOT / 'test/melonx_buffer_mirror_windows/Probe.cs'
HEADER = 'using System;\nusing System.Collections.Generic;\nusing Ryujinx.Common.Memory;\n'


def block(text, first, last):
    start = text.index(first)
    return text[start:text.index(last, start)]


def emit(tree, name):
    holder = (tree / GPU / 'BufferHolder.cs').read_text()
    updater = (tree / GPU / 'DescriptorSetUpdater.cs').read_text()
    bitmap = (tree / GPU / 'BitMapStruct.cs').read_text().replace('namespace Ryujinx.Graphics.Vulkan', 'namespace ' + name)
    ranges = (SOURCE / GPU / 'BufferMirrorRangeList.cs').read_text().replace('namespace Ryujinx.Graphics.Vulkan', 'namespace ' + name)
    # Use the production write and fill branches, replacing only the staging destination and native handles.
    write = holder.split('if (allowMirror && !_waitable.IsBufferRangeInUse(offset, dataSize, true))', 1)[1]
    write = block(write[write.index('{') + 1:], write[write.index('{') + 1:].lstrip()[:12], '                // Remove any overlapping mirrors.')
    extra = ''
    if name == 'After':
        extra = method(holder, '        private Span<byte> PendingWriteSpan') + '\n' + method(holder, '        private void FillMirror')
        fill = 'FillMirror(baseData, offset, result);'
        layout = method(updater, '        internal static DirtyFlags BufferViewSets(')
        assert 'BufferViewDirtyFlags = DescriptorSetUpdater.BufferViewSets(BindingSegments);' in (tree / GPU / 'ShaderCollection.cs').read_text()
        assert '_dirty |= program.BufferViewDirtyFlags;' in updater
        classify = 'return (int)BufferViewSets(segments);'
    else:
        layout = method(updater, '        private static DirtyFlags BufferViewSets(')
        classify = 'return (int)BufferViewSets(new ShaderCollection { BindingSegments = segments });'
        fill = 'var modData = _pendingData.AsSpan(offset, result.Length); _pendingDataRanges.FillData(baseData, modData, offset, result);'
    fallback = block(holder.split('// Tell the graphics device to rebind', 1)[1], '            if (_pendingData != null)', '            if (cbs != null')
    sources = {'Map': bitmap, 'Ranges': ranges}
    body = '''
    internal enum ResourceType { None, BufferTexture, BufferImage }
    internal struct ResourceBindingSegment { public ResourceType Type; }
    internal class ShaderCollection { public ResourceBindingSegment[][] BindingSegments; }
    internal static class PipelineBase { public const int TextureSetIndex = 2, ImageSetIndex = 3; }
    // The encoding policy of PipelineBase.cs: the final write branch reads it since Core 771 (adapt_hogwarts_frame_budget,
    // a later adapter in BufferHolder.cs: under the policy a large buffer's window grows by doubling instead of to the
    // whole buffer). Off, as for every title but the one the launch sets it for, unless the probe sets it.
    internal static class EncodingPolicy { public static bool IncrementalArrayDescriptors; }
    internal class DisposableBuffer {}
    internal class Auto<T> {}
    internal struct DescriptorBufferInfo { public ulong Range; }
    internal sealed class Mirror : IProbeMirror
    {
        readonly int Size;
        private const int MirrorWindowBytes = 16 * 1024;
        byte[] _pendingData;
        int _pendingDataOffset;
        BufferMirrorRangeList _pendingDataRanges;
        struct StagingBufferReserved {}
        Dictionary<ulong, StagingBufferReserved> _mirrors;
        readonly Device _gd = new();
        readonly object _buffer = new();
        class Device { public Device PipelineInternal => this; public void Rebind(object b, int o, int s) {} }
        static class MirrorCopyJournal { public static void Added(int n, int previous = 0) {} }
        public Mirror(int size) { Size = size; }
        public int Held => _pendingData?.Length ?? 0;
        public void Write(int offset, ReadOnlySpan<byte> data) { int dataSize = data.Length; WRITE }
        public void Fill(int offset, Span<byte> baseData, Span<byte> result)
        {
            if (!_pendingDataRanges.OverlapsWith(offset, result.Length)) { baseData.CopyTo(result); return; }
            FILL
        }
        public void Remove(int offset, int size) { _pendingDataRanges.Remove(offset, size); }
        public void Reserve(int offset, int size) { _mirrors[ToMirrorKey(offset, size)] = default; }
        public bool Has(int offset, int size) => _mirrors.ContainsKey(ToMirrorKey(offset, size));
        public void Fallback(int offset, int dataSize) { FALLBACK }
        KEYS
        EXTRA
    }
    internal sealed class Descriptors : IProbeDescriptors
    {
        readonly object _program = new();
        struct BufferRef { public Auto<DisposableBuffer> Buffer; public int Offset; }
        [Flags] internal enum DirtyFlags { None = 0, Uniform = 1, Storage = 2, Texture = 4, Image = 8 }
        DirtyFlags _dirty;
        void SignalDirty(DirtyFlags bit) => _dirty |= bit;
        readonly Auto<DisposableBuffer> shared = new(), other = new();
        BitMapStruct<Array2<long>> _uniformMirrored, _uniformSet, _storageMirrored, _storageSet;
        readonly BufferRef[] _uniformBufferRefs = new BufferRef[128], _storageBufferRefs = new BufferRef[128];
        readonly DescriptorBufferInfo[] _uniformBuffers = new DescriptorBufferInfo[128], _storageBuffers = new DescriptorBufferInfo[128];
        readonly int[] _uniformSetPd = new int[128];
        public Descriptors() {
            for (int i=0; i<128; i++) {
                _uniformBufferRefs[i] = new BufferRef { Buffer = i % 3 == 0 ? other : shared, Offset = 8*i };
                _storageBufferRefs[i] = new BufferRef { Buffer = i % 5 == 0 ? other : shared, Offset = 8*i + 4 };
                _uniformBuffers[i].Range = 20; _storageBuffers[i].Range = 12;
                _uniformSetPd[i] = 19; _uniformSet.Set(i); _storageSet.Set(i);
                if (i % 2 == 0) _uniformMirrored.Set(i);
                if (i % 3 == 0) _storageMirrored.Set(i);
            }
        }
        public void Call(int start, int size, bool first) => Rebind(first ? shared : other, start, size);
        public int State(int i) => (int)_dirty * 10000 + (_uniformSet.IsSet(i) ? 1000 : 0) + (_storageSet.IsSet(i) ? 100 : 0) + _uniformSetPd[i];
        public static int Classify(int texture, int image, int count = 4) {
            var segments = new ResourceBindingSegment[count][];
            for (int i = 0; i < count; i++) {
                var type = (ResourceType)(i == 2 ? texture : i == 3 ? image : 0);
                segments[i] = new ResourceBindingSegment[] { default, new ResourceBindingSegment { Type = type } };
            }
            CLASSIFY
        }
        LAYOUT
        REBIND
    }
'''
    body = body.replace('WRITE', write).replace('FILL', fill).replace('FALLBACK', fallback).replace('EXTRA', extra)
    body = body.replace('KEYS', '\n'.join(method(holder, s) for s in ['        private static ulong ToMirrorKey', '        private static (int offset, int size) FromMirrorKey','        public bool RemoveOverlappingMirrors']))
    body = body.replace('LAYOUT', layout).replace('CLASSIFY', classify)
    body = body.replace('REBIND','\n'.join(method(updater,s) for s in ['        private static bool BindingOverlaps', '        internal void Rebind']))
    sources['Methods'] = HEADER + 'namespace ' + name + ' {\n' + body + '\n}'
    return sources


with tempfile.TemporaryDirectory(prefix='melonx-buffer-windows-') as directory:
    work = Path(directory)
    for tree, name in ((BEFORE, 'Before'), (SOURCE, 'After')):
        for label, source in emit(tree, name).items():
            (work / (name + label + '.cs')).write_text(source)
    for filename in (COORDINATOR, 'src/Ryujinx.Common/Memory/IArray.cs', 'src/Ryujinx.Common/Memory/StructArrayHelpers.cs'):
        shutil.copyfile(SOURCE / filename, work / Path(filename).name)
    pool_fixture = FIXTURE.with_name('DescriptorPools.cs').read_text()
    shared_api, boundary = pool_fixture.split('namespace AfterPool', 1)
    (work / 'PoolDriver.cs').write_text(shared_api)
    for tree, name in ((POOL_BEFORE, 'BeforePool'), (SOURCE, 'AfterPool')):
        (work / (name + '.cs')).write_text((tree / MANAGER).read_text().replace('namespace Ryujinx.Graphics.Vulkan', 'namespace ' + name))
        (work / (name + 'Boundary.cs')).write_text('using Silk.NET.Vulkan;\nnamespace ' + name + boundary)
    shutil.copyfile(FIXTURE, work / 'Probe.cs')
    (work / 'probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType><ImplicitUsings>enable</ImplicitUsings><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup></Project>')
    dotnet = os.environ.get('DOTNET', 'dotnet')
    result = subprocess.run([dotnet, 'run', '-c', 'Release', '--project', str(work / 'probe.csproj')], text=True, stdout=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stdout)
    stats = json.loads(result.stdout.strip().splitlines()[-1])
receipt = dict(result='passed', finalPreparationBound=True, physicalDeviceTested=False,
               sourceKind='finalPreparationWithReversedControl',
               measured=stats, postimages={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in [*BASELINE, MANAGER, COORDINATOR]})
output = ROOT / 'dist/melonx/buffer-mirror-windows-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(stats))
