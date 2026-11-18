"""Reduce render-side synchronization and descriptor work on the Hogwarts route."""

import hashlib

from adapt_session import once


GPU = 'src/Ryujinx.Graphics.Gpu/'
GAL = 'src/Ryujinx.Graphics.GAL/Multithreading/'
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
CONTEXT = GPU + 'GpuContext.cs'
SYNCS = VULKAN + 'SyncManager.cs'
DESCRIPTORS = VULKAN + 'DescriptorSetUpdater.cs'
RENDERER = GAL + 'ThreadedRenderer.cs'
TEXTURE = GAL + 'Resources/ThreadedTexture.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'

BASELINE = {'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ThreadedTexture.cs': 'cda37819ccf791403e5a93e5138caa9c396043b17290d1f7f43d6f222230692e',
 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs': 'a7f90f056bef072f105dacb1658b8f9921abc3393237d6441d5bf19f991f91a0',
 'src/Ryujinx.Graphics.Gpu/GpuContext.cs': 'ecfa654802e7a4c6f81edc766caf34556a99e3ec17a3a086aa7c588cc2d67304',
 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs': '41547c7d9832cd24003656f2b48ef1d55cea64d21f15c3ce549836f178e27296',
 'src/Ryujinx.Graphics.Vulkan/SyncManager.cs': '4927c3c53aab2d89f108aa1c60dc7854734080e92a4d91997e1882b9a9989fb1',
 'src/Ryujinx.Library/Library.cs': 'ea0f7af448cae5d4e6c88c9fbd47a70e0256c070301dae252e68db6f559a627c'}


def reduce_report_submissions(path):
    once(path, '        private const double QueuedSyncpointMaxAgeMs = 50;',
         '''        private const double QueuedSyncpointMaxAgeMs = 50;
        private const double ReportSubmitIntervalMs = 4;
        private long _lastStrictSubmission;
        private long _deferredReportSince;''')
    once(path, '''            // Submitted as the blocking path submits, without waiting for the renderer or the reports.
            // RewindBox (adapt_queued_3d_syncpoints): with no report pending the sync is the call site's own, so the 3D
            // engine's increment ("IncrementSyncpoint") is paced by StrictSyncPacer as when it is not queued, and counted
            // under its site; the forced sync of pending reports is never paced ("queued syncpoints").
            if (pending)
            {
                CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint | HostSyncFlags.Force);
            }
            else
            {
                CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint, site);
            }
            List<DeferredCounterReport> reports = new();
            foreach (var cache in _counterReportCaches) reports.AddRange(cache.TakePendingReports());
            _counterReportCaches.Clear();
            _queuedSyncpoints.Enqueue((syncpoint, reports.ToArray(), System.Diagnostics.Stopwatch.GetTimestamp()));''',
         '''            if (pending)
            {
                long now = System.Diagnostics.Stopwatch.GetTimestamp();
                bool recentlySubmitted = PaceStrictHostSyncs && _lastStrictSubmission != 0 &&
                    System.Diagnostics.Stopwatch.GetElapsedTime(_lastStrictSubmission, now).TotalMilliseconds < ReportSubmitIntervalMs;
                CreateHostSyncIfNeeded(HostSyncFlags.Force |
                    (recentlySubmitted ? HostSyncFlags.Syncpoint : HostSyncFlags.StrictSyncpoint));
                if (recentlySubmitted && _deferredReportSince == 0)
                {
                    _deferredReportSince = now;
                }
            }
            else
            {
                CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint, site);
            }

            // The usual one-cache batch already owns an array. A syncpoint with
            // no new reports requires no allocation for its dependency list.
            DeferredCounterReport[] reports = Array.Empty<DeferredCounterReport>();
            List<DeferredCounterReport> multipleBatches = null;
            foreach (var cache in _counterReportCaches)
            {
                var batch = cache.TakePendingReports();
                if (batch.Length == 0)
                {
                    continue;
                }
                if (reports.Length == 0)
                {
                    reports = batch;
                }
                else
                {
                    (multipleBatches ??= new(reports)).AddRange(batch);
                }
            }
            _counterReportCaches.Clear();
            _queuedSyncpoints.Enqueue((syncpoint, multipleBatches?.ToArray() ?? reports,
                System.Diagnostics.Stopwatch.GetTimestamp()));''')
    once(path, '''        internal void ProcessQueuedSyncpoints()
        {
            bool submitted = false;''',
         '''        internal void ProcessQueuedSyncpoints()
        {
            SubmitDeferredReports(demanded: false);
            bool submitted = false;''')
    once(path, '''            if (submitted) return;
            Renderer.BackgroundContextAction(static () => { });
            submitted = true;
        }

        // Leaves the entry at the head:''',
         '''            if (submitted) return;
            SubmitDeferredReports(demanded: true);
            Renderer.BackgroundContextAction(static () => { });
            submitted = true;
        }

        private void SubmitDeferredReports(bool demanded)
        {
            if (_deferredReportSince != 0 && (demanded ||
                System.Diagnostics.Stopwatch.GetElapsedTime(_deferredReportSince).TotalMilliseconds >= ReportSubmitIntervalMs))
            {
                // A guest demand or the bounded fallback submits before any
                // blocking query read. Publication order remains the FIFO's.
                CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint | HostSyncFlags.Force,
                    nameof(QueueSyncpointBehindReports));
            }
        }

        // Leaves the entry at the head:''')
    once(path, '''                Renderer.CreateSync(SyncNumber, strict);

                SyncNumber++;''',
         '''                Renderer.CreateSync(SyncNumber, strict);
                if (strict && PaceStrictHostSyncs)
                {
                    _lastStrictSubmission = System.Diagnostics.Stopwatch.GetTimestamp();
                    _deferredReportSince = 0;
                }

                SyncNumber++;''')


