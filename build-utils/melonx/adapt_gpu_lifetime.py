"""GPU texture/cache teardown boundaries for embedded MeloNX sessions.

Super Smash Bros. Ultimate, 25 October 2026 (Build 54x): after the guest had
stopped, the render worker's single GpuContext.Dispose ran
PhysicalMemory.Destroy -> TextureCache.Dispose and a listed texture released
an already-disposed RegionHandle. BufferCache.Dispose had just succeeded, so
Destroy did not run twice: a texture listed in TextureCache had already been
released. The worker failed, the session was quarantined and its 4 GiB donor
lease retained. Upstream desktop hosts usually exit the process here; the
embedded host must survive the same teardown.

- MeloNX 2.6 replaced the upstream single eviction (32-texture floor) with a
  loop that can evict the texture currently being added or lifted. A new
  texture is added to the auto-delete cache before TextureCache lists it:
  evicting it disposes it, then it is listed, returned, used and released
  again at teardown. Never evict the texture the caller still owns.
- Teardown releases each texture/group exactly once and still attempts every
  cache, the CPU memory reference and the renderer if one step fails.
- RewindBox terminates the guest while the render worker still runs. Guest and
  HLE threads enqueue deferred GPU actions concurrently with the render thread;
  use a concurrent queue and enqueue PhysicalMemory destruction only once.
Fail closed on upstream drift.
"""
from adapt_session import once


