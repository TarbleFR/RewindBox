"""Copy readback data only when a virtual buffer actually contributes bytes.

Keep ownership of renderer data in the existing FlushImpl using scope,
including the synchronous guest-memory write. GetRanges/ConsumeModifiedRegion
are observed in precisely the same order: there is no racy preliminary dirty
check. The private fallback captures a copy of the non-owning PinnedSpan struct
and allocates its mutable snapshot at the first actual callback, before any
buffer copy. A clean dependency therefore returns the original pinned span.
For an unowned lease valid only until the next backend call, that first copy
precedes the call which could invalidate it. One local callback is reused for
the synchronous dependency queries of each invocation; no mutable callback
state is shared across invocations, threads or reentrant calls.

The callback's GPU copy now uses its clamped modified size, as the GPU-only
overload already does. Copying the whole outer readback size from a sub-range
offset could overwrite unrelated bytes or exceed the source/destination buffer.
No renderer data lease is disposed in the helper; FlushImpl remains its owner.
"""
import hashlib
from adapt_session import once


RELATIVE = 'src/Ryujinx.Graphics.Gpu/Memory/Buffer.cs'
BASELINE = '2e6173d5785636cadb9ab8ad4c5fc1631a6afff809cd0ac30b2bfcc384772320'
CONSUMERS = {
    'src/Ryujinx.Graphics.Gpu/Memory/MultiRangeBuffer.cs': 'ebb48b7a07c3b370590ab982e43024d1bd124972d5635cf39ce50033370370a8',
    'src/Ryujinx.Graphics.Gpu/Memory/BufferModifiedRangeList.cs': '94129cf9cdcb552e5e614f4aaf75914f1cbd7e222448e9474025ace69ea36580',
}


def method(text, signature):
    assert text.count(signature) == 1, signature
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def share_callback(text, arguments):
    """Retain the exact sorted enumeration and synchronous consume calls."""
    loop = '            foreach (MultiRangeBuffer virtualBuffer in _virtualDependencies.OrderBy(x => x.ModificationSequenceNumber))\n'
    call = f'''                virtualBuffer.ConsumeModifiedRegion({arguments}, (mAddress, mSize) =>
                {{
'''
    ending = '''                });
            }
'''
    assert text.count(loop) == text.count(call) == text.count(ending) == 1
    start = text.index(loop)
    body_start = text.index(call, start) + len(call)
    body_end = text.index(ending, body_start)
    body = '\n'.join(line[4:] if line else '' for line in text[body_start:body_end].splitlines())
    body = body.replace('virtualBuffer.', 'currentVirtualBuffer.')
    return text[:start] + '''            MultiRangeBuffer currentVirtualBuffer = null;
            // The consumer invokes this action synchronously and never retains
            // it. Each invocation owns its current dependency and callback.
            Action<ulong, ulong> copyRange = (mAddress, mSize) =>
            {
''' + body + '''
            };

''' + loop + '''            {
                currentVirtualBuffer = virtualBuffer;
''' + f'''                virtualBuffer.ConsumeModifiedRegion({arguments}, copyRange);
''' + '''            }
''' + text[body_end + len(ending):]


def apply(source):
    path = source / RELATIVE
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE, str(path)
    # A callback may be shared only while both complete consumers retain their
    # reviewed synchronous contract. Fail before any mutation if they drift.
    for relative, digest in CONSUMERS.items():
        assert hashlib.sha256((source / relative).read_bytes()).hexdigest() == digest, relative
    once(path, 'CopyFromDependantVirtualBuffers(data.Get(), address, size)',
         'CopyFromDependantVirtualBuffers(data, address, size)')
    old = method(path.read_text(), '        private ReadOnlySpan<byte> CopyFromDependantVirtualBuffers(ReadOnlySpan<byte> dataSpan, ulong address, ulong size)')
    start = old.index('                    byte[] storage = dataSpan.ToArray();')
    end = old.index('                    dataSpan = storage;')
    inner = '\n'.join(line[8:] if line else '' for line in old[start:end].splitlines()).rstrip()
    assert inner.count('byte[] storage = dataSpan.ToArray();') == 1
    inner = inner.replace('byte[] storage = dataSpan.ToArray();', 'byte[] storage = null;')
    callback = '''                virtualBuffer.ConsumeModifiedRegion(address, size, (mAddress, mSize) =>
                {
'''
    assert inner.count(callback) == 1
    inner = inner.replace(callback, callback + '''                    // Snapshot before a renderer call can invalidate borrowed
                    // readback data. Without a callback no snapshot is needed.
                    storage ??= data.Get().ToArray();

''')
    oversized = '_context.Renderer.Pipeline.CopyBuffer(virtualBuffer.Handle, Handle, virtualOffset, physicalOffset, (int)size);'
    assert inner.count(oversized) == 1
    inner = inner.replace(oversized, oversized.replace('(int)size', '(int)mSize'))
    new = '''        private ReadOnlySpan<byte> CopyFromDependantVirtualBuffers(PinnedSpan<byte> data, ulong address, ulong size)
        {
            _virtualDependenciesLock.EnterReadLock();

            try
            {
                if (_virtualDependencies != null)
                {
                    return CopyFromDependantVirtualBuffersImpl(data, address, size);
                }

                return data.Get();
            }
            finally
            {
                _virtualDependenciesLock.ExitReadLock();
            }
        }

        // Keep callback captures out of the no-dependency path. The PinnedSpan
        // is borrowed; the using scope in FlushImpl owns and disposes its lease.
        [MethodImpl(MethodImplOptions.NoInlining)]
        private ReadOnlySpan<byte> CopyFromDependantVirtualBuffersImpl(PinnedSpan<byte> data, ulong address, ulong size)
        {
''' + inner + '''

            return storage != null ? storage : data.Get();
        }'''
    once(path, old, new)
    for signature, arguments in (
        ('        private void CopyFromDependantVirtualBuffersImpl()', 'this'),
        ('        private ReadOnlySpan<byte> CopyFromDependantVirtualBuffersImpl(PinnedSpan<byte> data, ulong address, ulong size)', 'address, size'),
    ):
        old = method(path.read_text(), signature)
        once(path, old, share_callback(old, arguments))
    once(path, '<param name="dataSpan">Span where the unmodified data will be taken from for the output</param>',
         '<param name="data">Borrowed pinned data providing the unmodified bytes for the output</param>')
    once(path, '<returns>A span with <paramref name="dataSpan"/>, and the data for all modified ranges if any</returns>',
         '<returns>The borrowed data, or an owned snapshot with modified ranges overlaid when needed</returns>')
    return [path]
