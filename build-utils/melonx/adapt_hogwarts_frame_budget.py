"""Reduce speculative work and buffer backing on the embedded Vulkan path."""

import hashlib

from adapt_session import once


GPU = 'src/Ryujinx.Graphics.Gpu/'
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
DISK_CACHE = GPU + 'Shader/DiskCache/'


BASELINE = {
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': '2ba59cace1ff874c99617d1da0308a1899192eb071e88dec154ca2199ee1168d',
    'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs': 'edbf2fb50c9ea2f311d537999eae1370e4db4ad94bca62c477e71d4dc64b379e',
    'src/Ryujinx.Graphics.Vulkan/AutoFlushCounter.cs': '2fdb9307872e0e3fcb8f986c5bcdea887571ed512f8b18eb5801c6174bdf8a0b',
    'src/Ryujinx.Graphics.Vulkan/BufferHolder.cs': '65b3f764b802ea24547100ffef5b770efdd7bec01d2e081de9513f4949bfe871',
    'src/Ryujinx.Graphics.Vulkan/BufferManager.cs': '54482c170c881114719f3fdcacd06fa8fa4223c6f9c96834d812f4ff7dce8d92',
    'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs': '8714143fdb047ca14649583693f862e49c5fa28d34ccc60e066b5ecfce06b913',
    'src/Ryujinx.Graphics.Vulkan/MemoryAllocator.cs': '708c5c349c72c8005f7c1ac4a872c06c9da324727fb4b564d53c2463a6853711',
    'src/Ryujinx.Graphics.Vulkan/MemoryAllocatorBlockList.cs': 'bc8e3356198f959bf7fb039f5ceacc1e994f397183f637ddfa446a73a312f9fa',
    'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs': '9c91c012baf658114e178d89d03889459caeeee994322ece827f9fdc4954a261',
    'src/Ryujinx.Library/EmbeddedRuntime.cs': 'b5842f6d9e00122be3a35737fc66dbbe0a7eaf4de0d2aa49c1ad53b93ffdd611',
}

def pace_submissions_and_trim(source):
    context = source / (GPU + 'GpuContext.cs')
    flush = source / (VULKAN + 'AutoFlushCounter.cs')
    # The guest wait path still submits on demand. Forced occlusion/report fences
    # stay strict, and the original thresholds are retained for other games.
    once(context, 'public const double IntervalMs = 4.0;',
         'public const double IntervalMs = 6.0;')
    once(flush, '''        // and on draw in fast flush mode (8 ms): the strict syncs paced on the GPU side are not replaced one for one.
        private readonly static long _pacedFramebufferFlushTimer = Stopwatch.Frequency / 250;
        private readonly static long _pacedDrawFlushTimer = Stopwatch.Frequency / 125;''',
         '''        // Wait 6 ms for an attachment change and 12 ms for an opportunistic draw flush.
        // A real waiter still submits through SyncManager, irrespective of these timers.
        private readonly static long _pacedFramebufferFlushTimer = Stopwatch.Frequency * 6 / 1000;
        private readonly static long _pacedDrawFlushTimer = Stopwatch.Frequency * 12 / 1000;''')
    once(flush, 'the voluntary submissions (attachment change, draw in fast flush mode) wait\n    /// 4 ms and 8 ms',
         'the voluntary submissions (attachment change, draw in fast flush mode) wait\n    /// 6 ms and 12 ms')
    once(context, '''            if (device >= 0 && device <= DeviceShortPercent && now - _lastDeviceShortTrim >= DeviceShortTrimIntervalMs)''',
         '''            // At 8–10% in Hogwarts, release only resources the existing warning path can free without a flush.
            // The critical/escalation thresholds and the process headroom guard still apply in TrimCaches.
            int shortPercent = PaceStrictHostSyncs ? ColdTextureDevicePercent : DeviceShortPercent;
            if (device >= 0 && device <= shortPercent && now - _lastDeviceShortTrim >= DeviceShortTrimIntervalMs)''')
    return [context, flush]


