"""Keep upstream allocator ownership until every guest allocation has returned."""
from adapt_session import once

def apply(source):
    path = source / 'src/Ryujinx.Memory/DonatedMemory.cs'
    once(path, '''        public static void Offer(nint baseAddress, ulong size)
        {
            lock (_lock)
            {
                Reset();''', '''        public static void Offer(nint baseAddress, ulong size) => TryOffer(baseAddress, size);

        public static bool TryOffer(nint baseAddress, ulong size)
        {
            lock (_lock)
            {
                if (_liveAllocations.Count != 0 || _base != nint.Zero) return false;
                if (baseAddress == nint.Zero || size < Granularity ||
                    ((ulong)baseAddress & (Granularity - 1)) != 0 ||
                    (size & (Granularity - 1)) != 0 ||
                    (ulong)baseAddress > ulong.MaxValue - size) return false;
                Reset();''')
    once(path, '''                    return;
                }

                _base = baseAddress;''', '''                    return false;
                }

                _base = baseAddress;''')
    once(path, '''                _freeRanges.Add(new FreeRange(0, _size, false));
            }
        }

        public static void Withdraw()
        {
            lock (_lock)
            {
                Reset();
            }
        }''', '''                _freeRanges.Add(new FreeRange(0, _size, false));
                return true;
            }
        }

        public static void Withdraw() => TryWithdraw();

        public static bool TryWithdraw()
        {
            lock (_lock)
            {
                if (_liveAllocations.Count != 0) return false;
                Reset();
                return true;
            }
        }

        public static void Snapshot(out ulong offered, out ulong used, out ulong allocations)
        {
            lock (_lock)
            {
                offered = _base != nint.Zero ? _size : 0;
                used = _usedBytes;
                allocations = (ulong)_liveAllocations.Count;
            }
        }''')
    return [path]
