"""Preserve expensive first-use timings and replay them earlier."""

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
    note_slow_default_pipeline(source / PROGRAM)
    skip_unchanged_array_descriptors(source / ARRAY_CACHE)
    return [source / name for name in (JOURNAL, PROGRAM, ARRAY_CACHE)]