def retain_texture_bindings(source):
    path = source / (VULKAN + 'DescriptorSetUpdater.cs')
    once(path, '''            TextureArrayExtra = 1 << 4,
            All = Uniform | Storage | Texture | Image | TextureArrayExtra,''',
         '''            TextureArrayExtra = 1 << 4,
            ImageArrayExtra = 1 << 5,
            All = Uniform | Storage | Texture | Image | TextureArrayExtra | ImageArrayExtra,''')
    once(path, '''            if (!program.HasSameLayout(_program))
            {''',
         '''            bool sameLayout = program.HasSameLayout(_program);
            if (!sameLayout)
            {''')
    once(path, '''            _program = program;
            _updateDescriptorCacheCbIndex = true;
            _dirty = DirtyFlags.All;
        }

        internal static DirtyFlags BufferViewSets''',
         '''            // The exact same layout, bind point and scalar texture bindings can
            // keep their set. Leave array-dependent and dynamic buffer views on the
            // existing update path, and retain any invalidation already pending.
            bool keepTextures = EncodingPolicy.IncrementalArrayDescriptors && isBound && sameLayout &&
                program.IsCompute == _program.IsCompute &&
                !program.UpdateTexturesWithoutTemplate && !_program.UpdateTexturesWithoutTemplate &&
                SameScalarTextureBindings(program, _program);
            _program = program;
            _updateDescriptorCacheCbIndex = true;
            _dirty |= keepTextures ? DirtyFlags.All & ~DirtyFlags.Texture : DirtyFlags.All;
        }

        private static bool SameScalarTextureBindings(ShaderCollection program, ShaderCollection previous)
        {
            ResourceBindingSegment[] current = program.BindingSegments[PipelineBase.TextureSetIndex];
            ResourceBindingSegment[] prior = previous.BindingSegments[PipelineBase.TextureSetIndex];
            if (current.Length != prior.Length)
            {
                return false;
            }

            for (int i = 0; i < current.Length; i++)
            {
                ref readonly ResourceBindingSegment a = ref current[i];
                ref readonly ResourceBindingSegment b = ref prior[i];
                if (a.IsArray || b.IsArray || a.Type == ResourceType.BufferTexture ||
                    a.Binding != b.Binding || a.Count != b.Count || a.Type != b.Type || a.Stages != b.Stages)
                {
                    return false;
                }
            }

            return true;
        }

        internal static DirtyFlags BufferViewSets''')
    once(path, '''                arrayRef = new ArrayRef<ImageArray>(stage, array as ImageArray);

                SignalDirty(DirtyFlags.TextureArrayExtra);''',
         '''                arrayRef = new ArrayRef<ImageArray>(stage, array as ImageArray);

                SignalDirty(DirtyFlags.ImageArrayExtra);''')
    once(path, '''                BindExtraSets(cbs, program, pbp, arraysKept: (_dirty & DirtyFlags.TextureArrayExtra) == 0);''',
         '''                BindExtraSets(cbs, program, pbp);''')
    once(path, '''        private void BindExtraSets(CommandBufferScoped cbs, ShaderCollection program, PipelineBindPoint pbp, bool arraysKept = false)''',
         '''        private void BindExtraSets(CommandBufferScoped cbs, ShaderCollection program, PipelineBindPoint pbp)''')
    once(path, '''                if (arraysKept && segment.IsArray && segment.Type is not (ResourceType.BufferTexture or ResourceType.BufferImage))
                {
                    continue;
                }''',
         '''                DirtyFlags arrayFlags = DirtyFlags.TextureArrayExtra | DirtyFlags.ImageArrayExtra;
                if (EncodingPolicy.IncrementalArrayDescriptors)
                {
                    arrayFlags = segment.Type == ResourceType.Image ? DirtyFlags.ImageArrayExtra : DirtyFlags.TextureArrayExtra;
                }

                if ((_dirty & arrayFlags) == 0 && segment.IsArray &&
                    segment.Type is not (ResourceType.BufferTexture or ResourceType.BufferImage))
                {
                    continue;
                }''')
    once(path, 'SignalDirty(DirtyFlags.Image | DirtyFlags.TextureArrayExtra);',
         'SignalDirty(DirtyFlags.Image | DirtyFlags.ImageArrayExtra);')
    return [path]


