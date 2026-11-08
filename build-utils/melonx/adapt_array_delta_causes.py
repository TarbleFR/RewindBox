"""Bindless delta passes count why they scan a whole pool array (Core 695; diagnostics).

IPA 691 and IPA 692 (Hogwarts Legacy, Core 691/693), core-performance windows in play: gpuWork.arrayDelta 0.4-0.9 s per
5 s window for about 270-450 passes, 6-21 M elements visited for 18-50 k changed, i.e. about 15-40 whole scans of a
524 288-element pool array per window. UpdateFromPoolDelta visits only the logged ids when it can; it scans the whole
array for a sampler array, after an alias list was destroyed (AliasGeneration), when the array's log position is from
another pool, when more than DeltaLogCapacity (4096) ids were logged since its last pass, or when a bound texture was
invalidated (ValidateTextures); it rescans everything again if a texture was invalidated during the pass, and it
synchronises every texture the array holds on each pass. Which of these causes the scans is not measured.

Change, diagnostics only (the pass itself is unchanged): counters on the GPU thread and one private Core journal line
(EmbeddedLaunchDiagnostics, stage arrayDelta, status causes; the file already compiles against the collector) every 512
passes: passes, logged passes, whole scans by cause (samplers, aliases moved, other pool, log overflow, invalidated
texture), elements visited and changed, epoch rescans, passes that fall back to the full rebuild, and the textures
synchronised per pass. Not measured on an iPhone. Fail closed on drift: the file must be the Core 693 preparation's.
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
BASELINE = {
    CACHE: '20760e44f814fa73039a394ca209011b1f1811d97cae55570a99750f57b72db8',
}

ENTRY_OLD = '''            long logPosition = texturePool?.DeltaLogCount ?? 0;
            int candidates = 0;
            bool logged = !isSampler && !aliasesMoved && CollectLoggedChanges(entry, texturePool, logPosition, out candidates);
            int visits = logged ? candidates : length;
'''
ENTRY_NEW = '''            long logPosition = texturePool?.DeltaLogCount ?? 0;
            int candidates = 0;
            // RewindBox (adapt_array_delta_causes): why the pass cannot use the log, measured before CollectLoggedChanges.
            bool otherPool = texturePool == null || entry.DeltaLogPool != texturePool;
            bool overflow = !otherPool && logPosition - entry.DeltaLogPosition > TexturePool.DeltaLogCapacity;
            bool logged = !isSampler && !aliasesMoved && CollectLoggedChanges(entry, texturePool, logPosition, out candidates);
            int visits = logged ? candidates : length;
            NoteDeltaPass(logged, isSampler, aliasesMoved, otherPool, overflow, visits, entry.Textures.Count);
'''
EPOCH_OLD = '''                if (Volatile.Read(ref Texture.InvalidationEpoch) != invalidationEpoch)
                {
'''
EPOCH_NEW = '''                if (Volatile.Read(ref Texture.InvalidationEpoch) != invalidationEpoch)
                {
                    _deltaEpochRescans++; // RewindBox (adapt_array_delta_causes)
'''
COUNT_OLD = '''                PD.Count(PD.Counter.ArrayDeltaElements, visits);
                PD.Count(PD.Counter.ArrayDeltaChanged, changed);
'''
COUNT_NEW = '''                PD.Count(PD.Counter.ArrayDeltaElements, visits);
                PD.Count(PD.Counter.ArrayDeltaChanged, changed);
                _deltaChanged += changed; // RewindBox (adapt_array_delta_causes)
'''
FINALLY_OLD = '''                if (!completed)
                {
                    // The backend array and the state are left to the full rebuild, now or on the next update.
'''
FINALLY_NEW = '''                if (!completed)
                {
                    _deltaRebuilds++; // RewindBox (adapt_array_delta_causes)
                    // The backend array and the state are left to the full rebuild, now or on the next update.
'''
METHOD_OLD = '''        /// <summary>
        /// Updates the elements of a pool array whose pool objects changed since its last update.
        /// </summary>
'''
METHOD_NEW = '''        // RewindBox (adapt_array_delta_causes): delta pass causes, GPU thread only; one Core journal line every 512 passes.
        private long _deltaPasses, _deltaLogged, _deltaSamplerScans, _deltaAliasScans, _deltaOtherPoolScans, _deltaOverflowScans,
            _deltaInvalidScans, _deltaVisits, _deltaChanged, _deltaEpochRescans, _deltaRebuilds, _deltaSynchronised;

        private void NoteDeltaPass(bool logged, bool isSampler, bool aliasesMoved, bool otherPool, bool overflow, int visits, int synchronised)
        {
            _deltaPasses++;
            _deltaVisits += visits;
            _deltaSynchronised += synchronised;

            if (logged)
            {
                _deltaLogged++;
            }
            else if (isSampler)
            {
                _deltaSamplerScans++;
            }
            else if (aliasesMoved)
            {
                _deltaAliasScans++;
            }
            else if (otherPool)
            {
                _deltaOtherPoolScans++;
            }
            else if (overflow)
            {
                _deltaOverflowScans++;
            }
            else
            {
                _deltaInvalidScans++;
            }

            if (_deltaPasses % 512 == 0)
            {
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("arrayDelta", "causes", detail:
                    $"Bindless delta passes: {_deltaPasses} (logged {_deltaLogged}; whole scans: samplers {_deltaSamplerScans}, " +
                    $"aliases moved {_deltaAliasScans}, other pool {_deltaOtherPoolScans}, log overflow {_deltaOverflowScans}, " +
                    $"invalidated texture {_deltaInvalidScans}); elements visited {_deltaVisits}, changed {_deltaChanged}; " +
                    $"epoch rescans {_deltaEpochRescans}; full rebuilds {_deltaRebuilds}; textures synchronised per pass " +
                    $"{_deltaSynchronised / _deltaPasses} (adapt_array_delta_causes)");
            }
        }

        /// <summary>
        /// Updates the elements of a pool array whose pool objects changed since its last update.
        /// </summary>
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    cache = paths[CACHE]
    once(cache, ENTRY_OLD, ENTRY_NEW)
    once(cache, EPOCH_OLD, EPOCH_NEW)
    once(cache, COUNT_OLD, COUNT_NEW)
    once(cache, FINALLY_OLD, FINALLY_NEW)
    once(cache, METHOD_OLD, METHOD_NEW)
    return list(paths.values())