def index_sync_handles(path):
    once(path, '''        private readonly Queue<SyncHandle> _handles;''',
         '''        private readonly Queue<SyncHandle> _handles;
        private readonly Dictionary<ulong, SyncHandle> _handlesById = new();''')
    once(path, '''                _handles.Enqueue(handle);''',
         '''                _handlesById.Add(id, handle);
                _handles.Enqueue(handle);''')
    once(path, '''                foreach (SyncHandle handle in _handles)
                {
                    if (handle.ID == id)
                    {
                        result = handle;
                        break;
                    }
                }''',
         '''                _handlesById.TryGetValue(id, out result);''')
    once(path, '''                            _handles.Dequeue();
                            Array.Clear(first.Waitable.Fences);''',
         '''                            _handles.Dequeue();
                            _handlesById.Remove(first.ID);
                            Array.Clear(first.Waitable.Fences);''')
    once(path, '''            _flushId++;''',
         '''            System.Threading.Interlocked.Increment(ref _flushId);''')
    once(path, '''            ulong flushId = _flushId;''',
         '''            ulong flushId = System.Threading.Volatile.Read(ref _flushId);''')
    once(path, '''                if (result.NeedsFlush(_flushId))''',
         '''                if (result.NeedsFlush(System.Threading.Volatile.Read(ref _flushId)))''')
    once(path, '''                if (handle.NeedsFlush(_flushId))''',
         '''                if (handle.NeedsFlush(System.Threading.Volatile.Read(ref _flushId)))''')
    once(path, '''                        _waitTicks += Stopwatch.GetTimestamp() - beforeTicks;''',
         '''                        System.Threading.Interlocked.Add(ref _waitTicks, Stopwatch.GetTimestamp() - beforeTicks);''')
    once(path, '''            long result = _waitTicks;
            _waitTicks = 0;

            return result;''',
         '''            return System.Threading.Interlocked.Exchange(ref _waitTicks, 0);''')


