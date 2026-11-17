"""Keep every Vulkan descriptor pool alive until its owner and all issued sets have released it."""
import hashlib

from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetManager.cs'
BASELINE = {MANAGER: '81172287a6bfac179eac0d241feef5f06828daecec7be2191ac3320fb99a62b5'}


def apply(source):
    path = source / MANAGER
    for name, expected in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name

    once(path, 'using System.Diagnostics;', 'using System.Diagnostics;\nusing System.Threading;')
    once(path, '''            private int _setsInUse;
            private bool _done;''', '''            // One reference for the manager plus one per allocated descriptor set.
            // A command buffer may release its last set concurrently with pool retirement.
            private int _references = 1;
            private int _retired;''')
    once(path, '                Debug.Assert(!_done);', '                Debug.Assert(Volatile.Read(ref _retired) == 0);')
    once(path, '''                            _totalSets = (int)MaxSets;
                            _done = true;
                            DestroyIfDone();''', '''                            Retire();''')
    once(path, '                _setsInUse += layouts.Length;', '                Interlocked.Add(ref _references, layouts.Length);')
    once(path, '''                _setsInUse -= dsc.SetsCount;
                Debug.Assert(_setsInUse >= 0);
                DestroyIfDone();''', '''                ReleaseReferences(dsc.SetsCount);''')
    once(path, '''                if (_totalSets + setsCount <= MaxSets && _freeDescriptors >= descriptorsCount)''', '''                if (Volatile.Read(ref _retired) != 0)
                {
                    return false;
                }

                if (_totalSets + setsCount <= MaxSets && _freeDescriptors >= descriptorsCount)''')
    once(path, '''                _done = true;
                DestroyIfDone();
                return false;''', '''                Retire();
                return false;''')
    once(path, '''            private unsafe void DestroyIfDone()
            {
                if (_done && _setsInUse == 0)''', '''            private void Retire()
            {
                if (Interlocked.Exchange(ref _retired, 1) == 0)
                {
                    ReleaseReferences(1);
                }
            }

            private unsafe void ReleaseReferences(int count)
            {
                int remaining = Interlocked.Add(ref _references, -count);
                Debug.Assert(remaining >= 0);
                if (remaining == 0)''')
    once(path, '''                    unsafe
                    {
                        Api.DestroyDescriptorPool(Device, _pool, null);
                    }''', '''                    Retire();''')
    once(path, '        private readonly DescriptorPoolHolder[] _currentPools;',
         '        private readonly DescriptorPoolHolder[] _currentPools;\n        private bool _disposed;')
    once(path, '''            DescriptorPoolHolder pool = GetPool(api, poolSizes, poolIndex, layouts.Length, consumedDescriptors, updateAfterBind);
            if (!pool.TryAllocateDescriptorSets(layouts, consumedDescriptors, out DescriptorSetCollection dsc))
            {
                pool = GetPool(api, poolSizes, poolIndex, layouts.Length, consumedDescriptors, updateAfterBind);
                dsc = pool.AllocateDescriptorSets(layouts, consumedDescriptors);
            }

            return new Auto<DescriptorSetCollection>(dsc);''', '''            // Only new native sets enter here. Cached binds and fence releases need no manager lock.
            lock (_currentPools)
            {
                ObjectDisposedException.ThrowIf(_disposed, this);
                DescriptorPoolHolder pool = GetPool(api, poolSizes, poolIndex, layouts.Length, consumedDescriptors, updateAfterBind);
                if (!pool.TryAllocateDescriptorSets(layouts, consumedDescriptors, out DescriptorSetCollection dsc))
                {
                    pool = GetPool(api, poolSizes, poolIndex, layouts.Length, consumedDescriptors, updateAfterBind);
                    dsc = pool.AllocateDescriptorSets(layouts, consumedDescriptors);
                }

                return new Auto<DescriptorSetCollection>(dsc);
            }''')
    once(path, '''                for (int index = 0; index < _currentPools.Length; index++)
                {
                    _currentPools[index]?.Dispose();
                    _currentPools[index] = null;
                }''', '''                lock (_currentPools)
                {
                    _disposed = true;
                    for (int index = 0; index < _currentPools.Length; index++)
                    {
                        _currentPools[index]?.Dispose();
                        _currentPools[index] = null;
                    }
                }''')
    return [path]