def keep_partial_buffer_mirrors(source):
    path = source / (VULKAN + 'BufferHolder.cs')
    once(path, '                _mirrors = new Dictionary<ulong, StagingBufferReserved>();',
         '                _mirrors ??= new Dictionary<ulong, StagingBufferReserved>();')
    once(path, '''                int capacity = Size >= 85000 && length <= MirrorWindowBytes ? MirrorWindowBytes : Size;''',
         '''                int capacity = EncodingPolicy.IncrementalArrayDescriptors && Size >= 85000
                    ? Math.Min(Size, Math.Max(length, MirrorWindowBytes))
                    : Size >= 85000 && length <= MirrorWindowBytes ? MirrorWindowBytes : Size;''')
    once(path, '''                    byte[] full = new byte[Size];
                    previous.AsSpan().CopyTo(full.AsSpan(_pendingDataOffset));
                    _pendingData = full;
                    _pendingDataOffset = 0;
                    MirrorCopyJournal.Added(full.Length, previous.Length);''',
         '''                    int start = 0;
                    int capacity = Size;
                    if (EncodingPolicy.IncrementalArrayDescriptors)
                    {
                        int end = Math.Max(offset + length, _pendingDataOffset + previous.Length);
                        start = Math.Min(offset, _pendingDataOffset);
                        capacity = (int)Math.Min(Size, Math.Max(end - start, previous.Length * 2L));
                        start = Math.Min(start, Size - capacity);
                    }

                    byte[] expanded = new byte[capacity];
                    previous.AsSpan().CopyTo(expanded.AsSpan(_pendingDataOffset - start));
                    _pendingData = expanded;
                    _pendingDataOffset = start;
                    MirrorCopyJournal.Added(expanded.Length, previous.Length);''')
    once(path, '''                _mirrors.Clear();
            }
        }

        public void ClearMirrors(CommandBufferScoped''',
         '''                _mirrors.Clear();
                // The command buffer has switched. Release a large backing array only
                // once staging references and dirty ranges are both gone.
                if (EncodingPolicy.IncrementalArrayDescriptors && _pendingData.Length >= 85000 &&
                    _pendingDataRanges.Count() == 0)
                {
                    MirrorCopyJournal.Removed(_pendingData.Length);
                    _pendingData = null;
                    _pendingDataOffset = 0;
                }
            }
        }

        public void ClearMirrors(CommandBufferScoped''')
    once(path, '''                _pendingDataRanges.Remove(offset, size);

                foreach''',
         '''                // A nested render-pass submission may clear the mirrors while
                // uploading. Keep the data and origin alive for this whole batch.
                byte[] pending = _pendingData;
                int pendingOffset = _pendingDataOffset;
                _pendingDataRanges.Remove(offset, size);

                foreach''')
    once(path, 'SetData(rangeOffset, _pendingData.AsSpan(rangeOffset - _pendingDataOffset, rangeSize), cbs, _gd.PipelineInternal.EndRenderPassDelegate, false);',
         'SetData(rangeOffset, pending.AsSpan(rangeOffset - pendingOffset, rangeSize), cbs, _gd.PipelineInternal.EndRenderPassDelegate, false);')
    once(path, 'SetData(rangeOffset, _pendingData.AsSpan(rangeOffset - _pendingDataOffset, rangeSize), cbs, null, false);',
         'SetData(rangeOffset, pending.AsSpan(rangeOffset - pendingOffset, rangeSize), cbs, null, false);')
    return [path]


