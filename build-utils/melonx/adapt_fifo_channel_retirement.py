"""Keep a GPU channel alive through the FIFO entries already accepted for it."""

import hashlib

from adapt_session import once


GPU = 'src/Ryujinx.Graphics.Gpu/'
FIFO = GPU + 'Engine/GPFifo/'
CHANNEL = GPU + 'GpuChannel.cs'
DEVICE = FIFO + 'GPFifoDevice.cs'
PROCESSOR = FIFO + 'GPFifoProcessor.cs'
WINDOW = GPU + 'Window.cs'
MEMORY = GPU + 'Memory/MemoryManager.cs'
PHYSICAL = GPU + 'Memory/PhysicalMemory.cs'
NV_CHANNEL = 'src/Ryujinx.HLE/HOS/Services/Nv/NvDrvServices/NvHostChannel/NvHostChannelDeviceFile.cs'

BASELINE = {'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs': '6cd79be67a7693a227ff9d51118c778166564db6e6297741e8e1a236178987f6',
 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoProcessor.cs': '71b397bdaf2e6972c15ceea79e60c13746fc349a3acb64b9e79d05f93550ba9c',
 'src/Ryujinx.Graphics.Gpu/GpuChannel.cs': '349a932f6cca03e7a1f99aee33a01f2b9eeb1f1963df37cd6002884994f240c0',
 'src/Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs': '608945fd1d9769e52d9c9f7e58c7f3e10bc3bc324947e6bc76467dbe4ab80786',
 'src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs': 'f8187ac7a6c3cce1a93105fa27b84b66e8b5e26fbe7cbe1b1e1e1cc449dbfd66',
 'src/Ryujinx.Graphics.Gpu/Window.cs': 'a80510e7b2f6a806ff67402243c524947fffc836c2684b323947393ad9bbb484',
 'src/Ryujinx.HLE/HOS/Services/Nv/NvDrvServices/NvHostChannel/NvHostChannelDeviceFile.cs': 'fd12303e716df0605e7d4b226c60bf0fc73450b211b3a76b02ee96d709c868c4'}