def keep_compatible_buffer_descriptors(path):
    once(path, '''            // The exact same layout, bind point and scalar texture bindings can
            // keep their set. Leave array-dependent and dynamic buffer views on the
            // existing update path, and retain any invalidation already pending.''',
         '''            // Matching layouts and binding segments can retain their sets.
            // Array-dependent textures and dynamic buffer views still update.''')
    once(path, '''            bool keepTextures = EncodingPolicy.IncrementalArrayDescriptors && isBound && sameLayout &&
                program.IsCompute == _program.IsCompute &&
                !program.UpdateTexturesWithoutTemplate && !_program.UpdateTexturesWithoutTemplate &&
                SameScalarTextureBindings(program, _program);
            _program = program;
            _updateDescriptorCacheCbIndex = true;
            _dirty |= keepTextures ? DirtyFlags.All & ~DirtyFlags.Texture : DirtyFlags.All;''',
         '''            DirtyFlags changed = DirtyFlags.All;
            if (EncodingPolicy.IncrementalArrayDescriptors && isBound && sameLayout && program.IsCompute == _program.IsCompute)
            {
                if (!program.UpdateTexturesWithoutTemplate && !_program.UpdateTexturesWithoutTemplate &&
                    SameBindings(program, _program, PipelineBase.TextureSetIndex, scalarTextures: true))
                {
                    changed &= ~DirtyFlags.Texture;
                }
                if (program.UsePushDescriptors == _program.UsePushDescriptors &&
                    SameBindings(program, _program, PipelineBase.UniformSetIndex))
                {
                    changed &= ~DirtyFlags.Uniform;
                }
                if (SameBindings(program, _program, PipelineBase.StorageSetIndex))
                {
                    changed &= ~DirtyFlags.Storage;
                }
            }

            _program = program;
            _updateDescriptorCacheCbIndex = true;
            // Setters and buffer migrations may have marked these sets dirty
            // already. Compatible layouts never clear a pending invalidation.
            _dirty |= changed;''')
    once(path, '''        private static bool SameScalarTextureBindings(ShaderCollection program, ShaderCollection previous)
        {
            ResourceBindingSegment[] current = program.BindingSegments[PipelineBase.TextureSetIndex];
            ResourceBindingSegment[] prior = previous.BindingSegments[PipelineBase.TextureSetIndex];''',
         '''        private static bool SameBindings(ShaderCollection program, ShaderCollection previous, int setIndex, bool scalarTextures = false)
        {
            ResourceBindingSegment[] current = program.BindingSegments[setIndex];
            ResourceBindingSegment[] prior = previous.BindingSegments[setIndex];
            return SameSegments(current, prior, scalarTextures) &&
                SameSegments(program.ClearSegments[setIndex], previous.ClearSegments[setIndex], false);
        }

        private static bool SameSegments(ResourceBindingSegment[] current, ResourceBindingSegment[] prior, bool scalarTextures)
        {''')
    once(path, '''                if (a.IsArray || b.IsArray || a.Type == ResourceType.BufferTexture ||
                    a.Binding != b.Binding || a.Count != b.Count || a.Type != b.Type || a.Stages != b.Stages)''',
         '''                if (a.Binding != b.Binding || a.Count != b.Count || a.Type != b.Type || a.Stages != b.Stages ||
                    a.IsArray != b.IsArray || (scalarTextures && (a.IsArray || a.Type == ResourceType.BufferTexture)))''')