def prioritize_cache_loading(source):
    path = source / (VULKAN + 'PipelineCacheManager.cs')
    once(path, '''        private readonly ManualResetEventSlim _mainLoaded = new(true);''',
         '''        private readonly ManualResetEventSlim _mainLoaded = new(true);
        private readonly ManualResetEventSlim _primaryCacheReady = new(true);
        private long _smallSavedSidecarGeneration = -1;''')
    once(path, '''            if (_mainLoaded.IsSet)
            {
                return;
            }

            long remaining''', '''            if (_primaryCacheReady.IsSet)
            {
                return;
            }

            long remaining''')
    once(path, '_mainLoaded.Wait((int)Math.Min(remaining, int.MaxValue));',
         '_primaryCacheReady.Wait((int)Math.Min(remaining, int.MaxValue));')
    once(path, '            _mainLoaded.Reset();',
         '            _mainLoaded.Reset();\n            _primaryCacheReady.Reset();')
    once(path, '''                // The worker snapshots load here too, outside the main lock.''',
         '''                // Publish the primary snapshot as soon as it can serve lookups. Keep
                // checkpointing frozen until the secondary snapshots are accounted for.
                if (accepted && staging.Handle != 0)
                {
                    Interlocked.Increment(ref _mainCheckpointHolders);
                    _mainCacheLock.Enter();
                    try
                    {
                        if (_disposed)
                        {
                            accepted = false;
                        }
                        else
                        {
                            ReadOnlySpan<PipelineCache> primary = stackalloc PipelineCache[] { staging };
                            accepted = MergeInto(_mainState.Cache, primary);
                            failed = !accepted;
                            if (accepted)
                            {
                                _mainState.HasUsableSnapshot = true;
                            }
                        }
                    }
                    finally
                    {
                        _mainCacheLock.Exit();
                        Interlocked.Decrement(ref _mainCheckpointHolders);
                    }

                    if (accepted)
                    {
                        Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineCache", "primaryReady",
                            detail: $"{FormatSize(length)} in {Environment.TickCount64 - start} ms");
                        _primaryCacheReady.Set();
                    }
                }

                // The worker snapshots load here too, outside the main lock.''')
    once(path, '''                        if (accepted && staging.Handle != 0)
                        {
                            ReadOnlySpan<PipelineCache> source = stackalloc PipelineCache[] { staging };

                            if (!MergeInto(_mainState.Cache, source))
                            {
                                accepted = false;
                                failed = true;
                            }
                        }

''', '                        // The primary was merged before loading the worker snapshots.\n\n')
    once(path, '''                                Interlocked.Exchange(ref _workerSnapshotsHeldUntil, held);
                            }''',
         '''                                Interlocked.Exchange(ref _workerSnapshotsHeldUntil, held);
                                if (accepted && mergedBytes <= MaxSmallSavedSidecarBytes && held - 1 == _mainState.SavedGeneration)
                                {
                                    // Every byte added here is already in a durable worker snapshot.
                                    _smallSavedSidecarGeneration = held;
                                }
                            }''')
    once(path, '        public void MergeAndSave()',
         '        private const long MaxSmallSavedSidecarBytes = 256 * 1024;\n\n        public void MergeAndSave()')
    once(path, '''                    Maintain(_mainState, force: true, allowRecycle: false);

                    // Main's file holds main's content''',
         '''                    if (count == 0 && !_mainState.Frozen && _mainState.Generation == _smallSavedSidecarGeneration)
                    {
                        Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineCache", "retainedSmallSidecars",
                            detail: "Only already-persisted worker snapshots were merged; primary and worker files kept.");
                    }
                    else
                    {
                        Maintain(_mainState, force: true, allowRecycle: false);
                    }

                    // Main's file holds main's content''')
    once(path, '                _mainLoaded.Set();',
         '                _mainLoaded.Set();\n                _primaryCacheReady.Set();')
    once(path, '''                _ready.Sort((a, b) => Compare(a.Record, b.Record));''',
         '''                _ready.Sort((a, b) => CompareForPlayback(a.Record, b.Record));''')
    once(path, '''        internal static int Compare(Record a, Record b)''',
         '''        private static int CompareForPlayback(Record a, Record b)
        {
            if (EncodingPolicy.IncrementalArrayDescriptors)
            {
                const uint LaunchWindowMs = 30_000;
                int seenDuringLaunch = (b.FirstSeenMs <= LaunchWindowMs).CompareTo(a.FirstSeenMs <= LaunchWindowMs);
                if (seenDuringLaunch != 0)
                {
                    return seenDuringLaunch;
                }
            }
            return Compare(a, b);
        }

        internal static int Compare(Record a, Record b)''')
    return [path]


