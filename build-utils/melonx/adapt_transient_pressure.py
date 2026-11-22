"""Bound iOS upload and clean texture reclamation on the Hogwarts Vulkan path."""

import hashlib
from adapt_session import once


BASELINE = {
    'src/Ryujinx.Memory/HostMemoryBudget.cs': '8b3eb7295bb936ee96d4d97ba78adf41467855fb8900be089115ddd2139fd116',
    'src/Ryujinx.Common/Memory/MemoryOwner.cs': 'f94421c357ea252fd61e39c0e08969916eaaeb2327f4b1f60acd57300820d0ee',
    'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs': 'cc9fc4fa94429459eff6f8f5e6f152095581bef0e97d8e00c005aed2467a44d3',
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': 'a0fd265deec4cb5ae0676495f42733add8be1435d2dd47f0d3601dbe5adc5c01',
    'src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs': '50a61fbe658928195d9ce835b6892cac953d0efc7a90de2deadc936c7ed027ae',
    'src/Ryujinx.Graphics.Vulkan/BufferManager.cs': '06fe2224a972eed90da0490e996427d8ef499f9063b88152d011382b9f37c13f',
    'src/Ryujinx.Graphics.Vulkan/StagingBuffer.cs': '9df664492142b5347b431b402ec0866300d8da68829ab716a929a54148798e0a',
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': '27f89c04260ce82bf3ff8468eda36785516b081567e260e534a7074bbf2eb2d8',
}


