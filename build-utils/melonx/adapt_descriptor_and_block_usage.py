"""Keep independent descriptor sets bound and avoid per-allocation range lists for whole blocks."""
import hashlib

from adapt_session import once

UPDATER = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'
BLOCKS = 'src/Ryujinx.Graphics.Vulkan/MemoryAllocatorBlockList.cs'
BASELINE = {
    UPDATER: 'c9d1fce87b1bdee2ad50409695a21c147d90bd6064d797e6cad73be8cc236b31',
    BLOCKS: 'bdd8e37aa7b337afd7c3f99974c9a80d9b98d6e01b07759a94f231251d64315b',
}


def apply(source):
    for name, expected in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name

    updater = source / UPDATER
    once(updater, '''                SignalDirty(DirtyFlags.Image);
            }
        }

        private static ref ArrayRef<T>''', '''                SignalDirty(DirtyFlags.TextureArrayExtra);
            }
        }

        private static ref ArrayRef<T>''')
    once(updater, '''            // RewindBox (adapt_extra_array_dirty): a texture array bound to its own set changed; set 2 did not.''',
         '''            // A texture or image array in its own set changed. Scalar bindings live in other sets.''')
    once(updater, '''                // Program is using extra sets, we need to bind those too.
                // RewindBox (adapt_extra_set_binds): without a texture or image change since their last bind, the array sets
                // bound in this command buffer are still bound and still current.

                // RewindBox (adapt_extra_array_dirty): a separate texture array change binds them again too.
                BindExtraSets(cbs, program, pbp, arraysKept: (_dirty & (DirtyFlags.Texture | DirtyFlags.Image | DirtyFlags.TextureArrayExtra)) == 0);''',
         '''                // Setters for scalar bindings cannot replace an independently bound array. Buffer
                // views may change without a setter and are always visited inside BindExtraSets.
                BindExtraSets(cbs, program, pbp, arraysKept: (_dirty & DirtyFlags.TextureArrayExtra) == 0);''')
    for kind in ('Texture', 'Image'):
        once(updater, f'''        public void Force{kind}Dirty()
        {{
            SignalDirty(DirtyFlags.{kind});''', f'''        public void Force{kind}Dirty()
        {{
            SignalDirty(DirtyFlags.{kind} | DirtyFlags.TextureArrayExtra);''')

    blocks = source / BLOCKS
    once(blocks, 'private readonly List<Range> _freeRanges;', '''// A dedicated allocation normally consumes and returns exactly the whole block.
            // Materialize a range list only if a caller actually subdivides it.
            private List<Range> _freeRanges;
            private bool _wholeRangeFree;''')
    once(blocks, '''                _freeRanges =
                [
                    new(0, size)
                ];''', '''                if (dedicated)
                {
                    _wholeRangeFree = true;
                }
                else
                {
                    _freeRanges = [new(0, size)];
                }''')
    once(blocks, '''                    ulong free = 0;
                    foreach (Range range in _freeRanges)''', '''                    if (_freeRanges == null)
                    {
                        return _wholeRangeFree ? Size : 0;
                    }

                    ulong free = 0;
                    foreach (Range range in _freeRanges)''')
    once(blocks, '''                    for (int i = 0; i < _freeRanges.Count; i++)''', '''                    if (_freeRanges == null)
                    {
                        if (!_wholeRangeFree || Size == 0 || size > Size)
                        {
                            return InvalidOffset;
                        }

                        if (size == Size)
                        {
                            _wholeRangeFree = false;
                            return 0;
                        }

                        _freeRanges = [new(0, Size)];
                    }

                    for (int i = 0; i < _freeRanges.Count; i++)''')
    once(blocks, '''                    InsertFreeRangeComingled(offset, size);''', '''                    if (_freeRanges == null)
                    {
                        if (!_wholeRangeFree && offset == 0 && size == Size)
                        {
                            _wholeRangeFree = true;
                            return;
                        }

                        _freeRanges = _wholeRangeFree ? [new(0, Size)] : [];
                    }

                    InsertFreeRangeComingled(offset, size);''')
    once(blocks, '''                    if (_freeRanges.Count == 1 && _freeRanges[0].Size == Size)''', '''                    if (_freeRanges == null)
                    {
                        return _wholeRangeFree;
                    }

                    if (_freeRanges.Count == 1 && _freeRanges[0].Size == Size)''')
    once(blocks, '        private List<Block> _dedicatedBlocks;', '''        private List<Block> _dedicatedBlocks;
        // Updated under the same list lock as publication and removal. Never take a driver lock to report usage.
        private ulong _dedicatedBytes;
        private ulong _dedicatedMappedBytes;''')
    once(blocks, '''                    foreach (Block block in _dedicatedBlocks)
                    {
                        blocks++;
                        bytes += block.Size;
                        dedicated += block.Size;
                        mapped += block.Mapped ? block.Size : 0;
                    }''', '''                    blocks += (ulong)_dedicatedBlocks.Count;
                    bytes += _dedicatedBytes;
                    dedicated += _dedicatedBytes;
                    mapped += _dedicatedMappedBytes;''')
    once(blocks, '''                _dedicatedBlocks.Add(block);
                return;''', '''                _dedicatedBlocks.Add(block);
                _dedicatedBytes += block.Size;
                _dedicatedMappedBytes += block.Mapped ? block.Size : 0;
                return;''')
    once(blocks, '''                            _dedicatedBlocks.RemoveAt(last);
                            block.DedicatedIndex''', '''                            _dedicatedBlocks.RemoveAt(last);
                            _dedicatedBytes -= block.Size;
                            _dedicatedMappedBytes -= block.Mapped ? block.Size : 0;
                            block.DedicatedIndex''')
    return [updater, blocks]
