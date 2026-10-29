"""Reuse exact single-region memory tracking lookups under the tracking lock.

Repeated protected CPU/GPU accesses used to search the region tree, enter its
reader lock, rent a reference array and copy one entry on every event. Keep one
live region for host accesses and one for guest accesses. Only a nonempty range
fully contained in that region can use the cached lookup; every signal, dirty
flag, precise action and protection update still executes.

Creating/splitting regions and removing a region invalidate the corresponding
cache under the existing tracking lock. A miss containing one region can carry
the reference directly after releasing the reader lock. Multiple regions still
use a private snapshot, because callbacks can mutate the hierarchy or release
the tracking lock. Return that snapshot cleared, including when a callback
throws. No guest code, mappings, tracking policy or access ordering is changed.
"""
from adapt_session import once


OLD_LOOKUP = '''                NonOverlappingRangeList<VirtualRegion> regions = guest ? _guestVirtualRegions : _virtualRegions;
                
                // We use the non-span method here because keeping the lock will cause a deadlock.
                regions.Lock.EnterReadLock();
                VirtualRegion[] overlaps = regions.FindOverlapsAsArray(address, size, out int length);
                regions.Lock.ExitReadLock();
'''

NEW_LOOKUP = '''                NonOverlappingRangeList<VirtualRegion> regions = guest ? _guestVirtualRegions : _virtualRegions;
                VirtualRegion single = guest ? _lastGuestVirtualRegion : _lastVirtualRegion;
                VirtualRegion[] overlaps = null;
                int length;

                // Cache only topology, never permissions or the result of signalling.
                // The subtraction also excludes wrapped and empty access ranges.
                if (single != null && size != 0 && address >= single.Address &&
                    address < single.EndAddress && size <= single.EndAddress - address)
                {
                    length = 1;
                }
                else
                {
                    regions.Lock.EnterReadLock();

                    try
                    {
                        ReadOnlySpan<VirtualRegion> found = regions.FindOverlapsAsSpan(address, size);
                        length = found.Length;

                        if (length == 1)
                        {
                            single = found[0];

                            if (guest)
                            {
                                _lastGuestVirtualRegion = single;
                            }
                            else
                            {
                                _lastVirtualRegion = single;
                            }
                        }
                        else if (length != 0)
                        {
                            // Callbacks can release TrackingLock or change the region list.
                            // No span into that list may survive into a callback.
                            overlaps = ArrayPool<VirtualRegion>.Shared.Rent(length);
                            found.CopyTo(overlaps);
                        }
                    }
                    finally
                    {
                        regions.Lock.ExitReadLock();
                    }
                }
'''


def apply(source):
    path = source / 'src/Ryujinx.Memory/Tracking/MemoryTracking.cs'
    once(path, '        private readonly NonOverlappingRangeList<VirtualRegion> _guestVirtualRegions;\n',
         '''        private readonly NonOverlappingRangeList<VirtualRegion> _guestVirtualRegions;

        // Accessed only while holding TrackingLock. Topology mutations invalidate these.
        private VirtualRegion _lastVirtualRegion;
        private VirtualRegion _lastGuestVirtualRegion;

        private void InvalidateRegionCache(bool guest)
        {
            if (guest)
            {
                _lastGuestVirtualRegion = null;
            }
            else
            {
                _lastVirtualRegion = null;
            }
        }
''')
    once(path, '''        internal List<VirtualRegion> GetVirtualRegionsForHandle(ulong va, ulong size, bool guest)
        {
''', '''        internal List<VirtualRegion> GetVirtualRegionsForHandle(ulong va, ulong size, bool guest)
        {
            InvalidateRegionCache(guest);
''')
    once(path, '''        internal void RemoveVirtual(VirtualRegion region)
        {
''', '''        internal void RemoveVirtual(VirtualRegion region)
        {
            InvalidateRegionCache(region.Guest);
''')
    once(path, OLD_LOOKUP, NEW_LOOKUP)

    text = path.read_text()
    start = text.index('                if (length == 0 && !precise)')
    end_marker = '''            }

            if (shouldThrow)'''
    end = text.index(end_marker, start)
    body = text[start:end]
    old_return = '''                    if (length != 0)
                    {
                        ArrayPool<VirtualRegion>.Shared.Return(overlaps);
                    }
'''
    assert body.count(old_return) == 1, path
    assert body.count('VirtualRegion region = overlaps[i];') == 1, path
    body = body.replace(old_return, '').replace('VirtualRegion region = overlaps[i];',
                                               'VirtualRegion region = length == 1 ? single : overlaps[i];')
    body = '\n'.join('    ' + line if line else '' for line in body.rstrip('\n').splitlines())
    replacement = '''                try
                {
''' + body + '''
                }
                finally
                {
                    if (overlaps != null)
                    {
                        ArrayPool<VirtualRegion>.Shared.Return(overlaps, clearArray: true);
                    }
                }
'''
    once(path, text[start:end], replacement)
    return [path]