def apply(source):
    budget = source / 'src/Ryujinx.Memory/HostMemoryBudget.cs'
    owner = source / 'src/Ryujinx.Common/Memory/MemoryOwner.cs'
    threaded = source / 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
    context = source / 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
    texture = source / 'src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs'
    buffers = source / 'src/Ryujinx.Graphics.Vulkan/BufferManager.cs'
    staging = source / 'src/Ryujinx.Graphics.Vulkan/StagingBuffer.cs'
    renderer = source / 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs'
    for name, expected in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name

    available = """        public static ulong AvailableBytes
        {
            get
            {
                if (!OperatingSystem.IsIOS())
                {
                    return 0;
                }

                try
                {
                    long available = OsProcAvailableMemory();

                    return available > 0 ? (ulong)available : 0;
                }
                catch (EntryPointNotFoundException)
                {
                    return 0;
                }
            }
        }"""
    nullable = available.replace("public static ulong AvailableBytes", "public static ulong? ProcessHeadroomBytes")
    nullable = nullable.replace("return 0;", "return null;").replace(
        "return available > 0 ? (ulong)available : 0;", "return available >= 0 ? (ulong)available : null;")
    once(budget, available, """        public static ulong AvailableBytes => ProcessHeadroomBytes ?? 0;

        // A successful iOS query may report zero at the process limit.
""" + nullable)

    once(owner, 'namespace Ryujinx.Common.Memory\n{', '''namespace Ryujinx.Common.Memory
{
    // One sensor sample per second from the GPU context. Shared only with
    // the renderer and the byte-array pool; neither calls iOS from a draw.
    public static class UploadMemoryPressure
    {
        private static int _active;
        public static bool Active => Volatile.Read(ref _active) != 0;
        public static void Reset() => Volatile.Write(ref _active, 0);

        public static bool Update(int deviceAvailablePercent, ulong? processAvailable, ulong footprint)
        {
            bool wasActive = Active;
            int threshold = wasActive ? 25 : 20;
            // available / (footprint + available) below 1/5 (recover at 1/4).
            // Zero from a valid query is real process pressure; null is unavailable.
            ulong divisor = wasActive ? 3UL : 4UL;
            bool processShort = processAvailable is ulong room &&
                                (room == 0 || (footprint != 0 && room <= (footprint - 1) / divisor));
            bool deviceShort = deviceAvailablePercent >= 0 && deviceAvailablePercent < threshold;
            bool active = processShort || deviceShort;
            Volatile.Write(ref _active, active ? 1 : 0);
            return active;
        }
    }
''')
    once(owner, '            private static long Bytes(T[] array)', '''            // Keep the reusable primary array for each size. Reclaim only
            // returned duplicates, without contending with a simultaneous rent.
            internal static long TrimIdleSpares(long now)
            {
                const long budget = 16L << 20;
                if (!_lock.TryEnter()) return 0;
                try
                {
                    long dropped = 0;
                    int checks = 0;
                    var node = _spares.First;
                    while (node != null && checks++ < 16)
                    {
                        Holder holder = node.Value;
                        node = node.Next;
                        if (now - holder.Returned < 500) break;
                        long bytes = Bytes(holder.Array!);
                        if (bytes <= budget - dropped)
                        {
                            RemoveSpareLocked(holder);
                            dropped += bytes;
                        }
                    }
                    return dropped;
                }
                finally { _lock.Exit(); }
            }

            private static long Bytes(T[] array)''')
    once(owner, '                if (bytes < MinSpareBytes || bytes > MaxSpareBytes)', '''                // Keep reuse for bursts. Once the smaller quota is full, stop
                // adding duplicates; existing entries drain under the bounded trim.
                if (typeof(T) == typeof(byte) && UploadMemoryPressure.Active && _spareBytes + bytes > (16L << 20))
                {
                    return;
                }
                if (bytes < MinSpareBytes || bytes > MaxSpareBytes)''')
    once(owner, '        public static MemoryOwner<T> Rent(int length) => new(length);',
         '''        public static MemoryOwner<T> Rent(int length) => new(length);

        public static long TrimIdleUploadSpares(long now) => ArrayPooling.TrimIdleSpares(now);''')
    once(threaded, "        public IRenderer BaseRenderer => _baseRenderer;", """        public IRenderer BaseRenderer => _baseRenderer;

        // Single GAL producer only. The consumer can only make more room.
        public int AvailableCommandSlots =>
            (Volatile.Read(ref _consumerPtr) - _producerPtr + QueueCount - 1) % QueueCount;""")
    once(context, 'using Ryujinx.Common.Logging;', 'using Ryujinx.Common.Logging;\nusing Ryujinx.Common.Memory;')
    once(context, '        public static bool PaceStrictHostSyncs { get; set; }', '''        public static bool PaceStrictHostSyncs
        {
            get;
            set
            {
                UploadMemoryPressure.Reset();
                field = value;
            }
        }''')
    once(context, '            ReleaseColdTextures(device, now, out _);', '''            if (PaceStrictHostSyncs)
            {
                bool pressure = UploadMemoryPressure.Update(device, HostMemoryBudget.ProcessHeadroomBytes, HostMemoryBudget.FootprintBytes);
                if (pressure)
                {
                    _returnedUploadBytes += MemoryOwner<byte>.TrimIdleUploadSpares(now);
                    // At <=10% the existing cold pass already owns this work.
                    if (TextureUseEpoch >= _coldTextureAgeSeconds && (device < 0 || device > ColdTextureDevicePercent))
                    {
                        ReleaseEarlyColdTextures();
                    }
                }
            }
            ReleaseColdTextures(device, now, out _);''')
    once(context, '        private long _lastColdTextureRelease;', '''        private int _nextPressurePool;
        private long _returnedUploadBytes;
        private ulong _earlyColdTextureBytes;

        private void ReleaseEarlyColdTextures()
        {
            const int maxTextures = 16;
            // Disposing one eligible texture enqueues up to four host texture
            // releases and one optional group flush-buffer deletion.
            if (Renderer is Ryujinx.Graphics.GAL.Multithreading.ThreadedRenderer threaded &&
                threaded.AvailableCommandSlots < 5 * maxTextures) return;

            // Try once between command lists. A concurrent pool registration
            // or removal wins; the next sensor tick will try again.
            if (!Monitor.TryEnter(TexturePools)) return;
            try
            {
                if (TexturePools.Count == 0) return;
                if (_nextPressurePool >= TexturePools.Count) _nextPressurePool = 0;
                var pool = TexturePools[_nextPressurePool++];
                ColdTextureStats stats = default;
                pool.ScanColdTextures(TextureUseEpoch, _coldTextureAgeSeconds, true,
                    32UL << 20, maxTextures, ref stats, slotBudget: 512);
                _earlyColdTextureBytes += stats.ReleasedBytes;
                _coldReleasedTotal += stats.Released;
                _coldReleasedBytesTotal += stats.ReleasedBytes;
            }
            finally { Monitor.Exit(TexturePools); }
        }

        private long _lastColdTextureRelease;''')
    once(context, '''$"Host memory: footprint {HostMemoryBudget.FootprintBytes / TrimMiB} MiB, " +''','''$"Host memory: footprint {HostMemoryBudget.FootprintBytes / TrimMiB} MiB, " +
                $"early clean texture estimates {_earlyColdTextureBytes / TrimMiB} MiB, returned upload arrays {_returnedUploadBytes / (long)TrimMiB} MiB (session totals), " +''')
    anchor = '''        internal void ScanColdTextures(int epoch, int minimumAge, bool release, ulong byteBudget, int countBudget, ref GpuContext.ColdTextureStats stats)
        {
            Texture[] items = Items;

            if (items == null)
            {
                return;
            }

            for (int id = 0; id < items.Length; id++)
            {
                Texture texture = items[id];'''
    once(texture, '        /// <summary>\n        /// RewindBox (adapt_cold_texture_release): measures', '''        private int _nextPressureSlot;

        /// <summary>
        /// RewindBox (adapt_cold_texture_release): measures''')
    once(texture, anchor, '''        internal void ScanColdTextures(int epoch, int minimumAge, bool release, ulong byteBudget, int countBudget,
            ref GpuContext.ColdTextureStats stats, int slotBudget = 0)
        {
            Texture[] items = Items;
            if (items == null || items.Length == 0) return;

            int first = 0, end = items.Length;
            if (slotBudget > 0)
            {
                first = _nextPressureSlot < end ? _nextPressureSlot : 0;
                end = first + Math.Min(slotBudget, end - first);
                _nextPressureSlot = end == items.Length ? 0 : end;
            }
            for (int id = first; id < end; id++)
            {
                // Prune reload stamps within the same inspection budget.
                if (slotBudget > 0 && _coldReleasedAt != null && _coldReleasedAt.TryGetValue(id, out int previous) &&
                    epoch - previous > GpuContext.ColdTextureReloadWindowSeconds)
                {
                    _coldReleasedAt.Remove(id);
                }
                Texture texture = items[id];''')
    # Release bounded fence references first. A recording / in-flight copy
    # retains its fence. The mandatory vertex ring keeps its current behavior.
    once(staging, '        public void FreeCompleted()', '''        internal bool IsIdle => _freeSize == BufferSize && _pendingCopies.Count == 0;

        public void FreeCompleted() => FreeCompleted(int.MaxValue);

        internal void FreeCompleted(int limit)''')
    once(staging, '            while (_pendingCopies.TryPeek(out PendingCopy pc) && (pc.Fence == signalledFence',
         '            while (limit-- > 0 && _pendingCopies.TryPeek(out PendingCopy pc) && (pc.Fence == signalledFence')
    once(buffers, '        private bool _textureStagingUnavailable;', '''        private bool _textureStagingUnavailable;
        private bool _textureUploadUsed;
        private long _lastTextureUpload, _lastTexturePressureCheck;

        internal void RetireIdleTextureStaging()
        {
            StagingBuffer ring = _textureStagingBuffer;
            if (ring == null) return;
            long now = Environment.TickCount64;
            if (now - _lastTexturePressureCheck < 1000) return;
            _lastTexturePressureCheck = now;
            if (_textureUploadUsed)
            {
                _textureUploadUsed = false;
                _lastTextureUpload = now;
                return;
            }
            if (now - _lastTextureUpload < 3000) return;
            ring.FreeCompleted(32);
            if (ring.IsIdle)
            {
                _textureStagingBuffer = null;
                ring.Dispose();
                Logger.Debug?.Print(LogClass.Gpu, "iOS pressure retired the idle 16 MiB texture upload ring");
            }
        }''')
    once(buffers, '''            if (_textureStagingBuffer != null)
            {
                return _textureStagingBuffer;''','''            if (OperatingSystem.IsIOS() && !gd.CommandBufferPool.OwnedByCurrentThread) return null;
            _textureUploadUsed = true;
            if (_textureStagingBuffer != null)
            {
                return _textureStagingBuffer;''')
    once(renderer, '''        public void PreFrame()
        {
            ThrowIfBackgroundPipelineFailed();''','''        public void PreFrame()
        {
            // Serialized with texture uploads by the GAL command owner.
            if (Ryujinx.Common.Memory.UploadMemoryPressure.Active && CommandBufferPool.OwnedByCurrentThread)
            {
                BufferManager.RetireIdleTextureStaging();
            }
            ThrowIfBackgroundPipelineFailed();''')
    return [budget, owner, threaded, context, texture, buffers, staging, renderer]