def reduce_repeated_texture_storage(renderer, texture, library):
    once(renderer, '''        public unsafe void DeleteBuffer(BufferHandle buffer)
        {
            New<BufferDisposeCommand>()->Set(buffer);''',
         '''        public bool CoalesceTextureStorage { get; set; }
        internal ulong BufferDeletionEpoch { get; private set; }

        public unsafe void DeleteBuffer(BufferHandle buffer)
        {
            if (CoalesceTextureStorage)
            {
                BufferDeletionEpoch++;
            }
            New<BufferDisposeCommand>()->Set(buffer);''')
    once(texture, '''        public ITexture Base;''',
         '''        public ITexture Base;
        private BufferRange _boundStorage;
        private ulong _boundStorageEpoch;
        private bool _hasBoundStorage;''')
    once(texture, '''        public unsafe void SetStorage(BufferRange buffer)
        {
            _renderer.New<TextureSetStorageCommand>()->Set(Ref(this), buffer);
            _renderer.QueueCommand();
        }''',
         '''        public unsafe void SetStorage(BufferRange buffer)
        {
            if (_renderer.CoalesceTextureStorage && _info.Target == Target.TextureBuffer)
            {
                // Logical handles are unique within this renderer. Any queued
                // deletion invalidates the shortcut before a stale request
                // could retain a previous backend buffer view.
                ulong epoch = _renderer.BufferDeletionEpoch;
                if (_hasBoundStorage && _boundStorageEpoch == epoch && _boundStorage.Handle == buffer.Handle &&
                    _boundStorage.Offset == buffer.Offset && _boundStorage.Size == buffer.Size && _boundStorage.Write == buffer.Write)
                {
                    return;
                }
                _boundStorage = buffer;
                _boundStorageEpoch = epoch;
                _hasBoundStorage = true;
            }

            _renderer.New<TextureSetStorageCommand>()->Set(Ref(this), buffer);
            _renderer.QueueCommand();
        }''')
    once(texture, '''        public unsafe void Release()
        {
            _renderer.New<TextureReleaseCommand>()->Set(Ref(this));''',
         '''        public unsafe void Release()
        {
            _hasBoundStorage = false;
            _renderer.New<TextureReleaseCommand>()->Set(Ref(this));''')
    once(library, '''            renderer = renderer.TryMakeThreaded(options.BackendThreading);''',
         '''            renderer = renderer.TryMakeThreaded(options.BackendThreading);
            if (renderer is Ryujinx.Graphics.GAL.Multithreading.ThreadedRenderer threaded)
            {
                threaded.CoalesceTextureStorage = hogwarts;
            }''')


def reduce_render_queue_atomics(path):
    once(path, '        private int _invokePtr;', '        private int _invokePtr = -1;')
    once(path, '                    if (Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr)',
         '''                    if (Volatile.Read(ref _invokePtr) == commandPtr &&
                        Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr)''')
    once(path, '''                using (PD.Measure(PD.Phase.RenderDrain))
                while (Volatile.Read(ref _commandCount) > 0 && Volatile.Read(ref _interruptAction) == null)''',
         '''                // Only this consumer retires commands. Keep a conservative published count until
                // this bounded batch completes. The ring cursor still releases each executed slot.
                int remaining = Volatile.Read(ref _commandCount);
                int retired = 0;
                using (PD.Measure(PD.Phase.RenderDrain))
                while (remaining > 0 && Volatile.Read(ref _interruptAction) == null)''')
    once(path, '''                    _consumerPtr = (_consumerPtr + 1) % QueueCount;
                    Volatile.Write(ref _completedCommands, _completedCommands + 1);

                    Interlocked.Decrement(ref _commandCount);
                }''',
         '''                    Volatile.Write(ref _consumerPtr, (_consumerPtr + 1) % QueueCount);
                    Volatile.Write(ref _completedCommands, _completedCommands + 1);

                    retired++;
                    if (--remaining == 0 || retired == 32)
                    {
                        // The returned count includes anything the producer published during the batch.
                        remaining = Interlocked.Add(ref _commandCount, -retired);
                        retired = 0;
                    }
                }

                if (retired != 0)
                {
                    // An interrupt ended the drain early. The interrupt wake is already pending.
                    Interlocked.Add(ref _commandCount, -retired);
                }''')


def apply(source):
    for name, digest in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest, name

    reduce_report_submissions(source / CONTEXT)
    index_sync_handles(source / SYNCS)
    keep_compatible_buffer_descriptors(source / DESCRIPTORS)
    reduce_repeated_texture_storage(source / RENDERER, source / TEXTURE, source / LIBRARY)
    reduce_render_queue_atomics(source / RENDERER)
    return [source / name for name in (CONTEXT, SYNCS, DESCRIPTORS, RENDERER, TEXTURE, LIBRARY)]
