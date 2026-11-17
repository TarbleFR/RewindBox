"""Render thread (every title): a finished command buffer clears its dependants' ownership bits in one pass, then
releases them in a second.

IPA 764 / Core a80b212f, Hogwarts Legacy in the castle courtyard (private journals, pid 28682; docs/melonx-ipa764-journals-
2026-11-17.md): 660 to 720 submissions per 5 s window cost 310 to 630 ms of the render thread. Profile #2 of the window
(300 samples in 3 322 ms, decoded with the Core's symbol map and binary): CommandBufferPool.Rent holds 17 samples, 10 of
them in FreeConsumed -> WaitAndDecrementRef, 6 of those on its one indirect call, IAuto.DecrementReferenceCount(int), and 7
in vkBeginCommandBuffer (MoltenVK's reset); no lock wait. A main command buffer holds about 1 000 to 2 600 dependants
(at least 360 descriptor sets written, up to 2 054 view and sampler references of texture array passes, the draws'
textures, buffers, pipelines and framebuffers). For each, Auto<T>.DecrementReferenceCount(int) clears its bit, walks the
objects it references to clear theirs (a view: its image, then the memory), then decrements its count: Interlocked.
Decrement, compiled for ARMv8.0 as ldaxr/stlxr and dmb ish, a full barrier before the next dependant's loads can start,
so the cache misses of the next objects (clean samples on RhpInterfaceDispatch and DecrementReferenceCount) do not
overlap.

Change:
- Auto.cs: IAuto gains ReleaseCommandBufferOwnership(int), the bit clears of DecrementReferenceCount(int) without the
  release; DecrementReferenceCount(int) is that, then DecrementReferenceCount() (Auto<T> is the only IAuto).
- CommandBufferPool.WaitAndDecrementRef: the ownership bits of every dependant first (plain stores), then the releases.

Same clears and same releases, in the list's order: no dependant is released before its bits are cleared, a destroyed
object is never walked (every clear now comes before every release), the final bits and counts are those of before, and
every resource is destroyed at the same point after its fence. The waitables, the fence and the lists are unchanged.

Expected on the device: fewer samples on that indirect call and a smaller "submits ... (queue ...)" figure (computed 40 to
60 ms per 5 s window; it depends on the processor's caches, and may be none if the objects are already cached). Not
measured. Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

AUTO = 'src/Ryujinx.Graphics.Vulkan/Auto.cs'
POOL = 'src/Ryujinx.Graphics.Vulkan/CommandBufferPool.cs'
# The preparation of Core a80b212f (IPA 764): Auto.cs after adapt_command_buffer_ownership, CommandBufferPool.cs after
# adapt_signalled_fence_release.
BASELINE = {
    AUTO: '970f46ec809cc14d2de558c2e9531236f5e30bd8866d319ef02686f96ed0b156',
    POOL: '5f1bfde291195d5e29bf4a710d77c6eac28b3295b0fc12bd76a4ce7a46732b6c',
}

INTERFACE_OLD = '''        void IncrementReferenceCount();
        void DecrementReferenceCount(int cbIndex);
        void DecrementReferenceCount();
    }
'''
INTERFACE_NEW = '''        void IncrementReferenceCount();
        void DecrementReferenceCount(int cbIndex);
        void DecrementReferenceCount();

        // RewindBox (adapt_release_passes): the bit clears of DecrementReferenceCount(int), without the release.
        void ReleaseCommandBufferOwnership(int cbIndex);
    }
'''

RELEASE_OLD = '''        public void DecrementReferenceCount(int cbIndex)
        {
            _cbOwnership.Clear(cbIndex);

            // RewindBox (adapt_command_buffer_ownership): the bits set through this object, before the release that may
            // destroy it and release the objects it references.
            if (_referencedObjs != null)
            {
                for (int i = 0; i < _referencedObjs.Length; i++)
                {
                    _referencedObjs[i].ClearCommandBufferOwnership(cbIndex);
                }
            }

            DecrementReferenceCount();
        }
'''
RELEASE_NEW = '''        public void DecrementReferenceCount(int cbIndex)
        {
            ReleaseCommandBufferOwnership(cbIndex); // RewindBox (adapt_release_passes)
            DecrementReferenceCount();
        }

        // RewindBox (adapt_release_passes): the ownership bits of a finished command buffer set through this object,
        // cleared without releasing it (CommandBufferPool clears every dependant's before it releases any).
        public void ReleaseCommandBufferOwnership(int cbIndex)
        {
            _cbOwnership.Clear(cbIndex);

            // RewindBox (adapt_command_buffer_ownership): the bits set through this object, before the release that may
            // destroy it and release the objects it references.
            if (_referencedObjs != null)
            {
                for (int i = 0; i < _referencedObjs.Length; i++)
                {
                    _referencedObjs[i].ClearCommandBufferOwnership(cbIndex);
                }
            }
        }
'''

LOOP_OLD = '''            foreach (DependantEntry dependant in entry.Dependants)
            {
                dependant.Value.DecrementReferenceCount(cbIndex);
            }
'''
LOOP_NEW = '''            // RewindBox (adapt_release_passes): every dependant's ownership bits first (plain stores: the loads of the next
            // objects overlap), then the releases (an interlocked decrement each, on lines now cached). The same clears and
            // releases in the list's order; no dependant is released before its bits are cleared.
            foreach (DependantEntry dependant in entry.Dependants)
            {
                dependant.Value.ReleaseCommandBufferOwnership(cbIndex);
            }

            foreach (DependantEntry dependant in entry.Dependants)
            {
                dependant.Value.DecrementReferenceCount();
            }
'''

PAIRS = [
    (AUTO, INTERFACE_OLD, INTERFACE_NEW),
    (AUTO, RELEASE_OLD, RELEASE_NEW),
    (POOL, LOOP_OLD, LOOP_NEW),
]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