def pool_small_temporary_buffers(source):
    manager = source / (VULKAN + 'BufferManager.cs')
    allocator = source / (VULKAN + 'MemoryAllocator.cs')
    blocks = source / (VULKAN + 'MemoryAllocatorBlockList.cs')
    once(manager, '''            out BufferHolder holder,
            bool sparseCompatible = false,
            BufferAllocationType baseType = BufferAllocationType.HostMapped,
            bool forceMirrors = false)
        {
            holder = Create(gd, size, forConditionalRendering: false, sparseCompatible, baseType);''',
         '''            out BufferHolder holder,
            bool sparseCompatible = false,
            BufferAllocationType baseType = BufferAllocationType.HostMapped,
            bool forceMirrors = false,
            bool temporary = false)
        {
            holder = Create(gd, size, forConditionalRendering: false, sparseCompatible, baseType, temporary);''')
    once(manager, '''                BufferHandle handle = CreateWithHandle(gd, size, out BufferHolder holder);

                return new ScopedTemporaryBuffer''',
         '''                BufferHandle handle = CreateWithHandle(gd, size, out BufferHolder holder, temporary: true);

                return new ScopedTemporaryBuffer''')
    once(manager, 'BufferAllocationType fallbackType = BufferAllocationType.Auto)',
         'BufferAllocationType fallbackType = BufferAllocationType.Auto,\n            bool temporary = false)')
    once(manager, '''            if (sparseCompatible)
            {
                requirements.Alignment''',
         '''            bool poolSmallBuffer = false;
            if (temporary && !sparseCompatible && OperatingSystem.IsIOS() && EncodingPolicy.IncrementalArrayDescriptors &&
                requirements.Size <= 64 * 1024 && requirements.Alignment <= (ulong)Environment.SystemPageSize)
            {
                MemoryDedicatedRequirements dedicated = new() { SType = StructureType.MemoryDedicatedRequirements };
                MemoryRequirements2 requirements2 = new() { SType = StructureType.MemoryRequirements2, PNext = &dedicated };
                BufferMemoryRequirementsInfo2 bufferInfo = new()
                {
                    SType = StructureType.BufferMemoryRequirementsInfo2,
                    Buffer = buffer,
                };
                gd.Api.GetBufferMemoryRequirements2(_device, &bufferInfo, &requirements2);
                requirements = requirements2.MemoryRequirements;
                poolSmallBuffer = !dedicated.RequiresDedicatedAllocation && !dedicated.PrefersDedicatedAllocation &&
                    requirements.Size <= 64 * 1024 && requirements.Alignment <= (ulong)Environment.SystemPageSize;
            }

            if (sparseCompatible)
            {
                requirements.Alignment''')
    once(manager, 'allocation = gd.MemoryAllocator.AllocateDeviceMemory(requirements, allocateFlags, true);',
         'allocation = gd.MemoryAllocator.AllocateDeviceMemory(requirements, allocateFlags, true, poolSmallBuffer);')
    once(manager, '''            BufferAllocationType baseType = BufferAllocationType.HostMapped)
        {
            BufferAllocationType type = baseType;''',
         '''            BufferAllocationType baseType = BufferAllocationType.HostMapped,
            bool temporary = false)
        {
            BufferAllocationType type = baseType;''')
    once(manager, 'CreateBacking(gd, size, type, forConditionalRendering, sparseCompatible);',
         'CreateBacking(gd, size, type, forConditionalRendering, sparseCompatible, temporary: temporary);')
    once(manager, '''            gd.Api.BindBufferMemory(_device, buffer, allocation.Memory, allocation.Offset);

            return (buffer, allocation, type);''',
         '''            Result bound = gd.Api.BindBufferMemory(_device, buffer, allocation.Memory, allocation.Offset);
            if (poolSmallBuffer && bound != Result.Success)
            {
                allocation.Dispose();
                allocation = default;
                try
                {
                    allocation = gd.MemoryAllocator.AllocateDeviceMemory(requirements, GetMemoryFlags(type), isBuffer: true);
                    if (allocation.Memory.Handle != 0 &&
                        gd.Api.BindBufferMemory(_device, buffer, allocation.Memory, allocation.Offset) == Result.Success)
                    {
                        return (buffer, allocation, type);
                    }
                }
                catch (VulkanException)
                {
                    // Use the caller's ordinary allocation failure path below.
                }

                gd.Api.DestroyBuffer(_device, buffer, null);
                if (allocation.Memory.Handle != 0)
                {
                    allocation.Dispose();
                }
                return default;
            }

            return (buffer, allocation, type);''')
    once(allocator, '''            bool isBuffer = false)
        {''', '''            bool isBuffer = false,
            bool poolSmallBuffer = false)
        {''')
    once(allocator, '''            return Allocate(memoryTypeIndex, requirements.Size, requirements.Alignment, map, isBuffer);
        }

        private MemoryAllocation Allocate(int memoryTypeIndex, ulong size, ulong alignment, bool map, bool isBuffer)''',
         '''            if (poolSmallBuffer && map && flags.HasFlag(MemoryPropertyFlags.HostCoherentBit))
            {
                try
                {
                    return Allocate(memoryTypeIndex, requirements.Size, requirements.Alignment, map, isBuffer, pooledTemporary: true);
                }
                catch (VulkanException)
                {
                    // Try the ordinary allocation of the same memory type first.
                }
            }
            return Allocate(memoryTypeIndex, requirements.Size, requirements.Alignment, map, isBuffer);
        }

        private MemoryAllocation Allocate(int memoryTypeIndex, ulong size, ulong alignment, bool map, bool isBuffer,
            bool pooledTemporary = false)''')
    # The same key is checked under the read lock and again under the write lock.
    lookup = 'bl.MemoryTypeIndex == memoryTypeIndex && bl.ForBuffer == isBuffer)'
    once(allocator, f'''                    if ({lookup}
                    {{
                        return bl.Allocate(size, alignment, map);
                    }}
                }}
            }}
            finally
            {{
                _lock.ExitReadLock();''',
         '''                    if (bl.MemoryTypeIndex == memoryTypeIndex && bl.ForBuffer == isBuffer &&
                        bl.PooledTemporary == pooledTemporary)
                    {
                        return bl.Allocate(size, alignment, map);
                    }
                }
            }
            finally
            {
                _lock.ExitReadLock();''')
    once(allocator, f'''                    if ({lookup}
                    {{
                        return bl.Allocate(size, alignment, map);
                    }}
                }}

                MemoryAllocatorBlockList newBl = new(_api, _device, memoryTypeIndex, _poolBlockSize, isBuffer);''',
         '''                    if (bl.MemoryTypeIndex == memoryTypeIndex && bl.ForBuffer == isBuffer &&
                        bl.PooledTemporary == pooledTemporary)
                    {
                        return bl.Allocate(size, alignment, map);
                    }
                }

                const int TemporaryBlockSize = 1024 * 1024;
                MemoryAllocatorBlockList newBl = new(_api, _device, memoryTypeIndex,
                    pooledTemporary ? TemporaryBlockSize : _poolBlockSize, isBuffer, pooledTemporary);''')
    once(blocks, '''        public MemoryAllocatorBlockList(Vk api, Device device, int memoryTypeIndex, int poolBlockSize, bool forBuffer)
        {''',
         '''        private const int MaxTemporaryBlocks = 2;
        private int _temporaryBlocks;
        internal bool PooledTemporary { get; }

        public MemoryAllocatorBlockList(Vk api, Device device, int memoryTypeIndex, int poolBlockSize, bool forBuffer,
            bool pooledTemporary = false)
        {
            PooledTemporary = pooledTemporary;''')
    once(blocks, '''            ulong blockSize = dedicated ? size : (ulong)_poolBlockSize;''',
         '''            bool reserveTemporary = PooledTemporary && !dedicated;
            if (reserveTemporary && Interlocked.Increment(ref _temporaryBlocks) > MaxTemporaryBlocks)
            {
                Interlocked.Decrement(ref _temporaryBlocks);
                reserveTemporary = false;
                dedicated = true;
            }

            ulong blockSize = dedicated ? size : (ulong)_poolBlockSize;''')
    once(blocks, '''            _api.AllocateMemory(_device, in memoryAllocateInfo, null, out DeviceMemory deviceMemory).ThrowOnError();

            nint hostPointer''',
         '''            DeviceMemory deviceMemory = default;
            nint hostPointer''')
    once(blocks, '''            try
            {
                if (map)
                {
                    void* pointer''',
         '''            try
            {
                _api.AllocateMemory(_device, in memoryAllocateInfo, null, out deviceMemory).ThrowOnError();
                if (map)
                {
                    void* pointer''')
    once(blocks, '''                if (!published)
                {
                    try''',
         '''                if (!published && reserveTemporary)
                {
                    Interlocked.Decrement(ref _temporaryBlocks);
                }
                if (!published && deviceMemory.Handle != 0)
                {
                    try''')
    once(blocks, '''            if (destroy)
            {
                block.Destroy(_api, _device);
            }''',
         '''            if (destroy)
            {
                block.Destroy(_api, _device);
                if (PooledTemporary && !block.Dedicated)
                {
                    Interlocked.Decrement(ref _temporaryBlocks);
                }
            }''')
    return [manager, allocator, blocks]