def apply(source):
    for name, digest in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest, name

    channel = source / CHANNEL
    device = source / DEVICE
    processor = source / PROCESSOR
    nv_channel = source / NV_CHANNEL
    window = source / WINDOW
    memory = source / MEMORY
    physical = source / PHYSICAL

    once(channel, '        private MemoryManager _memoryManager;',
         '''        private MemoryManager _memoryManager;
        private readonly object _submissionGate = new();
        private bool _retiring;
        private Action _onRetired;''')
    once(channel, '''        public void BindMemory(MemoryManager memoryManager)
        {
            MemoryManager oldMemoryManager = Interlocked.Exchange(ref _memoryManager, memoryManager ?? throw new ArgumentNullException(nameof(memoryManager)));

            memoryManager.Physical.IncrementReferenceCount();

            if (oldMemoryManager != null)
            {
                oldMemoryManager.Physical.BufferCache.NotifyBuffersModified -= BufferManager.Rebind;
                oldMemoryManager.Physical.DecrementReferenceCount();
                oldMemoryManager.MemoryUnmapped -= MemoryUnmappedHandler;
            }

            memoryManager.Physical.BufferCache.NotifyBuffersModified += BufferManager.Rebind;''',
         '''        public void BindMemory(MemoryManager memoryManager)
        {
            ArgumentNullException.ThrowIfNull(memoryManager);

            lock (_submissionGate)
            {
                ObjectDisposedException.ThrowIf(_retiring, this);
                BindMemoryCore(memoryManager);
            }
        }

        private void BindMemoryCore(MemoryManager memoryManager)
        {
            memoryManager.AttachToChannel(BufferManager.Rebind);
            MemoryManager previous = Interlocked.Exchange(ref _memoryManager, memoryManager);
            if (previous != null)
            {
                previous.MemoryUnmapped -= MemoryUnmappedHandler;
                previous.DetachFromChannel(BufferManager.Rebind);
            }''')
    once(channel, '            _device.PushHostCommandBuffer(_processor, commandBuffer);',
         '''            lock (_submissionGate)
            {
                ObjectDisposedException.ThrowIf(_retiring, this);
                _device.PushHostCommandBuffer(_processor, commandBuffer);
            }''')
    once(channel, '            _device.PushEntries(_processor, entries);',
         '''            lock (_submissionGate)
            {
                ObjectDisposedException.ThrowIf(_retiring, this);
                _device.PushEntries(_processor, entries);
            }''')
    once(channel, '''        public void Dispose()
        {
            GC.SuppressFinalize(this);
            _context.DeferredActions.Enqueue(Destroy);''',
         '''        public void Dispose() => Retire(null);

        public void Retire(Action onRetired)
        {
            lock (_submissionGate)
            {
                if (_retiring)
                {
                    return;
                }

                _retiring = true;
                _onRetired = onRetired;
                // A deferred action would run ahead of entries already submitted by
                // this channel. Its memory must stay bound until their FIFO marker.
                _device.RetireChannel(_processor);
            }
            GC.SuppressFinalize(this);''')
    once(channel, '''        private void Destroy()
        {
            _processor.Dispose();
            TextureManager.Dispose();

            MemoryManager oldMemoryManager = Interlocked.Exchange(ref _memoryManager, null);
            if (oldMemoryManager != null)
            {
                oldMemoryManager.Physical.BufferCache.NotifyBuffersModified -= BufferManager.Rebind;
                oldMemoryManager.Physical.DecrementReferenceCount();
                oldMemoryManager.MemoryUnmapped -= MemoryUnmappedHandler;
            }
        }''',
         '''        internal void DestroyRetiredChannel()
        {
            // Accepted command buffers may have left an async report before
            // incrementing one of this channel's syncpoints.
            if (_onRetired != null && _context.HasQueuedSyncpoints)
            {
                try
                {
                    _context.DrainQueuedSyncpoints();
                }
                catch
                {
                    // Final disposal cancels queued reports before running
                    // deferred destruction, even after a render failure.
                    _context.DeferredActions.Enqueue(DestroyResources);
                    throw;
                }
            }

            DestroyResources();
        }

        private void DestroyResources()
        {
            try
            {
                _processor.Dispose();
                TextureManager.Dispose();
            }
            finally
            {
                MemoryManager previous = Interlocked.Exchange(ref _memoryManager, null);
                if (previous != null)
                {
                    previous.MemoryUnmapped -= MemoryUnmappedHandler;
                    previous.DetachFromChannel(BufferManager.Rebind);
                }
                _onRetired?.Invoke();
                _onRetired = null;
            }
        }''')
    once(processor, '        public MemoryManager MemoryManager => _channel.MemoryManager;',
         '''        public MemoryManager MemoryManager => _channel.MemoryManager;

        internal void DestroyRetiredChannel() => _channel.DestroyRetiredChannel();''')
    once(device, '''            Prefetch,
            NoPrefetch,''',
         '''            Prefetch,
            NoPrefetch,
            RetireChannel,''')
    once(device, '''            private readonly ReadOnlySpan<int> GetWords(MemoryManager memoryManager, bool flush)
            {
                return MemoryMarshal.Cast<byte, int>(memoryManager.GetSpan(EntryAddress, (int)EntryCount * 4, flush));
            }''',
         '''            private readonly ReadOnlyRegion GetWords(MemoryManager memoryManager, bool flush)
            {
                return memoryManager.GetReadOnlyRegion(EntryAddress, (int)EntryCount * sizeof(int), flush);
            }''')
    once(device, '''            public readonly ReadOnlySpan<int> Fetch(MemoryManager memoryManager, bool flush)
            {
                return Words != null ? new ReadOnlySpan<int>(Words, 0, (int)EntryCount) : GetWords(memoryManager, flush);
            }''',
         '''            public readonly ReadOnlyRegion Fetch(MemoryManager memoryManager, bool flush)
            {
                return Words != null
                    ? new ReadOnlyRegion(MemoryMarshal.AsBytes(Words.AsSpan(0, (int)EntryCount)))
                    : GetWords(memoryManager, flush);
            }''')
    once(device, '''                    ReadOnlySpan<int> words = entry.Fetch(entry.Processor.MemoryManager, flushCommandBuffer);''',
         '''                    using var fetched = entry.Fetch(entry.Processor.MemoryManager, flushCommandBuffer);
                    ReadOnlySpan<int> words = MemoryMarshal.Cast<byte, int>(fetched.Span);''')
    once(device, '''        // RewindBox (adapt_forced_syncpoint_wait): command buffers not yet taken by the GPU thread.''',
         '''        internal void RetireChannel(GPFifoProcessor processor)
        {
            _commandBufferQueue.Enqueue(new CommandBuffer { Processor = processor, Type = CommandBufferType.RetireChannel });
            SignalNewEntries();
        }

        // RewindBox (adapt_forced_syncpoint_wait): command buffers not yet taken by the GPU thread.''')
    once(device, '''                _context.NoteCommandBufferStarted();

                bool flushCommandBuffer''',
         '''                if (entry.Type == CommandBufferType.RetireChannel)
                {
                    if (_prevChannelProcessor == entry.Processor)
                    {
                        _prevChannelProcessor = null;
                    }
                    entry.Processor.DestroyRetiredChannel();
                    continue;
                }

                _context.NoteCommandBufferStarted();

                bool flushCommandBuffer''')
    once(device, '''            if (!_commandBufferQueue.IsEmpty) return true;
            using var waitMeasurement''',
         '''            if (!_commandBufferQueue.IsEmpty || !_context.DeferredActions.IsEmpty) return true;
            if (GpuContext.PaceStrictHostSyncs && _context.Window.IsFrameAvailable) return false;
            using var waitMeasurement''')
    once(device, '''            // Process command buffers.
            while (_ibEnable''',
         '''            // A saturated FIFO should still let the render loop present a ready image.
            // Yield between entries, never inside a guest command buffer or retirement.
            bool presentDuringBacklog = GpuContext.PaceStrictHostSyncs;
            int entriesSincePresentCheck = 0;
            while (_ibEnable''')
    once(device, '''                finally
                {
                    if (entry.PooledWords)
                    {
                        _wordPool.Return(entry.Words);
                    }
                }
            }

            _interrupt = false;''',
         '''                finally
                {
                    if (entry.PooledWords)
                    {
                        _wordPool.Return(entry.Words);
                    }
                }

                if (presentDuringBacklog && (++entriesSincePresentCheck & 31) == 0 && _context.Window.IsFrameAvailable)
                {
                    break;
                }
            }

            _interrupt = false;''')
    once(window, 'public bool IsFrameAvailable => _framesAvailable != 0;',
         'public bool IsFrameAvailable => Volatile.Read(ref _framesAvailable) != 0;')
    once(device, '''                if (entry.PooledWords)
                {
                    _wordPool.Return(entry.Words);
                }
            }

            _event.Dispose();''',
         '''                if (entry.Type == CommandBufferType.RetireChannel)
                {
                    // At session disposal the guest and FIFO consumer have stopped.
                    // Relinquish the channel through the existing renderer cleanup.
                    _context.DeferredActions.Enqueue(entry.Processor.DestroyRetiredChannel);
                }
                else if (entry.PooledWords)
                {
                    _wordPool.Return(entry.Words);
                }
            }

            _prevChannelProcessor = null;
            _event.Dispose();''')
    once(nv_channel, '        private NvFence _channelSyncpoint;',
         '''        private NvFence _channelSyncpoint;
        private readonly object _submitGate = new();
        private bool _closed;''')
    once(nv_channel, '''        protected NvInternalResult SubmitGpfifo(ref SubmitGpfifoArguments header, Span<ulong> entries)
        {
            if (header.Flags''',
         '''        protected NvInternalResult SubmitGpfifo(ref SubmitGpfifoArguments header, Span<ulong> entries)
        {
            lock (_submitGate)
            {
                if (_closed)
                {
                    return NvInternalResult.BadFileNumber;
                }

                // The optional host wait, guest entries and host fence increment
                // must all precede retirement when a close races this ioctl.
                return SubmitGpfifoLocked(ref header, entries);
            }
        }

        private NvInternalResult SubmitGpfifoLocked(ref SubmitGpfifoArguments header, Span<ulong> entries)
        {
            if (header.Flags''')
    once(nv_channel, '''        public override void Close()
        {
            _host1xContext.Host1x.DestroyContext(_contextId);''',
         '''        public override void Close()
        {
            lock (_submitGate)
            {
                if (_closed)
                {
                    return;
                }
                _closed = true;
            }

            _host1xContext.Host1x.DestroyContext(_contextId);''')
    once(nv_channel, '''            Channel.Dispose();

            for (int i = 0; i < MaxModuleSyncpoint; i++)''',
         '''            Channel.Retire(ReleaseChannelSyncpoints);
        }

        private void ReleaseChannelSyncpoints()
        {
            for (int i = 0; i < MaxModuleSyncpoint; i++)''')
    once(nv_channel, '''            if (ChannelSyncpoints[index] != 0)
            {
                return ChannelSyncpoints[index];
            }

            ChannelSyncpoints[index] = _device.System.HostSyncpoint.AllocateSyncpoint(isClientManaged);

            return ChannelSyncpoints[index];''',
         '''            lock (_submitGate)
            {
                if (_closed)
                {
                    return 0;
                }

                if (ChannelSyncpoints[index] == 0)
                {
                    ChannelSyncpoints[index] = _device.System.HostSyncpoint.AllocateSyncpoint(isClientManaged);
                }

                return ChannelSyncpoints[index];
            }''')
    once(memory, '''            physicalMemory.IncrementReferenceCount();
            physicalMemory.BufferCache.NotifyBuffersModified += rebind;
            physicalMemory.BufferCache.QueuePrune();''',
         '''            physicalMemory.AcquireChannel();
            physicalMemory.BufferCache.NotifyBuffersModified += rebind;''')
    once(memory, '''            physicalMemory.BufferCache.NotifyBuffersModified -= rebind;
            physicalMemory.DecrementReferenceCount();''',
         '''            physicalMemory.BufferCache.NotifyBuffersModified -= rebind;
            physicalMemory.ReleaseChannel();''')
    once(physical, '''        private int _referenceCount;''',
         '''        private int _referenceCount;
        private readonly object _channelGate = new();
        private int _boundChannels;
        private bool _disposeRequested;''')
    once(physical, '''        public void Dispose()
        {
            // Process unregistration can race GpuContext.Dispose when the guest
            // stops while the render worker is live. Destroy exactly once.
            if (Interlocked.Exchange(ref _disposeRequested, 1) == 0)
            {
                _context.DeferredActions.Enqueue(Destroy);
            }
        }

        private int _disposeRequested;''',
         '''        internal void AcquireChannel()
        {
            lock (_channelGate)
            {
                ObjectDisposedException.ThrowIf(_disposeRequested, this);
                _boundChannels++;
                IncrementReferenceCount();
            }
        }

        internal void ReleaseChannel()
        {
            lock (_channelGate)
            {
                DecrementReferenceCount();
                if (--_boundChannels == 0 && _disposeRequested)
                {
                    _context.DeferredActions.Enqueue(Destroy);
                }
            }
        }

        public void Dispose()
        {
            // Unregistration can precede the GPU's last read from a channel.
            // The registry reference and its caches survive every FIFO lease.
            lock (_channelGate)
            {
                if (_disposeRequested)
                {
                    return;
                }
                _disposeRequested = true;
                if (_boundChannels == 0)
                {
                    _context.DeferredActions.Enqueue(Destroy);
                }
            }
        }''')
    return [channel, device, processor, nv_channel, window, memory, physical]
