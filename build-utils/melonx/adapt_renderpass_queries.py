"""Remove per-query closure allocation from render-pass attachment/barrier checks.

BarrierBatch calls ContainsAttachment for each image barrier. The two LINQ
predicates capture the queried storage, allocating a display class and delegate
even when the first attachment or an existing forced fence matches. Indexed
loops retain the same equality, first-match behavior and first fence flags.
No barrier, resource ownership, render-pass lifetime or cache key changes.
"""
from adapt_session import once


def apply(source):
    holder = source / 'src/Ryujinx.Graphics.Vulkan/RenderPassHolder.cs'
    once(holder, '''        public void AddForcedFence(TextureStorage storage, PipelineStageFlags stageFlags)
        {
            if (!_forcedFences.Any(fence => fence.Texture == storage))
            {
                _forcedFences.Add(new ForcedFence(storage, stageFlags));
            }
        }''', '''        public void AddForcedFence(TextureStorage storage, PipelineStageFlags stageFlags)
        {
            for (int index = 0; index < _forcedFences.Count; index++)
            {
                if (_forcedFences[index].Texture == storage)
                {
                    return;
                }
            }

            _forcedFences.Add(new ForcedFence(storage, stageFlags));
        }''')
    once(holder, '''        public bool ContainsAttachment(TextureStorage storage)
        {
            return _textures.Any(view => view.Storage == storage);
        }''', '''        public bool ContainsAttachment(TextureStorage storage)
        {
            for (int index = 0; index < _textures.Length; index++)
            {
                if (_textures[index].Storage == storage)
                {
                    return true;
                }
            }

            return false;
        }''')
    once(holder, 'using System.Linq;\n', '')
    return [holder]