def batch_startup_validation(source):
    path = source / (DISK_CACHE + 'DiskCacheHostStorage.cs')
    # EnqueueForValidation still applies the in-flight limit on every program.
    # The final blocking drain validates the tail even when there are < 8 entries.
    once(path, '''                    loader.CheckCompilation();
                    programIndex++;''',
         '''                    programIndex++;
                    if ((programIndex & 7) == 0)
                    {
                        loader.CheckCompilation();
                    }''')
    return [path]


def trace_jit_startup(source):
    path = source / 'src/Ryujinx.Library/EmbeddedRuntime.cs'
    once(path, '''                Ryujinx.Cpu.LightningJit.DualMappedMemory.PrepareEmbeddedMapping();
                EmbeddedLaunchDiagnostics.Record("jitArena", "passed",''',
         '''                using (new Ryujinx.Common.EmbeddedStartupTrace(mappedArena == 0 ? "jitArenaCold" : "jitArenaReuse"))
                {
                    Ryujinx.Cpu.LightningJit.DualMappedMemory.PrepareEmbeddedMapping();
                }
                EmbeddedLaunchDiagnostics.Record("jitArena", "passed",''')
    return [path]


def apply(source):
    for name, digest in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest, name
    return (
        pace_submissions_and_trim(source)
        + retain_texture_bindings(source)
        + keep_partial_buffer_mirrors(source)
        + pool_small_temporary_buffers(source)
        + prioritize_cache_loading(source)
        + batch_startup_validation(source)
        + trace_jit_startup(source)
    )
