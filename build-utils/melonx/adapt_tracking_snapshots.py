"""Keep private tracking-handle snapshots without allocating for every flush.

RegionHandle must freeze the current handle list before releasing TrackingLock
for a pre-action. The outer VirtualRegion owns that snapshot until signalling
finishes, including nested accesses and exceptional exits. A stack-only owner
holds a single handle directly, rents at most 4096 references for larger lists,
and clears the rental in finally. Larger snapshots remain private allocations.
The snapshot is still taken lazily at the exact original unlock boundary;
precise callbacks, dirty events, exemptions and permission updates are unchanged.
"""
from adapt_session import once


SNAPSHOT = '''using System;
using System.Buffers;
using System.Collections.Generic;

namespace Ryujinx.Memory.Tracking
{
    // One signalling invocation owns this value. Never share its snapshot with
    // another invocation: pre-actions release TrackingLock and can re-enter.
    internal ref struct RegionHandleSnapshot
    {
        private const int MaxPooledHandles = 4096;
        private readonly List<RegionHandle> _list;
        private RegionHandle[] _snapshot;
        private RegionHandle _single;
        private int _count;

        public RegionHandleSnapshot(List<RegionHandle> list)
        {
            _list = list;
            _snapshot = null;
            _single = null;
            _count = -1;
        }

        public readonly int Count => _count < 0 ? _list.Count : _count;

        public readonly RegionHandle this[int index] => _count < 0
            ? _list[index]
            : _snapshot != null
                ? _snapshot[index]
                : index == 0 && _count == 1 ? _single : throw new ArgumentOutOfRangeException(nameof(index));

        public void Snapshot()
        {
            if (_count >= 0)
            {
                return;
            }

            int count = _list.Count;

            if (count == 1)
            {
                _single = _list[0];
                _count = 1;
            }
            else if (count == 0)
            {
                _count = 0;
            }
            else
            {
                _snapshot = count <= MaxPooledHandles
                    ? ArrayPool<RegionHandle>.Shared.Rent(count)
                    : new RegionHandle[count];
                _count = count;
                _list.CopyTo(_snapshot, 0);
            }
        }

        public void Dispose()
        {
            if (_snapshot != null && _count <= MaxPooledHandles)
            {
                ArrayPool<RegionHandle>.Shared.Return(_snapshot, clearArray: true);
            }

            _snapshot = null;
            _single = null;
            _count = 0;
        }
    }
}
'''


def apply(source):
    directory = source / 'src/Ryujinx.Memory/Tracking'
    handle = directory / 'RegionHandle.cs'
    region = directory / 'VirtualRegion.cs'
    owner = directory / 'RegionHandleSnapshot.cs'
    assert not owner.exists(), owner

    once(handle, 'using System.Linq;\n', '')
    for name, result in [('Signal', 'void'), ('SignalPrecise', 'bool')]:
        once(handle,
             f'internal {result} {name}(ulong address, ulong size, bool write, ref IList<RegionHandle> handleIterable)',
             f'internal {result} {name}(ulong address, ulong size, bool write, ref RegionHandleSnapshot handleIterable)')
    once(handle, '''                if (handleIterable is List<RegionHandle>)
                {
                    handleIterable = handleIterable.ToArray();
                }
''', '''                handleIterable.Snapshot();
''')

    for name in ['Signal', 'SignalPrecise']:
        text = region.read_text(encoding='utf-8-sig')
        start = text.index(f'        public override void {name}(')
        end = text.index('\n        ///', start)
        old = text[start:end]
        declaration = '            IList<RegionHandle> handles = Handles;\n'
        assert old.count(declaration) == 1, (region, name)
        body = old[old.index(declaration) + len(declaration):]
        assert body.endswith('        }\n'), (region, name)
        body = body[:-len('        }\n')].strip('\n')
        body = '\n'.join('    ' + line if line else '' for line in body.splitlines())
        replacement = old[:old.index(declaration)] + '''            RegionHandleSnapshot handles = new(Handles);

            try
            {
''' + body + '''
            }
            finally
            {
                handles.Dispose();
            }
        }
'''
        once(region, old, replacement)

    owner.write_text(SNAPSHOT, encoding='utf-8')
    return [handle, region, owner]
