"""Track dedicated blocks without sorted-list scans and clean unpublished allocations.

Dedicated native blocks cannot satisfy later suballocations. Keep them in their
own lazily allocated list and update an intrusive index when swap-removing a
retired block, under the same write lock. Pooled and imported ranges retain
all range bookkeeping and synchronization. The ordering among equivalent
pooled blocks can differ because dedicated equal-size entries no longer affect
List.BinarySearch's arbitrary equality position; guest bytes and ownership,
not physical block identity, are the compatibility contract.

A driver allocation becomes owned by the list only after InsertBlock succeeds.
Any mapping or managed setup failure before that publication must unmap (only
if mapping succeeded) and free it. No allocation budget, pool size, fence,
resource retirement, mapping choice or suballocation policy changes.
"""
from adapt_session import once


def apply(source):
    block = source / 'src/Ryujinx.Graphics.Vulkan/MemoryAllocatorBlockList.cs'
    old = '''            nint hostPointer = nint.Zero;

            if (map)
            {
                void* pointer = null;
                _api.MapMemory(_device, deviceMemory, 0, blockSize, 0, ref pointer).ThrowOnError();
                hostPointer = (nint)pointer;
            }

            Block newBlock = new(deviceMemory, hostPointer, blockSize, dedicated);

            // Claim our range before publishing the block, so a concurrent allocation cannot take
            // the space this call already committed to.
            ulong newBlockOffset = newBlock.Allocate(size, alignment);
            Debug.Assert(newBlockOffset != InvalidOffset);

            _lock.EnterWriteLock();

            try
            {
                InsertBlock(newBlock);
            }
            finally
            {
                _lock.ExitWriteLock();
            }

            return new MemoryAllocation(this, newBlock, deviceMemory, GetHostPointer(newBlock, newBlockOffset), newBlockOffset, size);'''
    new = '''            nint hostPointer = nint.Zero;
            bool mapped = false;
            bool published = false;

            try
            {
                if (map)
                {
                    void* pointer = null;
                    _api.MapMemory(_device, deviceMemory, 0, blockSize, 0, ref pointer).ThrowOnError();
                    mapped = true;
                    hostPointer = (nint)pointer;
                }

                Block newBlock = new(deviceMemory, hostPointer, blockSize, dedicated);

                // Claim our range before publishing the block, so a concurrent allocation cannot take
                // the space this call already committed to.
                ulong newBlockOffset = newBlock.Allocate(size, alignment);
                Debug.Assert(newBlockOffset != InvalidOffset);

                _lock.EnterWriteLock();

                try
                {
                    InsertBlock(newBlock);
                    published = true;
                }
                finally
                {
                    _lock.ExitWriteLock();
                }

                return new MemoryAllocation(this, newBlock, deviceMemory, GetHostPointer(newBlock, newBlockOffset), newBlockOffset, size);
            }
            finally
            {
                if (!published)
                {
                    try
                    {
                        if (mapped)
                        {
                            _api.UnmapMemory(_device, deviceMemory);
                        }
                    }
                    finally
                    {
                        _api.FreeMemory(_device, deviceMemory, null);
                    }
                }
            }'''
    once(block, old, new)
    once(block, '            public bool Dedicated { get; }\n',
         '            public bool Dedicated { get; }\n            public int DedicatedIndex { get; set; } = -1;\n')
    once(block, '        private readonly List<Block> _blocks;\n',
         '        private readonly List<Block> _blocks;\n        private List<Block> _dedicatedBlocks;\n')
    once(block, '''                if (block.IsTotallyFree())
                {
                    for (int i = 0; i < _blocks.Count; i++)
                    {
                        if (_blocks[i] == block)
                        {
                            _blocks.RemoveAt(i);
                            destroy = true;
                            break;
                        }
                    }
                }''', '''                if (block.IsTotallyFree())
                {
                    if (block.Dedicated)
                    {
                        int index = block.DedicatedIndex;
                        if (_dedicatedBlocks != null && (uint)index < (uint)_dedicatedBlocks.Count &&
                            _dedicatedBlocks[index] == block)
                        {
                            int last = _dedicatedBlocks.Count - 1;
                            if (index != last)
                            {
                                Block replacement = _dedicatedBlocks[last];
                                _dedicatedBlocks[index] = replacement;
                                replacement.DedicatedIndex = index;
                            }
                            _dedicatedBlocks.RemoveAt(last);
                            block.DedicatedIndex = -1;
                            destroy = true;
                        }
                    }
                    else
                    {
                        for (int i = 0; i < _blocks.Count; i++)
                        {
                            if (_blocks[i] == block)
                            {
                                _blocks.RemoveAt(i);
                                destroy = true;
                                break;
                            }
                        }
                    }
                }''')
    once(block, '''        private void InsertBlock(Block block)
        {
            int index = _blocks.BinarySearch(block);''', '''        private void InsertBlock(Block block)
        {
            if (block.Dedicated)
            {
                _dedicatedBlocks ??= [];
                block.DedicatedIndex = _dedicatedBlocks.Count;
                _dedicatedBlocks.Add(block);
                return;
            }

            int index = _blocks.BinarySearch(block);''')
    once(block, '''        public void Dispose()
        {
            for (int i = 0; i < _blocks.Count; i++)
            {
                _blocks[i].Destroy(_api, _device);
            }
        }''', '''        public void Dispose()
        {
            for (int i = 0; i < _blocks.Count; i++)
            {
                _blocks[i].Destroy(_api, _device);
            }

            if (_dedicatedBlocks != null)
            {
                for (int i = 0; i < _dedicatedBlocks.Count; i++)
                {
                    _dedicatedBlocks[i].Destroy(_api, _device);
                }
            }
        }''')
    return [block]
