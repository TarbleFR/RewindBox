"""Bindless delta passes no longer scan the whole array, check it again or rebuild it after an invalidation (Core 697).

IPA 693 (Hogwarts Legacy, pid 38401, Core 695 counters, 3 min of play): of 3 584 delta passes, 297 scanned the whole
524 288-element array: 293 because a bound texture had been invalidated (ValidateTextures), 3 for a log overflow, 1
sampler array; 40 checked every element again after an invalidation during the pass ("epoch rescans") and 24 fell
back to the full rebuild; 155 M elements visited for 318 k changed. IPA 692 (Core 693), in play: gpuWork.arrayDelta
530 ms per 5.3 s window for 182 passes, each whole scan about 30 ms of GPU-thread time, the main cost of
gpuWork.bindings (1 039 ms) on the thread whose per-frame work bounds the frame rate.

Change, exact (same elements bound as before; only fewer elements are visited):
- CollectLoggedChanges: when a bound texture's sequence moved (the only reason for those 293 scans), the elements
  recorded with a moved sequence join the logged ids, found by one pointer pass over DeltaTextures/DeltaSequences
  (no pool lookup, about 1 ms for 524 288 elements instead of about 30 ms). Every element keeps the sequence it was
  resolved with, a sequence moves only with Texture.InvalidationEpoch, and pool items and invalid states change only
  at logged ids (the invariant the logged path already relies on), so the candidates are exactly the elements the
  whole scan would find changed. Too many to hold (more than 16 384 ids): the whole scan, as before.
- After the pass, an invalidation during it (the epoch moved) or a memory synchronisation that replaced a bound
  texture's storage no longer checks all elements and rebuilds the array: the ids logged since the pass started and
  the elements with a moved sequence are re-resolved in place, in up to four rounds; past that, or for a sampler
  array, or when the log no longer holds the pass's ids, the former whole check and full rebuild.
Fail closed on drift: the file must be the Core 693 preparation's.
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
BASELINE = {
    CACHE: '20760e44f814fa73039a394ca209011b1f1811d97cae55570a99750f57b72db8',
}

BUFFER_OLD = '''        private readonly int[] _deltaCandidates = new int[TexturePool.DeltaLogCapacity];
'''
BUFFER_NEW = '''        // RewindBox (adapt_array_delta_invalidated): room for the logged ids and the elements of invalidated textures.
        private const int DeltaCandidateCapacity = TexturePool.DeltaLogCapacity * 4;
        private const int DeltaRepairRounds = 4;
        private readonly int[] _deltaCandidates = new int[DeltaCandidateCapacity];
        private readonly int[] _deltaRepairs = new int[DeltaCandidateCapacity];

        /// <summary>
        /// RewindBox (adapt_array_delta_invalidated): appends the elements recorded with a texture whose sequence has
        /// moved since (it was invalidated, removed from the pool or its storage replaced). One pointer pass, no pool
        /// lookup.
        /// </summary>
        /// <returns>False if they do not fit in <paramref name="destination"/></returns>
        private static bool AppendStaleElements(CacheEntry entry, int[] destination, ref int count)
        {
            Texture[] textures = entry.DeltaTextures;

            if (textures == null)
            {
                return true;
            }

            int[] sequences = entry.DeltaSequences;
            int length = Math.Min(entry.DeltaLength, textures.Length);

            for (int index = 0; index < length; index++)
            {
                Texture texture = textures[index];

                if (texture != null && texture.InvalidatedSequence != sequences[index])
                {
                    if (count == destination.Length)
                    {
                        return false;
                    }

                    destination[count++] = index;
                }
            }

            return true;
        }

        /// <summary>
        /// RewindBox (adapt_array_delta_invalidated): sorts the first <paramref name="count"/> ids and removes duplicates.
        /// </summary>
        private static int SortUnique(int[] ids, int count)
        {
            Array.Sort(ids, 0, count);

            int unique = 0;

            for (int index = 0; index < count; index++)
            {
                if (unique == 0 || ids[unique - 1] != ids[index])
                {
                    ids[unique++] = ids[index];
                }
            }

            return unique;
        }

        /// <summary>
        /// RewindBox (adapt_array_delta_invalidated): the elements a change during a pass may have made stale: the ids
        /// the pool logged since the pass read its position, and the elements recorded with a moved sequence.
        /// </summary>
        /// <returns>False if the log no longer holds them or they do not fit: the whole array must be checked</returns>
        private bool CollectRepairs(CacheEntry entry, TexturePool pool, long since, out int count)
        {
            count = 0;

            if (pool == null || entry.DeltaTextures == null ||
                !pool.CopyDeltaLog(since, pool.DeltaLogCount, _deltaRepairs, out count) ||
                !AppendStaleElements(entry, _deltaRepairs, ref count))
            {
                count = 0;
                return false;
            }

            count = SortUnique(_deltaRepairs, count);
            return true;
        }
'''

COLLECT_OLD = '''            if (pool == null || entry.DeltaLogPool != pool ||
                !pool.CopyDeltaLog(entry.DeltaLogPosition, until, _deltaCandidates, out count) ||
                !entry.ValidateTextures())
            {
                count = 0;
                return false;
            }

            Array.Sort(_deltaCandidates, 0, count);

            int unique = 0;

            for (int index = 0; index < count; index++)
            {
                if (unique == 0 || _deltaCandidates[unique - 1] != _deltaCandidates[index])
                {
                    _deltaCandidates[unique++] = _deltaCandidates[index];
                }
            }

            count = unique;
            return true;
'''
COLLECT_NEW = '''            if (pool == null || entry.DeltaLogPool != pool ||
                !pool.CopyDeltaLog(entry.DeltaLogPosition, until, _deltaCandidates, out count))
            {
                count = 0;
                return false;
            }

            // RewindBox (adapt_array_delta_invalidated): a bound texture whose sequence moved no longer forces a whole
            // scan: the elements recorded with a moved sequence join the logged ids.
            if (!entry.ValidateTextures() && !AppendStaleElements(entry, _deltaCandidates, ref count))
            {
                count = 0;
                return false;
            }

            count = SortUnique(_deltaCandidates, count);
            return true;
'''

LOOP_OLD = '''            bool completed = false;

            try
            {
                for (int visit = 0; visit < visits; visit++)
                {
                    int index = logged ? _deltaCandidates[visit] : visit;

                    if (index >= length || entry.DeltaUnchanged(index, texturePool, samplerPool, isSampler, aliasesMoved))
                    {
                        continue;
                    }
'''
LOOP_NEW = '''            bool completed = false;
            // RewindBox (adapt_array_delta_invalidated): round 0 visits the logged ids (with the elements of
            // invalidated textures) or the whole array; later rounds re-resolve, in place, the elements a change during
            // the pass made stale.
            int round = 0;
            int repairs = 0;

            try
            {
              while (true)
              {
                int roundVisits = round == 0 ? visits : repairs;

                for (int visit = 0; visit < roundVisits; visit++)
                {
                    int index = round != 0 ? _deltaRepairs[visit] : logged ? _deltaCandidates[visit] : visit;

                    if (index >= length || entry.DeltaUnchanged(index, texturePool, samplerPool, isSampler, round == 0 && aliasesMoved))
                    {
                        continue;
                    }
'''

AFTER_OLD = '''                FlushDeltaRun(entry, isImage, isSampler, runStart, ref runCount);

                if ((texturePool?.AliasGeneration ?? 0) != aliasGeneration)
                {
                    // A lookup of this pass destroyed an alias list: views bound before it may be stale.
                    return false;
                }

                if (Volatile.Read(ref Texture.InvalidationEpoch) != invalidationEpoch)
                {
                    // A texture was invalidated during the pass (possibly by one of its own lookups, which can remove
                    // or replace a texture bound at another element): every element must still resolve to what is
                    // bound. Without an invalidation, pool items change only for the ids this pass resolved itself
                    // (RemoveFromPools and UpdatePoolMappings, the only other writers, both move the epoch).
                    for (int index = 0; index < length; index++)
                    {
                        if (!entry.DeltaUnchanged(index, texturePool, samplerPool, isSampler, aliasesMoved: false))
                        {
                            return false;
                        }
                    }
                }

                // The same memory synchronisation, store signal and scale blacklist as the cache-hit path. Unchanged
                // elements were sent with their recorded hosts: if a synchronisation replaced a bound texture's
                // storage, the full rebuild binds the new host instead.
                if (!entry.SynchronizeMemoryAndValidate(isStore, resScaleUnsupported))
                {
                    return false;
                }
'''
AFTER_NEW = '''                FlushDeltaRun(entry, isImage, isSampler, runStart, ref runCount);

                if ((texturePool?.AliasGeneration ?? 0) != aliasGeneration)
                {
                    // A lookup of this pass destroyed an alias list: views bound before it may be stale.
                    return false;
                }

                int epoch = Volatile.Read(ref Texture.InvalidationEpoch);

                if (epoch != invalidationEpoch)
                {
                    // A texture was invalidated during the pass (possibly by one of its own lookups, which can remove
                    // or replace a texture bound at another element): every element must still resolve to what is
                    // bound. Without an invalidation, pool items change only for the ids this pass resolved itself
                    // (RemoveFromPools and UpdatePoolMappings, the only other writers, both move the epoch).
                    // RewindBox (adapt_array_delta_invalidated): those writers log the ids they change and move the
                    // sequence of the textures they invalidate, so the elements to check are the ids logged since the
                    // pass started and the elements recorded with a moved sequence; they are re-resolved in place.
                    if (!isSampler && round < DeltaRepairRounds && CollectRepairs(entry, texturePool, logPosition, out repairs))
                    {
                        invalidationEpoch = epoch;
                        round++;
                        continue;
                    }

                    for (int index = 0; index < length; index++)
                    {
                        if (!entry.DeltaUnchanged(index, texturePool, samplerPool, isSampler, aliasesMoved: false))
                        {
                            return false;
                        }
                    }
                }

                // The same memory synchronisation, store signal and scale blacklist as the cache-hit path. Unchanged
                // elements were sent with their recorded hosts: if a synchronisation replaced a bound texture's
                // storage, the full rebuild binds the new host instead.
                if (!entry.SynchronizeMemoryAndValidate(isStore, resScaleUnsupported))
                {
                    // RewindBox (adapt_array_delta_invalidated): a replaced storage moved its texture's sequence: the
                    // elements recorded with it (and any id logged meanwhile) are re-resolved in place instead.
                    int synchronisedEpoch = Volatile.Read(ref Texture.InvalidationEpoch);

                    if (!isSampler && round < DeltaRepairRounds && CollectRepairs(entry, texturePool, logPosition, out repairs))
                    {
                        invalidationEpoch = synchronisedEpoch;
                        round++;
                        continue;
                    }

                    return false;
                }

                break;
              }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    cache = paths[CACHE]
    once(cache, BUFFER_OLD, BUFFER_NEW)
    once(cache, COLLECT_OLD, COLLECT_NEW)
    once(cache, LOOP_OLD, LOOP_NEW)
    once(cache, AFTER_OLD, AFTER_NEW)
    return list(paths.values())
