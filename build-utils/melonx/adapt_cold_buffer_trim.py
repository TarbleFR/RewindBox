"""While only the device is short of memory, the buffer cache gives back the buffers nothing used for a minute of play.

IPA 724, Hogwarts Legacy on an 8 GiB iPhone (pid 49375; private journals, not in the repository; aggregates only): the
device has 4 to 9 % of its memory available from the first scene on while this process keeps 1.3 GiB or more of headroom
to its own limit. GpuContext.TrimCaches then runs on every host report and every 10 s (24 times in 150 s). Its texture
part has released only what frees memory without a flush since adapt_device_short_trim; its buffer part is upstream's:
BufferCache.Trim evicts the least recently used quarter (Warning) or half (Critical) of what the cache holds, whatever
was used a moment ago. The cache held 85 to 127 MiB, all of it in use:
- render thread, 5 s windows (LogRenderWork): with a trim, 1 400 to 7 026 buffers created (64 to 460 ms) and, after a
  Critical one, 3 637 to 7 317 disposed (63 to 122 ms); without one, 0 to 870 created (0 to 54 ms), none disposed in
  the list;
- GPU thread (gpuWork.bufLoad): 0.8 to 11.6 MiB allocated per window with a trim, 4 to 6 KiB without;
- every 30 s report finds the cache at its size again (89, 122, 85, 106, 127 MiB): about 1 000 MiB "released" in the
  session, nothing given back to the device; each cycle frees and allocates again some 50 MiB of Metal buffers while
  the device has no memory to spare.
The first report after the pause did the same at the resume (2 565 buffers disposed, 805 created in the window of the
4.3 s gap).

Change (BufferCache.cs and one field in Buffer.cs, every title):
- every buffer records the cache's use epoch when the cache returns it (Touch, which every lookup calls) or adds it;
- the epoch counts seconds of play, on the cache's own clock (no other file is involved): the host's uptime is read
  once every 256 lookups (thousands of lookups a second in play, so a few milliseconds apart) and, of the seconds
  between two reads, only one counts; a host pause, a stall without a frame or a stretch in which nothing looks a
  buffer up therefore ages nothing;
- BufferCache.Trim keeps its targets and floor; when this process's headroom is 768 MiB or more (the threshold at or
  above which TrimCaches runs only because the device is short) it evicts, oldest first, only the buffers unused for
  ColdBufferAgeSeconds (60, the age of adapt_cold_texture_release) and stops at the first one used since; below that
  headroom, or when it is unknown, the eviction is upstream's, unchanged;
- a bounded engine journal record ("bufferCache coldTrim": what the pass released, what it left in use above the
  target, the cache size and the totals so far): the first pass, then at most one every 10 s of play while passes
  release something and one every 60 s otherwise; at most 160 records.
Limits, the capacity eviction (EnforceCapacity), the recreation of an evicted buffer (adapt_evicted_buffer_recreate),
the texture trims and GpuContext are unchanged (the cache reads nothing of GpuContext: an earlier adapter's control tree
builds with these two files as they are). A buffer released here is recreated from guest memory by its next
lookup, as after any eviction. The cache may hold more than before under a short device: what the game used within the
last minute instead of a part of it; the 30 s memory inventory (bufferCacheBytes) says how much.
Not measured on an iPhone. Fail closed on drift: both files must be the Core 729 preparation's.
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'
BUFFER = 'src/Ryujinx.Graphics.Gpu/Memory/Buffer.cs'
BASELINE = {
    CACHE: 'c5a8991bd2b3f35e5978224ebcfe008b81fc3ce64a23fff5e4f3c3a91fc277dd',
    BUFFER: '2c6ab94389b5ef10dad8bac6f89f24d1ab0f32786ccd56de50f6b3772e5fe43d',
}

FIELD_OLD = '''        /// <summary>
        /// Node used to track this buffer in the cache's least-recently-used list.
        /// </summary>
        public LinkedListNode<Buffer> CacheNode { get; set; }
'''
FIELD_NEW = FIELD_OLD + '''
        /// <summary>
        /// RewindBox (adapt_cold_buffer_trim): the buffer cache's use epoch (seconds of play) when it last returned or
        /// added this buffer.
        /// </summary>
        public int LastUseEpoch;
'''

ADD_OLD = '''            _buffers.Add(buffer);
            _cachedBufferBytes += buffer.Size;
            buffer.CacheNode = _lruBuffers.AddLast(buffer);
'''
ADD_NEW = '''            _buffers.Add(buffer);
            _cachedBufferBytes += buffer.Size;
            buffer.LastUseEpoch = UseEpoch(); // RewindBox (adapt_cold_buffer_trim)
            buffer.CacheNode = _lruBuffers.AddLast(buffer);
'''

TOUCH_OLD = '''        private void Touch(Buffer buffer)
        {
            LinkedListNode<Buffer> node = buffer.CacheNode;
'''
TOUCH_NEW = '''        private void Touch(Buffer buffer)
        {
            buffer.LastUseEpoch = UseEpoch(); // RewindBox (adapt_cold_buffer_trim)
            LinkedListNode<Buffer> node = buffer.CacheNode;
'''

TRIM_OLD = '''            ulong before = _cachedBufferBytes;

            EnforceCapacity(null, target);

            return before - _cachedBufferBytes;
        }
'''
# The block between the two markers is what the gate's fixture compiles as the candidate's new members.
MEMBERS_BEGIN = '        // RewindBox (adapt_cold_buffer_trim): begin\n'
MEMBERS_END = '        // RewindBox (adapt_cold_buffer_trim): end\n'
TRIM_NEW = '''            ulong before = _cachedBufferBytes;

            // RewindBox (adapt_cold_buffer_trim): with this headroom GpuContext.TrimCaches runs only because the device is
            // short; the buffers used within the last minute of play stay.
            if (HostMemoryBudget.AvailableBytes >= DeviceShortOnlyHeadroomBytes)
            {
                EvictCold(target);
            }
            else
            {
                EnforceCapacity(null, target);
            }

            return before - _cachedBufferBytes;
        }

        // RewindBox (adapt_cold_buffer_trim): the host's uptime; apart from the members below so that the gate's fixture
        // drives the clock.
        private static long HostMilliseconds() => Environment.TickCount64;

''' + MEMBERS_BEGIN + '''        // IPA 724, Hogwarts Legacy: the device stayed at 4-9 % of its memory available with 1.3 GiB or more of headroom
        // here; 24 trims in 150 s each evicted a quarter to a half of a 85-127 MiB cache in use, and the game used those
        // buffers again at once (1 400 to 7 026 buffers created per 5 s window with a trim, 0 to 870 without; the cache
        // back at its size at every 30 s report). While only the device is short a trim gives back, oldest first and down
        // to the same target, the buffers no lookup returned for ColdBufferAgeSeconds of play; the others stay.
        internal const int ColdBufferAgeSeconds = 60;
        private const ulong DeviceShortOnlyHeadroomBytes = 768 * MiB; // GpuContext.ComfortableHeadroomBytes
        private const int UseClockLookups = 256;
        private const int MaxColdTrimRecords = 160;
        private const int ColdTrimNewsIntervalSeconds = 10;
        private const int ColdTrimQuietIntervalSeconds = 60;

        private int _useClockLookups;
        private int _hostSecondSeen;
        private int _skippedSeconds;
        private int _coldTrimPasses;
        private int _coldTrimBuffers;
        private ulong _coldTrimBytes;
        private int _coldTrimRecords;
        private int _coldTrimRecordEpoch;
        private int _coldTrimRecordedBuffers;

        // Seconds of play, for the stamps. The host's uptime is read once every UseClockLookups lookups (thousands of
        // lookups a second in play: a few milliseconds apart); of the seconds between two reads only one counts, so a
        // host pause, a stall without a frame or a stretch without lookups ages no buffer. GPU thread only, as the list
        // this stamps.
        private int UseEpoch()
        {
            if ((++_useClockLookups & (UseClockLookups - 1)) == 0)
            {
                int host = (int)(HostMilliseconds() / 1000);
                int step = host - _hostSecondSeen;

                if (step != 0)
                {
                    if (step > 1)
                    {
                        _skippedSeconds += step - 1;
                    }

                    _hostSecondSeen = host;
                }
            }

            return PlaySeconds();
        }

        private int PlaySeconds()
        {
            return _hostSecondSeen - _skippedSeconds;
        }

        private void EvictCold(ulong target)
        {
            if (_evictionSuppressDepth != 0)
            {
                return;
            }

            int epoch = PlaySeconds();
            ulong before = _cachedBufferBytes;
            int evicted = 0;
            LinkedListNode<Buffer> node = _lruBuffers.First;

            while (_cachedBufferBytes > target && node != null)
            {
                LinkedListNode<Buffer> next = node.Next;
                Buffer buffer = node.Value;

                // The list is in use order: every buffer after this one was used later.
                if (epoch - buffer.LastUseEpoch < ColdBufferAgeSeconds)
                {
                    break;
                }

                if (buffer.CanEvict())
                {
                    _buffers.Remove(buffer);
                    RemoveBufferTracking(buffer);
                    buffer.Dispose();
                    evicted++;
                }

                node = next;
            }

            if (evicted != 0)
            {
                _pruneCaches = true;
                NotifyBuffersModified?.Invoke();
            }

            ulong released = before - _cachedBufferBytes;
            ulong kept = _cachedBufferBytes > target ? _cachedBufferBytes - target : 0;

            _coldTrimPasses++;
            _coldTrimBuffers += evicted;
            _coldTrimBytes += released;

            // The first pass, then at most one record every 10 s of play while passes release something and one every
            // 60 s otherwise; each carries the totals, so the passes between two records are counted.
            int interval = _coldTrimBuffers != _coldTrimRecordedBuffers ? ColdTrimNewsIntervalSeconds : ColdTrimQuietIntervalSeconds;

            if (_coldTrimRecords < MaxColdTrimRecords && (_coldTrimRecords == 0 || epoch - _coldTrimRecordEpoch >= interval))
            {
                _coldTrimRecords++;
                _coldTrimRecordEpoch = epoch;
                _coldTrimRecordedBuffers = _coldTrimBuffers;

                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                    "bufferCache",
                    "coldTrim",
                    detail: $"pass {_coldTrimPasses}: released {evicted} buffers ({released / MiB} MiB) unused for {ColdBufferAgeSeconds} s of play, " +
                            $"left {kept / MiB} MiB above the target in use; cache {_cachedBufferBytes / MiB} of {_maxCachedBufferBytes / MiB} MiB; " +
                            $"so far {_coldTrimBuffers} buffers ({_coldTrimBytes / MiB} MiB) in {_coldTrimPasses} passes (adapt_cold_buffer_trim)");
            }
        }
''' + MEMBERS_END

PAIRS = ((CACHE, ADD_OLD, ADD_NEW), (CACHE, TOUCH_OLD, TOUCH_NEW), (CACHE, TRIM_OLD, TRIM_NEW), (BUFFER, FIELD_OLD, FIELD_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
