"""Release cold upload arrays and reuse texture comparison snapshots.

The upload pool keeps one array of every encountered length indefinitely; the
existing three-second expiry covers only duplicate spares. Extend that idle
window to the primary arrays, without changing their search/reuse policy,
their contents, the spare budget or the GC configuration. Leased arrays have
left the pool and cannot be released by the timer.

Textures requiring a slow format conversion keep a byte-for-byte guest snapshot
to suppress unchanged uploads. Reuse that private snapshot when its length is
unchanged instead of allocating a new large array on every changed upload.
"""
from adapt_session import once


def adapt_owner(source):
    owner = source / 'src/Ryujinx.Common/Memory/MemoryOwner.cs'
    once(owner, '''            private static Timer? _spareTimer;
''', '''            private static Timer? _spareTimer;
            private static Timer? _arrayTimer;
            private static bool _arrayTrimScheduled;
''')
    once(owner, '''                    holder.SkipCount = 0;
                    int i = _pool.BinarySearch(holder);
''', '''                    holder.SkipCount = 0;
                    holder.Returned = Environment.TickCount64;
                    int i = _pool.BinarySearch(holder);
''')
    once(owner, '''                    if (_pool.Count >= _maxCacheCount)
''', '''                    if (!_arrayTrimScheduled && _pool.Count != 0)
                    {
                        _arrayTrimScheduled = true;
                        (_arrayTimer ??= new Timer(ReleaseIdleArrays)).Change(SpareIdleMilliseconds, Timeout.Infinite);
                    }

                    if (_pool.Count >= _maxCacheCount)
''')
    once(owner, '''            private static void ReleaseIdleSpares(object? state)
''', '''            private static void ReleaseIdleArrays(object? state)
            {
                lock (_lock)
                {
                    long now = Environment.TickCount64;
                    long next = SpareIdleMilliseconds;
                    int writeIndex = 0;

                    for (int index = 0; index < _pool.Count; index++)
                    {
                        Holder holder = _pool[index];
                        long remaining = holder.Returned + SpareIdleMilliseconds - now;

                        if (remaining <= 0 && _sparesByLength.TryGetValue(holder.Array!.Length, out LinkedList<Holder>? spares))
                        {
                            // Keep a more recently returned spare as this length's primary array.
                            Holder newest = spares.Last!.Value;
                            RemoveSpareLocked(newest);
                            holder = newest;
                            remaining = newest.Returned + SpareIdleMilliseconds - now;
                        }

                        if (remaining > 0)
                        {
                            _pool[writeIndex++] = holder;
                            next = Math.Min(next, remaining);
                        }
                    }

                    // Preserve sorted lengths with one linear pass; removing each cold array
                    // separately would repeatedly shift interleaved live entries under the lock.
                    if (writeIndex != _pool.Count)
                    {
                        _pool.RemoveRange(writeIndex, _pool.Count - writeIndex);
                    }

                    _arrayTrimScheduled = _pool.Count != 0;

                    if (_arrayTrimScheduled)
                    {
                        _arrayTimer!.Change(Math.Max(1, next), Timeout.Infinite);
                    }
                }
            }

            private static void ReleaseIdleSpares(object? state)
''')
    return owner


def adapt_texture(source):
    texture = source / 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
    once(texture, '''                    _currentData = data.ToArray();
''', '''                    if (_currentData == null || _currentData.Length != data.Length)
                    {
                        _currentData = new byte[data.Length];
                    }

                    data.CopyTo(_currentData);
''')
    return texture


def apply(source):
    return [adapt_owner(source), adapt_texture(source)]
