"""Keep expensive first-use pipelines and give them earlier replay slots."""

import hashlib

from adapt_session import once


JOURNAL = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
PROGRAM = 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'
ARRAY_CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'

BASELINE = {'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs': '538630e13bae957c4f2e1114a6f868ca60ada42dd2f4f84fff22fe861ae553d5',
 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs': 'd81123196bb2e29d89fc8b6f9185aafdeb304c5e0cc617f841f69e1133e0d1e1',
 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': 'cea5852c2eb28b383609c8fd852e135cafe33a9733eb082e9ae2e236eb829a13'}


def prioritize_expensive_variants(path):
    once(path, '        internal const long CostlyReplayMs = 300;',
         '''        internal const long CostlyReplayMs = 300;
        internal const uint VisibleDrawStallMs = 100;''')
    once(path, '''                                rewrite = true; // a later line for the same variant replaces the earlier one
                                record.Sessions = (ushort)Math.Max(record.Sessions, previous.Sessions);''',
         '''                                // Notes can be appended in a different order from the draw and worker.
                                rewrite = true;
                                record.Sessions = (ushort)Math.Max(record.Sessions, previous.Sessions);
                                record.LastSession = Math.Max(record.LastSession, previous.LastSession);
                                record.FirstSeenMs = Math.Min(record.FirstSeenMs, previous.FirstSeenMs);
                                record.CostMs = Math.Max(record.CostMs, previous.CostMs);''')
    once(path, '''                // Not before the journal is read (the first second of a launch), and at most 4 notes per kept variant.
                if (_stopped || !_loaded || _notedThisSession.Count >= 4 * MaxRecords || !_notedThisSession.Add(key))''',
         '''                // Draw and worker can both encounter this exact variant.
                // A second note can improve the cost without refreshing its session twice.
                bool firstNote = !_stopped && _loaded && _notedThisSession.Count < 4 * MaxRecords &&
                    _notedThisSession.Add(key);
                if (!firstNote)''')
    once(path, '''                    if (!_stopped && !_notedThisSession.Contains(key))
                    {
                        NotRecorded++;
                    }

                    return;
                }

                // RewindBox (adapt_variant_journal_room): a state given up earlier this session is still known (back below).''',
         '''                    if (_stopped || !_loaded || !EncodingPolicy.IncrementalArrayDescriptors ||
                        elapsedMs < VisibleDrawStallMs || !_notedThisSession.Contains(key) ||
                        !_records.TryGetValue(key, out record) || elapsedMs <= record.CostMs)
                    {
                        if (!_stopped && !_notedThisSession.Contains(key))
                        {
                            NotRecorded++;
                        }
                        return;
                    }
                }

                // RewindBox (adapt_variant_journal_room): a state given up earlier this session is still known (back below).''')
    once(path, '''                if (builtForSkipped || waitedForSkipped)
                {
                    // RewindBox (adapt_queued_variant_record): counted above; recorded below, not a late creation.
                }''',
         '''                if (!firstNote || builtForSkipped || waitedForSkipped)
                {
                    // The cost-only update and skipped draw paths do not count as a second creation.
                }''')
    once(path, '''                if (seenDuringLaunch != 0)
                {
                    return seenDuringLaunch;
                }
            }
            return Compare(a, b);''',
         '''                if (seenDuringLaunch != 0)
                {
                    return seenDuringLaunch;
                }

                bool costly = a.CostMs >= VisibleDrawStallMs;
                int costlyFirst = (b.CostMs >= VisibleDrawStallMs).CompareTo(costly);
                if (costlyFirst != 0)
                {
                    return costlyFirst;
                }
                if (costly && a.CostMs != b.CostMs)
                {
                    return b.CostMs.CompareTo(a.CostMs);
                }
            }
            return Compare(a, b);''')


def retain_expensive_variants(path):
    once(path, '''            var key = (program, id);
            Record record;
            int generation; // RewindBox (adapt_variant_journal_room):''',
         '''            var key = (program, id);
            uint costMs = (uint)Math.Clamp(elapsedMs, 0, uint.MaxValue);
            int generation; // RewindBox (adapt_variant_journal_room):''')
    once(path, '''                if (!firstNote)
                {
                    // RewindBox (adapt_variant_journal_room): a state not noted yet this session and refused here (met before
                    // the journal is read, or past the session's note bound) is counted as not recorded.
                    if (_stopped || !_loaded || !EncodingPolicy.IncrementalArrayDescriptors ||
                        elapsedMs < VisibleDrawStallMs || !_notedThisSession.Contains(key) ||
                        !_records.TryGetValue(key, out record) || elapsedMs <= record.CostMs)
                    {
                        if (!_stopped && !_notedThisSession.Contains(key))
                        {
                            NotRecorded++;
                        }
                        return;
                    }
                }

                // RewindBox (adapt_variant_journal_room): a state given up earlier this session is still known (back below).
                bool known = _records.TryGetValue(key, out record) || _evicted.TryGetValue(key, out record);''',
         '''                // A costly draw may follow a cheaper worker note that was refused when the journal was full.
                bool canRaiseCost = !_stopped && _loaded && EncodingPolicy.IncrementalArrayDescriptors &&
                    costMs >= VisibleDrawStallMs && _notedThisSession.Contains(key);
                if (!firstNote && !canRaiseCost)
                {
                    if (!_stopped && !_notedThisSession.Contains(key))
                    {
                        NotRecorded++;
                    }
                    return;
                }

                bool known = _records.TryGetValue(key, out Record record) || _evicted.TryGetValue(key, out record);
                if (!firstNote && known && costMs <= record.CostMs)
                {
                    return;
                }''')
    once(path, '''                        if (!MakeRoom())
                        {
                            NotRecorded++;
                            return;
                        }

                        _evicted.Remove(key);''',
         '''                        if (!MakeRoom(Math.Max(record.CostMs, costMs)))
                        {
                            NotRecorded++;
                            return;
                        }

                        _evicted.Remove(key);''')
    once(path, '''                    record.CostMs = (uint)Math.Max(record.CostMs, (uint)Math.Min(uint.MaxValue, elapsedMs));''',
         '''                    record.CostMs = Math.Max(record.CostMs, costMs);''')
    once(path, '''                    if (!MakeRoom())
                    {
                        NotRecorded++;
                        return;
                    }

                    record = new Record''',
         '''                    if (!MakeRoom(costMs))
                    {
                        NotRecorded++;
                        return;
                    }

                    record = new Record''')
    once(path, '                        CostMs = (uint)Math.Min(uint.MaxValue, elapsedMs),', '                        CostMs = costMs,')
    once(path, '''                    if (!MakeRoom())
                    {
                        NotRecorded++;
                        return;
                    }

                    _evicted.Remove(key);''',
         '''                    if (!MakeRoom(record.CostMs))
                    {
                        NotRecorded++;
                        return;
                    }

                    _evicted.Remove(key);''')
    once(path, '''            int order = Tier(a, current).CompareTo(Tier(b, current));

            if (order == 0)''',
         '''            int order = Tier(a, current).CompareTo(Tier(b, current));

            if (order == 0 && EncodingPolicy.IncrementalArrayDescriptors &&
                (a.CostMs >= VisibleDrawStallMs || b.CostMs >= VisibleDrawStallMs))
            {
                order = a.CostMs.CompareTo(b.CostMs);
            }

            if (order == 0)''')
    once(path, '''        // state of this session's eviction order that it still holds and that was not met this session; false when none is
        // left (every state it holds was met this session). Each loaded state is examined once per session.
        private bool MakeRoom()''',
         '''        // state of this session's eviction order that it still holds and that was not met this session.
        // Keep a recent, costly variant if an incoming variant would save less time at its first draw.
        private bool MakeRoom(uint incomingCostMs)''')
    once(path, '''                Record victim = _victims[^1];
                _victims.RemoveAt(_victims.Count - 1);
                var key = (victim.Program, victim.Id);

                if (victim.LastSession < _session && _records.TryGetValue(key, out Record held) && ReferenceEquals(held, victim))
                {
                    _records.Remove(key);
                    _evicted[key] = victim;
                    Evicted++;
                }''',
         '''                Record victim = _victims[^1];
                var key = (victim.Program, victim.Id);

                if (victim.LastSession < _session && _records.TryGetValue(key, out Record held) && ReferenceEquals(held, victim))
                {
                    if (EncodingPolicy.IncrementalArrayDescriptors && Tier(victim, _session) != 0 &&
                        victim.CostMs >= VisibleDrawStallMs && victim.CostMs > incomingCostMs)
                    {
                        return false;
                    }

                    _records.Remove(key);
                    _evicted[key] = victim;
                    Evicted++;
                }

                _victims.RemoveAt(_victims.Count - 1);''')


def start_replay_when_cache_is_ready(path):
    # The journal can load on a pool thread as soon as it is constructed.
    # Publish the pending state before giving that thread access to the gate.
    once(path, "            Variants = new PipelineVariantJournal(",
         "            if (_pendingMainSnapshot != null) _primaryCacheReady.Reset();\n            Variants = new PipelineVariantJournal(")
    once(path, '''                        _primaryCacheReady.Set();''', '''                        PublishPrimaryCacheReady();''')
    once(path, '''                _mainLoaded.Set();
                _primaryCacheReady.Set();''', '''                _mainLoaded.Set();
                PublishPrimaryCacheReady();''')
    once(path, '''        public PipelineCache MainCache => _mainState.Cache;''',
         '''        private void PublishPrimaryCacheReady()
        {
            bool wakeReplay = !_primaryCacheReady.IsSet;
            _primaryCacheReady.Set();
            if (wakeReplay)
            {
                ThreadPool.UnsafeQueueUserWorkItem(_ => Variants?.Pump(), null);
            }
        }

        public PipelineCache MainCache => _mainState.Cache;''')
    once(path, '''                mainCachePath == null ? null : Path.ChangeExtension(mainCachePath, ".variants"), PipelineVariantJournal.Schema, null);''',
         '''                mainCachePath == null ? null : Path.ChangeExtension(mainCachePath, ".variants"),
                PipelineVariantJournal.Schema, null,
                primaryCacheReady: _pendingMainSnapshot == null ? null : () => _primaryCacheReady.IsSet);''')
    once(path, '''        private readonly Func<int> _devicePercent;''',
         '''        private readonly Func<int> _devicePercent;
        private readonly Func<bool> _primaryCacheReady;''')
    once(path, '''        public PipelineVariantJournal(string path, ulong schema, Func<int> devicePercent, bool loadInBackground = true)''',
         '''        public PipelineVariantJournal(string path, ulong schema, Func<int> devicePercent, bool loadInBackground = true,
            Func<bool> primaryCacheReady = null)''')
    once(path, '''            _devicePercent = devicePercent ?? DeviceAvailablePercent;''',
         '''            _devicePercent = devicePercent ?? DeviceAvailablePercent;
            _primaryCacheReady = primaryCacheReady;''')
    once(path, '''            List<(ulong Program, ITarget Target)> offers;

            lock (_lock)''', '''            int programCount;

            lock (_lock)''')
    once(path, '''                offers = new(_pendingOffers);
                _pendingOffers.Clear();''',
         '''                programCount = _plan.Count;
                if (!_stopped)
                {
                    foreach ((ulong program, ITarget target) in _pendingOffers)
                    {
                        QueueReady(program, target);
                    }

                    _ready.Sort((a, b) => CompareForPlayback(a.Record, b.Record));
                }
                _pendingOffers.Clear();''')
    once(path, '''                $"{kept.Count} variants of {_plan.Count} programs planned''',
         '''                $"{kept.Count} variants of {programCount} programs planned''')
    once(path, '''            foreach ((ulong program, ITarget target) in offers)
            {
                Offer(program, target);
            }''', '''            Pump();''')
    once(path, '''                if (!_plan.Remove(program, out List<Record> records))
                {
                    return;
                }

                foreach (Record record in records)
                {
                    _ready.Add((record, target));
                }
''', '''                if (!QueueReady(program, target))
                {
                    return;
                }
''')
    once(path, '''        // Schedules the best-ranked ready variants while the bounds allow it.''',
         '''        // Both the initial batch and a later offer are added under _lock before a worker can pick a variant.
        private bool QueueReady(ulong program, ITarget target)
        {
            if (!_plan.Remove(program, out List<Record> records))
            {
                return false;
            }

            foreach (Record record in records)
            {
                _ready.Add((record, target));
            }
            return true;
        }

        // Schedules the best-ranked ready variants while the bounds allow it.''')
    once(path, '''                        _replayMs >= ReplayWorkBudgetMs)''',
         '''                        _replayMs >= ReplayWorkBudgetMs || _primaryCacheReady?.Invoke() == false)''')

    # An offer often arrives while both workers are busy or the snapshot is loading.
    # Coalesce these offers into one sort immediately before actual consumption.
    sort = "_ready.Sort((a, b) => CompareForPlayback(a.Record, b.Record));"
    once(path, "                    " + sort, "")
    once(path, "                " + sort, "")
    once(path, "        private readonly List<(Record Record, ITarget Target)> _ready = new();",
         "        private readonly List<(Record Record, ITarget Target)> _ready = new();\n        private bool _readyOrderDirty;")
    once(path, "            foreach (Record record in records)\n            {\n                _ready.Add",
         "            _readyOrderDirty = true;\n            foreach (Record record in records)\n            {\n                _ready.Add")
    once(path, """                    (record, target) = _ready[0];
                    _ready.RemoveAt(0);""", """                    if (_readyOrderDirty)
                    {
                        _ready.Sort((a, b) => CompareForPlayback(b.Record, a.Record));
                        _readyOrderDirty = false;
                    }
                    int best = _ready.Count - 1;
                    (record, target) = _ready[best];
                    _ready.RemoveAt(best);""")


def note_slow_default_pipeline(path):
    once(path, '''        // Called by a draw that obtained a pipeline this program had not built for its state (created on the render thread,
        // or joined from a queued compile): recorded for the next launch, except the warm-up's own state.''',
         '''        // Record late pipelines for the next launch, including a default
        // state when an actual draw had to wait for it long enough to stutter.''')
    once(path, '''            PipelineUid initial = GetInitialGraphicsPipelineKey();

            if (state.Internal.Equals(ref initial))
            {
                return;
            }

            // RewindBox (adapt_queued_variant_record): the pipeline the draw obtained''',
         '''            PipelineUid initial = GetInitialGraphicsPipelineKey();
            long elapsedMs = (long)elapsed.TotalMilliseconds;

            if (state.Internal.Equals(ref initial) &&
                (!EncodingPolicy.IncrementalArrayDescriptors || elapsedMs < PipelineVariantJournal.VisibleDrawStallMs))
            {
                return;
            }

            // RewindBox (adapt_queued_variant_record): the pipeline the draw obtained''')
    once(path, '''                (long)elapsed.TotalMilliseconds,
                joined,
                replayJoined:''',
         '''                elapsedMs,
                joined,
                replayJoined:''')


def skip_unchanged_array_descriptors(path):
    once(path, '''                    entry.RecordDelta(
                        index,
                        isSampler ? null : texturePool.PeekForBindingDelta(index, out _),
                        texture,
                        hostTexture,
                        isSampler ? samplerPool?.GetCachedItem(index) : null,
                        hostSampler,
                        replacing: true);

                    int runEnd = runStart + runCount;''',
         '''                    // Update the guest pool bookkeeping, even if the
                    // resolved host view (or sampler) stays the same.
                    bool sameHost = isSampler
                        ? ReferenceEquals(entry.DeltaHostSamplers[index], hostSampler)
                        : ReferenceEquals(entry.DeltaHosts[index], hostTexture);
                    entry.RecordDelta(
                        index,
                        isSampler ? null : texturePool.PeekForBindingDelta(index, out _),
                        texture,
                        hostTexture,
                        isSampler ? samplerPool?.GetCachedItem(index) : null,
                        hostSampler,
                        replacing: true);
                    changed++;
                    if (sameHost)
                    {
                        continue;
                    }

                    int runEnd = runStart + runCount;''')
    once(path, '''                    _deltaRunSamplers[runCount] = hostSampler;
                    runCount++;
                    changed++;''',
         '''                    _deltaRunSamplers[runCount] = hostSampler;
                    runCount++;''')


def apply(source):
    for name, digest in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest, name

    prioritize_expensive_variants(source / JOURNAL)
    retain_expensive_variants(source / JOURNAL)
    start_replay_when_cache_is_ready(source / JOURNAL)
    note_slow_default_pipeline(source / PROGRAM)
    skip_unchanged_array_descriptors(source / ARRAY_CACHE)
    return [source / name for name in (JOURNAL, PROGRAM, ARRAY_CACHE)]
