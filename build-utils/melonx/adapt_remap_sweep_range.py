"""A guest Map or Unmap re-queues only the partially mapped textures it can concern, not all of them.

IPA 725, Hogwarts Legacy (pid 51986; private journals, not in the repository; aggregates only). In the `performance`
samples of 5.1 s, the bindless delta pass (TextureBindingsArrayCache.UpdateFromPoolDelta) runs 390 to 570 times per
sample (4 to 5 times per frame), visits 53 to 160 pool ids per call of which 88 % are changed, takes 0.43 to 0.68 s of
the GPU thread per sample and allocates 18 to 34 KiB per call, in the 20 s at 30 FPS as well as in the stretches at
20 FPS: a nearly constant set of ids, in steady scenes.

Mechanism (upstream TextureCache.MemoryUnmappedHandler): every Map and Unmap of a GPU address space runs a remap action
that calls UpdatePoolMappings on EVERY member of _partiallyMappedTextures ("any texture that has been unmapped at any
point or is partially unmapped"), wherever the event is. UpdatePoolMappings empties each pool item that names the
texture, logs the id, queues the reference in the pool's dereference queue and moves the texture's sequence. On the GPU
thread the next use puts the same texture back (TexturePool.ProcessDereferenceQueue: two page walks of its range, and
two region lists allocated when the range has a hole), and every bindless array entry over that pool then sees each of
those ids as changed, records it again and sends its element to the backend again. A set of textures that stay
partially mapped, or that cannot leave the set (a view, a texture with views or copy dependencies is never looked at
again by UpdatePartiallyMapped), is therefore resolved and re-sent after every mapping event of the guest, whatever the
event touched. Host measurement (Linux, 75 such textures, four array entries over a pool of 2048): 850 us for the first
entry and 89 us for each following one per event, 31 KiB and 4.5 KiB allocated; with this change an unrelated event
does not reach the delta pass at all (the pool is not modified: the entries take their cache hit).

Change (every title; TextureCache.cs, Texture.cs, TexturePool.cs): the remap action still sweeps, exactly as before,
the textures the event physically overlaps (they are marked, under the lock of the set). Every other member is swept
only if the event can concern it (Texture.PoolMappingsTouch): one of its pool owners belongs to a pool of the event's
address space (TexturePool.ChannelMemoryManager: the one ProcessDereferenceQueue translates with) and the pages of
[owner.GpuAddress, owner.GpuAddress + texture.Size), the range the restore evaluates, intersect the pages of the event.
The translation of a range depends only on the page table entries of that range in that address space, and only Map
and Unmap write them, within their own range. Two rules keep the sweep where its side effects are relied on:
- a texture never swept (ChangedMapping false: created partially mapped) is swept as before, once: only then does every
  lookup by address compare its range (TextureCache.FindOrCreateTexture trusts an exact match at the creation address
  while ChangedMapping is false), so a hole filled at an address none of its pool owners uses is not missed later;
- a texture no pool references (short cache, auto delete cache, or already waiting in a dereference queue) is swept as
  before: nothing is queued for it, and the move of its sequence is what invalidates the short cache entry of a texture
  whose hole was filled while no pool named it (AutoDeleteCache.FindShortCache returns it without comparing its range).
A member that is left alone keeps its pool references, its sequence, ChangedMapping, its membership of the set, and its
owners at another address (their forced removal happens when an event concerns the texture). UpdatePoolMappings,
ProcessDereferenceQueue, the handling of the overlapped textures and the delta pass are unchanged. The check takes the
pool owners' lock inside the set's lock, as UpdatePoolMappings does, and allocates nothing (guest threads).
Behaviour that changes with it: a member that cannot be restored in place (view, views, copy dependency) and that only
the pool references was destroyed and created again at every unrelated event; it is now kept.

Two counters (EmbeddedPerformanceDiagnostics, in the "counts" of the performance samples like arrDeltaElems): per
event, remapSweepSkipped (members left alone) and remapSweepQueued (members swept). They are counted on the thread
that maps (a guest service thread: one of the 16 counter slots of the session, as readCopies already takes from the
guest's CPU threads).

Not measured on an iPhone: the device has not shown that its Map and Unmap events are the cause; the two counters
decide it (remapSweepSkipped large and arrDeltaChanged falling with it: this was the cause; remapSweepQueued staying
at the level of arrDeltaChanged: the events do concern these textures and the cost is elsewhere). Fail closed on drift:
the four files must be the Core 733 preparation's.
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs'
TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
POOL = 'src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs'
DIAGNOSTICS = 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
BASELINE = {
    CACHE: 'aab7df8766375daeebc17cfad2e9253a4cc97c9c5490dae767ce074d3968a897',
    TEXTURE: '185177cf3d69b78a5b59a7d886daee8b1645e8346149ae162e6034d9a783ac90',
    POOL: '01a50bf34d5eb49ead967ccd58f49a1d061b97aad624678411cfd162d79ce153',
    DIAGNOSTICS: 'cb4d8df1db93dfb663c2c384a73fa77416ba5de0afcfcd972c28890084b65882',
}

USING_OLD = '''using Ryujinx.Common;
using Ryujinx.Graphics.GAL;
using Ryujinx.Memory;
'''
USING_NEW = '''using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;
using Ryujinx.Common;
using Ryujinx.Graphics.GAL;
using Ryujinx.Memory;
'''

SWEEP_OLD = '''                    e.AddRemapAction(() =>
                    {
                        lock (_partiallyMappedTextures)
                        {
                            if (overlapCount > 0)
                            {
                                for (int i = 0; i < overlapCount; i++)
                                {
                                    _partiallyMappedTextures.Add(overlaps[i]);
                                }
                            }

                            // Any texture that has been unmapped at any point or is partially unmapped
                            // should update their pool references after the remap completes.

                            foreach (Texture texture in _partiallyMappedTextures)
                            {
                                texture.UpdatePoolMappings();
                            }
                        }
                    });
'''
SWEEP_NEW = '''                    e.AddRemapAction(() =>
                    {
                        lock (_partiallyMappedTextures)
                        {
                            if (overlapCount > 0)
                            {
                                for (int i = 0; i < overlapCount; i++)
                                {
                                    _partiallyMappedTextures.Add(overlaps[i]);

                                    // RewindBox (adapt_remap_sweep_range): physically overlapped by this event: swept below as before.
                                    overlaps[i].RemapSweepOverlapped = true;
                                }
                            }

                            // Any texture that has been unmapped at any point or is partially unmapped
                            // should update their pool references after the remap completes.
                            // RewindBox (adapt_remap_sweep_range): the other members only when this event can concern them
                            // (never swept yet, no pool owner, or a pool owner of this address space whose range the
                            // event intersects); the rest keep their pool references, sequence and mapping state.

                            MemoryManager memoryManager = (MemoryManager)sender;
                            int skipped = 0;
                            int queued = 0;

                            foreach (Texture texture in _partiallyMappedTextures)
                            {
                                if (texture.PoolMappingsTouch(memoryManager, e.Address, e.Size))
                                {
                                    texture.UpdatePoolMappings();
                                    queued++;
                                }
                                else
                                {
                                    skipped++;
                                }
                            }

                            PD.Count(PD.Counter.RemapSweepSkipped, skipped);
                            PD.Count(PD.Counter.RemapSweepQueued, queued);
                        }
                    });
'''

# The three tests of PoolMappingsTouch that decide a member the event does not physically overlap (the gate's
# sensitivity variants alter them one at a time).
NEVER_SWEPT_RULE = '''            if (!ChangedMapping)
            {
                return true;
            }

'''
NO_OWNER_RULE = '''                if (_poolOwners.Count == 0)
                {
                    return true;
                }
'''
OWNER_TEST = 'if (owner.Pool.ChannelMemoryManager == memoryManager && owner.GpuAddress < end && owner.GpuAddress + textureSize > start)'

TOUCH_OLD = '''        /// <summary>
        /// Queue updating texture mappings on the pool. Happens from another thread.
        /// </summary>
        public void UpdatePoolMappings()
'''
TOUCH_NEW = '''        /// <summary>
        /// RewindBox (adapt_remap_sweep_range): set by the texture cache on the textures a mapping event physically
        /// overlaps and consumed by <see cref="PoolMappingsTouch"/>, both under the lock of its partially mapped set.
        /// </summary>
        internal bool RemapSweepOverlapped;

        /// <summary>
        /// RewindBox (adapt_remap_sweep_range): whether a mapping event of <paramref name="memoryManager"/> over
        /// [<paramref name="address"/>, <paramref name="address"/> + <paramref name="size"/>) can concern this member of
        /// the partially mapped set, so that its pool mappings must be queued for an update as before. False only for a
        /// texture that was swept before (every lookup by address compares its range), that pools reference, and none
        /// of whose references is translated through pages of that address space the event writes. Happens from another
        /// thread; allocates nothing.
        /// </summary>
        internal bool PoolMappingsTouch(MemoryManager memoryManager, ulong address, ulong size)
        {
            if (RemapSweepOverlapped)
            {
                RemapSweepOverlapped = false;

                return true;
            }

''' + NEVER_SWEPT_RULE + '''            ulong start = address & ~MemoryManager.PageMask;
            ulong end = (address + size + MemoryManager.PageMask) & ~MemoryManager.PageMask;
            ulong textureSize = Size;

            lock (_poolOwners)
            {
''' + NO_OWNER_RULE + '''
                foreach (TexturePoolOwner owner in _poolOwners)
                {
                    ''' + OWNER_TEST + '''
                    {
                        return true;
                    }
                }
            }

            return false;
        }

        /// <summary>
        /// Queue updating texture mappings on the pool. Happens from another thread.
        /// </summary>
        public void UpdatePoolMappings()
'''

MANAGER_OLD = '''        /// <summary>
        /// Linked list node used on the texture pool cache.
        /// </summary>
        public LinkedListNode<TexturePool> CacheNode { get; set; }
'''
MANAGER_NEW = '''        /// <summary>
        /// RewindBox (adapt_remap_sweep_range): the GPU address space this pool's descriptors are translated with (the one
        /// ProcessDereferenceQueue re-evaluates a remapped texture in).
        /// </summary>
        internal MemoryManager ChannelMemoryManager => _channel.MemoryManager;

        /// <summary>
        /// Linked list node used on the texture pool cache.
        /// </summary>
        public LinkedListNode<TexturePool> CacheNode { get; set; }
'''

ENUM_OLD = '''        ArrayFullElements, ArrayDeltaElements, ArrayDeltaChanged, ArrayBufferElements, Count }
'''
ENUM_NEW = '''        ArrayFullElements, ArrayDeltaElements, ArrayDeltaChanged, ArrayBufferElements,
        RemapSweepSkipped, RemapSweepQueued, Count } // RewindBox (adapt_remap_sweep_range)
'''
NAMES_OLD = '''        "arrFullElems", "arrDeltaElems", "arrDeltaChanged", "arrBufElems" };
'''
NAMES_NEW = '''        "arrFullElems", "arrDeltaElems", "arrDeltaChanged", "arrBufElems",
        "remapSweepSkipped", "remapSweepQueued" }; // RewindBox (adapt_remap_sweep_range)
'''

# (file, old, new) in application order; every old text is the Core 733 preparation's (no pair needs another's result).
PAIRS = (
    (CACHE, USING_OLD, USING_NEW),
    (CACHE, SWEEP_OLD, SWEEP_NEW),
    (TEXTURE, TOUCH_OLD, TOUCH_NEW),
    (POOL, MANAGER_OLD, MANAGER_NEW),
    (DIAGNOSTICS, ENUM_OLD, ENUM_NEW),
    (DIAGNOSTICS, NAMES_OLD, NAMES_NEW),
)


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