def apply(source):
    gpu = source / 'src/Ryujinx.Graphics.Gpu'
    cache = gpu / 'Image/AutoDeleteCache.cs'
    texture = gpu / 'Image/Texture.cs'
    group = gpu / 'Image/TextureGroup.cs'
    texture_cache = gpu / 'Image/TextureCache.cs'
    physical = gpu / 'Memory/PhysicalMemory.cs'
    context = gpu / 'GpuContext.cs'

    once(cache, '''            texture.IncrementReferenceCount();
            texture.CacheNode = _textures.AddLast(texture);

            EnforceCapacity();''', '''            texture.IncrementReferenceCount();
            texture.CacheNode = _textures.AddLast(texture);

            EnforceCapacity(texture);''')
    once(cache, '''                    _textures.AddLast(texture.CacheNode);
                }

                EnforceCapacity();''', '''                    _textures.AddLast(texture.CacheNode);
                }

                EnforceCapacity(texture);''')
    once(cache, '''        private void EnforceCapacity()
        {
            while (_textures.Count > MaxCapacity ||
                   (_totalSize > _maxCacheMemoryUsage && _textures.Count > 0))
            {
                RemoveLeastUsedTexture();
            }
        }''', '''        /// <param name="protectedTexture">Texture being added or lifted, still owned by its caller</param>
        private void EnforceCapacity(Texture protectedTexture)
        {
            while (_textures.Count > MaxCapacity ||
                   (_totalSize > _maxCacheMemoryUsage && _textures.Count > 0))
            {
                // It is the newest entry. Reaching it means only it remains; a
                // new texture is not listed by TextureCache yet, so evicting it
                // would dispose a texture that is then listed and used.
                if (_textures.First.Value == protectedTexture)
                {
                    if (!_protectedOverflowReported)
                    {
                        _protectedOverflowReported = true;
                        Logger.Warning?.Print(LogClass.Gpu,
                            $"Texture cache kept its texture in use above the {_maxCacheMemoryUsage / MiB} MiB share ({_totalSize / MiB} MiB) instead of releasing it.");
                    }

                    break;
                }

                RemoveLeastUsedTexture();
            }
        }

        private bool _protectedOverflowReported;''')

    once(texture, '''        private int _referenceCount;
        private List<TexturePoolOwner> _poolOwners;''', '''        private int _referenceCount;
        private List<TexturePoolOwner> _poolOwners;
        private bool _disposed;

        /// <summary>
        /// Whether the host texture and owned tracking handles were already released.
        /// </summary>
        public bool IsDisposed => _disposed;''')
    once(texture, '''        public void Dispose()
        {
            DisposeTextures();

            if (Group.Storage == this)''', '''        public void Dispose()
        {
            // The last reference and TextureCache teardown can both reach a
            // texture that stayed listed. Release its resources exactly once.
            if (_disposed)
            {
                return;
            }

            _disposed = true;

            DisposeTextures();

            if (Group.Storage == this)''')

    once(group, '''        public void Dispose()
        {
            foreach (TextureGroupHandle group in _handles)
            {
                group.Dispose();
            }''', '''        public void Dispose()
        {
            // A group is released by its storage texture, or when it becomes a
            // view of another storage. Never release its tracking handles twice.
            if (_disposed)
            {
                return;
            }

            _disposed = true;

            foreach (TextureGroupHandle group in _handles)
            {
                group.Dispose();
            }''')
    once(group, '''        public Texture Storage { get; }
''', '''        public Texture Storage { get; }

        private bool _disposed;
''')

    once(texture_cache, '''            _texturesLock.EnterReadLock();

            try
            {
                foreach (Texture texture in _textures)
                {
                    texture.Dispose();
                }
            }
            finally
            {
                _texturesLock.ExitReadLock();
            }
        }''', '''            int released = 0;
            int stale = 0;

            _texturesLock.EnterReadLock();

            try
            {
                foreach (Texture texture in _textures)
                {
                    if (texture.IsDisposed)
                    {
                        released++;
                        continue;
                    }

                    try
                    {
                        texture.Dispose();
                    }
                    catch (ObjectDisposedException)
                    {
                        // Teardown runs after the guest and render loop stopped.
                        // A tracking handle already released by another owner
                        // throws before changing state; keep releasing the rest.
                        stale++;
                    }
                }
            }
            finally
            {
                _texturesLock.ExitReadLock();
            }

            if (released != 0 || stale != 0)
            {
                Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu,
                    $"Texture cache teardown skipped {released} texture(s) already released while still listed and {stale} stale tracking handle owner(s).");
            }
        }''')

    once(physical, '''        public void Dispose()
        {
            _context.DeferredActions.Enqueue(Destroy);
        }''', '''        public void Dispose()
        {
            // Process unregistration can race GpuContext.Dispose when the guest
            // stops while the render worker is live. Destroy exactly once.
            if (Interlocked.Exchange(ref _disposeRequested, 1) == 0)
            {
                _context.DeferredActions.Enqueue(Destroy);
            }
        }

        private int _disposeRequested;''')
    once(physical, '''        private void Destroy()
        {
            ShaderCache.Dispose();
            BufferCache.Dispose();
            TextureCache.Dispose();

            DecrementReferenceCount();
        }''', '''        private void Destroy()
        {
            // Attempt every cache and always release the CPU memory reference,
            // so one host cache error cannot strand guest memory. The error
            // still propagates to the session owner.
            try
            {
                ShaderCache.Dispose();
            }
            finally
            {
                try
                {
                    BufferCache.Dispose();
                }
                finally
                {
                    try
                    {
                        TextureCache.Dispose();
                    }
                    finally
                    {
                        DecrementReferenceCount();
                    }
                }
            }
        }''')

    once(context, '        internal Queue<Action> DeferredActions { get; }',
         '''        /// <remarks>
        /// Guest and HLE threads enqueue while the render thread drains it.
        /// </remarks>
        internal ConcurrentQueue<Action> DeferredActions { get; }''')
    once(context, '            DeferredActions = new Queue<Action>();',
         '            DeferredActions = new ConcurrentQueue<Action>();')
    once(context, '''            PhysicalMemoryRegistry.Clear();

            RunDeferredActions();

            Renderer.Dispose();
        }''', '''            PhysicalMemoryRegistry.Clear();

            // One release attempt: run every queued destruction and dispose the
            // renderer even if one of them fails, then report the first error.
            List<Exception> errors = null;

            while (DeferredActions.TryDequeue(out Action action))
            {
                try
                {
                    action();
                }
                catch (Exception error)
                {
                    (errors ??= []).Add(error);
                }
            }

            try
            {
                Renderer.Dispose();
            }
            catch (Exception error)
            {
                (errors ??= []).Add(error);
            }

            if (errors != null)
            {
                if (errors.Count == 1)
                {
                    System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(errors[0]).Throw();
                }

                throw new AggregateException(errors);
            }
        }''')
    return [cache, texture, group, texture_cache, physical, context]
