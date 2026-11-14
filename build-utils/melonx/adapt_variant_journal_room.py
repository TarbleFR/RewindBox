"""A full pipeline variant journal gives up, for a new state, the first state of its eviction order not met in the session
(one a next load would drop anyway, then met in the fewest sessions, longest ago, lowest ranked), and a full file is
compacted from memory: no new state and no refresh line is dropped silently, at the same 2048 states (every title).

Evidence (private core logs of IPA 737-740, "pipelineVariants" loaded and summary lines; counts only):
- PipelineVariantJournal.NoteLate stops recording a new state once the journal holds MaxRecords (2048) states ("if
  (_records.Count >= MaxRecords) return", after the counters: "late creations ... new" also counts the states lost).
  Hogwarts Legacy loaded 1517, 1613, 1654, 1684, 1748, 1791, 1811, 1809, 1825 then 1933 states at sessions 4 to 13. IPA
  740 (pid 5954): room for 115, "new 278": at least 163 states created late on the render thread were not recorded, and
  are created late again in later sessions (late creations up to 975 ms per session; about 3.5 ms each). Super Smash
  Bros. Ultimate: 2016 states loaded (room 32) and "new 139" (pid 4302): at least 107 lost; 2034 loaded (room 14) and
  "new 265" (pid 5159, second game): at least 251 lost. The loss is exact in one count: the launch after pid 4302 read
  2778 lines = 2016 compacted states + 730 refresh lines of replays served + 32 new states recorded.
- A second silent bound: Append returns without writing once the file would pass MaxFileBytes (2 MiB). A session writes
  the states compacted at its load, a refresh line per replay a draw used and a line per state noted late: 2778, 2920 and
  3313 lines read at the IPA 740 launches (3313 lines fitted in 2 MiB: 633 bytes per line at most on average), about 1.7
  x MaxRecords lines for a full journal (about 3500 lines, 2.2 MB at that average). Past 2 MiB the refresh lines are lost
  (a used state then ages out after 8 sessions as if unused) and so are new states. Not observed in the logs (no line
  size is logged): a bound of the code.
- Memory: device memory available fell to 4-6 % in play (Hogwarts, IPA 740); every recorded state is replayed at the next
  launch and stays alive with its program (adapt_variant_replay_all). The number of states, and so of replayed pipelines,
  is not raised: 2048 as now (the prototype's 4096 states are dropped).

Change (PipelineCacheManager.cs, PipelineVariantJournal):
- Eviction. When the journal is full, a new state (or one given up earlier this session and met again) takes the place of
  the first state of the eviction order (EvictionOrder) that the journal holds and that was not met this session: first
  those a next load would drop anyway (last met 8 sessions ago), then the others, met in fewer sessions first, then met
  longest ago, then the lowest ranked (Compare). A state met this session is never given up; when every state held was
  met this session the new one is counted "not recorded". The order is computed once at the load (background thread,
  _victims, the loaded states) and consumed from its end under the journal lock (O(1) per eviction, 2048 pops per session
  at most). A state given up stays known (_evicted): a draw that creates it late, or a draw that binds its replay, brings
  it back with its history. The replay plan is not changed: a given-up state still replays if scheduled.
- The load trims an over-full journal with the last session's eviction order (was: by rank), so it gives up exactly the
  states that session gave up whose lines are still in the file: a state recorded in a session is never dropped at the
  next load for a state of an older session ("given up for newer states" in the loaded line).
- File. MaxFileBytes 4 MiB (was 2 MiB). A line that would pass it compacts the file from memory (every state held and
  every failure marker, under the file lock; the journal lock only copies the states' fields) instead of being dropped;
  lines encoded before the compaction carry an older generation and are not appended (their content is in it). A
  compaction holds at most 2048 x 1483 bytes (the codec's largest variant, 1444 bytes) + 18432 x 28 bytes of failure
  markers (9 sessions of at most 2048 refused replays) + 16 = 3 553 296 bytes, 84.7 % of 4 MiB: it always leaves room
  for 432 lines of the largest size. One leaving less than an eighth of the file free (not reachable within these
  bounds) is the session's last; a line then not written is counted. A failed compaction stops the journal, as a failed
  append does (logged).
- Counted: the summary adds "Journal: N of 2048 states, given up for newer states E (at the load L), not recorded R,
  compactions C, lines not written W"; NoteLate counts a state refused before the journal is read or past the session's
  note bound as not recorded.
Unchanged: 2048 states, MaxReplaysPerSession = MaxRecords (adapt_variant_replay_all), the last 8 sessions, the 120 s compile
budget per launch, two replays in flight (one when costly), the hold while the device has 8 % of its memory or less,
strikes and evictions of failing states, the replay order (more sessions, then met earlier, then costlier).

Bound (from the logs, not measured): the states a session creates late that the next launches meet again, at about 3.5 ms
each on the render thread (975 ms for 281 late creations in IPA 740), recorded where they were lost: at least 163
(Hogwarts, IPA 740), 107 and 251 (SSBU). The states given up are the least likely to be met (not met this session, met in
the fewest sessions, longest ago): 31 % of the replayed states were not used in IPA 740 (1324 used of 1928, the last
summary of pid 5954). Cost: memory unchanged in pipelines (2048 replays at most, as now); on the heap, the new states
recorded beyond the loaded room (a record and its variant, about 0.6 KB at the average line: about 100 KB for Hogwarts'
163), the states given up kept known until the session ends (they were in memory already) and a list of at most 2048
references; one sort of at most 2048 states at the load, off the startup thread; the file up to 4 MiB on disk and read
once at launch (was 2 MiB); a compaction, if any, writes at most 3.6 MB on a thread-pool thread (none expected in a
session of 3500 lines of 633 bytes).

Expected on the device (pipelineVariants lines): "Journal: 2048 of 2048 states, given up for newer states E" with E about
the session's "new" beyond the loaded room, "not recorded 0", "lines not written 0"; at the next launch "given up for newer
states" in the loaded line when no compaction ran, "late creations ... new" lower in an area visited the session before.
Not measured on an iPhone; no FPS, heat or stability gain claimed. Runs before adapt_queued_variant_record (which takes this
adapter's post-image of PipelineCacheManager.cs). Rollback: drop this adapter from prepare_embedded.py and ORDER (a
journal file of up to 4 MiB is then read whole and trimmed by rank at the next load; appends stop at 2 MiB as before).
Fail closed on drift.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
# Core bacdcacd preparation (IPA 745); no adapter of the IPA 746 lot edits this file.
BASELINE = {MANAGER: '45ee8376556d63c9f026f12e9ce75d5f69658242b2f5f225a82222dd394415af'}

COMMENT_OLD = '''    // (ShaderCollection.TryWaitForBackgroundGraphicsPipeline) instead of creating a second one. Bounded: 2048 variants
    // and 2 MiB on disk, variants of the last 8 sessions only, every one of them replayed (adapt_variant_replay_all)
'''
COMMENT_NEW = '''    // (ShaderCollection.TryWaitForBackgroundGraphicsPipeline) instead of creating a second one. Bounded: 2048 variants
    // (adapt_variant_journal_room: a full journal gives up the first state of EvictionOrder not met in the session for a
    // new one) and 4 MiB on disk (a full file is compacted from memory), variants of the last 8 sessions only, every one
    // of them replayed (adapt_variant_replay_all)
'''

FILE_BOUND_OLD = '''        internal const long MaxFileBytes = 2L * 1024 * 1024;
'''
FILE_BOUND_NEW = '''        // RewindBox (adapt_variant_journal_room): 4 MiB (was 2 MiB, which a full journal's session passes: about 3500 lines).
        // A compaction holds at most MaxRecords lines of the largest variant (1444 bytes, 1483 with its framing) and the
        // failure markers of 9 sessions of at most MaxReplaysPerSession refused replays (28 bytes each): 3 553 296 bytes, so
        // it always leaves room for lines.
        internal const long MaxFileBytes = 4L * 1024 * 1024;
'''

FIELDS_OLD = '''        private long _replayTicksStarted;

        // Counters of this session (summary lines).
'''
FIELDS_NEW = '''        private long _replayTicksStarted;
        // RewindBox (adapt_variant_journal_room): the states loaded for this session in eviction order (the first to give
        // up at the end), the states given up this session (still known: one met again comes back with its history), and
        // the file's generation (a compaction writes every state from memory: a line encoded before it is not appended).
        private List<Record> _victims;
        private readonly Dictionary<(ulong, ulong), Record> _evicted = new();
        private int _fileGeneration;
        private bool _fileFull;

        // Counters of this session (summary lines); the journal's own bounds (adapt_variant_journal_room) first.
        internal int Evicted, GivenUpAtLoad, NotRecorded, Compactions, LinesNotWritten;
'''

TRIM_OLD = '''            kept.Sort(Compare);

            if (kept.Count > MaxRecords)
            {
                kept.RemoveRange(MaxRecords, kept.Count - MaxRecords);
                rewrite = true;
            }
'''
TRIM_NEW = '''            // RewindBox (adapt_variant_journal_room): over the bound, the states go in the last session's eviction order (was:
            // the lowest ranked), so the load keeps what that session kept: the states it gave up for newer ones (their
            // lines stay in the file until a compaction), never a state it met.
            int givenUp = Math.Max(0, kept.Count - MaxRecords);

            if (givenUp != 0)
            {
                kept.Sort((a, b) => EvictionOrder(a, b, _session - 1));
                kept.RemoveRange(0, givenUp);
                rewrite = true;
            }

            kept.Sort(Compare);

            // RewindBox (adapt_variant_journal_room): this session's eviction order of the loaded states, built off the
            // startup and render threads; the first state to give up is at the end.
            List<Record> victims = new(kept);
            victims.Sort((a, b) => EvictionOrder(b, a, _session));
'''

PUBLISH_OLD = '''                Dropped = failed + stale + invalid;
                _loaded = true;
'''
PUBLISH_NEW = '''                Dropped = failed + stale + invalid;
                GivenUpAtLoad = givenUp; // RewindBox (adapt_variant_journal_room)
                _victims = victims;
                _loaded = true;
'''

LOADED_OLD = '''                $"{RecentSessions} sessions, {invalid} unreadable; {read} lines read) (adapt_pipeline_variant_replay)");
'''
LOADED_NEW = '''                $"{RecentSessions} sessions, {invalid} unreadable, {givenUp} given up for newer states; {read} lines read) " +
                "(adapt_pipeline_variant_replay, adapt_variant_journal_room)");
'''

NOTE_DECLARE_OLD = '''            ulong id = Checksum64(variant);
            var key = (program, id);
            Record record;
            byte[] line;
'''
NOTE_DECLARE_NEW = '''            ulong id = Checksum64(variant);
            var key = (program, id);
            Record record;
            int generation; // RewindBox (adapt_variant_journal_room): the file generation its line is encoded in
            byte[] line;
'''

NOTE_GATE_OLD = '''                if (_stopped || !_loaded || _notedThisSession.Count >= 4 * MaxRecords || !_notedThisSession.Add(key))
                {
                    return;
                }

                bool known = _records.TryGetValue(key, out record);
'''
NOTE_GATE_NEW = '''                if (_stopped || !_loaded || _notedThisSession.Count >= 4 * MaxRecords || !_notedThisSession.Add(key))
                {
                    // RewindBox (adapt_variant_journal_room): a state not noted yet this session and refused here (met before
                    // the journal is read, or past the session's note bound) is counted as not recorded.
                    if (!_stopped && !_notedThisSession.Contains(key))
                    {
                        NotRecorded++;
                    }

                    return;
                }

                // RewindBox (adapt_variant_journal_room): a state given up earlier this session is still known (back below).
                bool known = _records.TryGetValue(key, out record) || _evicted.TryGetValue(key, out record);
'''

NOTE_KNOWN_OLD = '''                if (known)
                {

                    if (record.LastSession != _session)
                    {
                        record.Sessions = (ushort)Math.Min(ushort.MaxValue, record.Sessions + 1);
                        record.LastSession = _session;
                    }
'''
NOTE_KNOWN_NEW = '''                if (known)
                {
                    // RewindBox (adapt_variant_journal_room): given up earlier this session, met again: back in the journal
                    // with its history, in the place of another state not met this session.
                    if (_evicted.ContainsKey(key))
                    {
                        if (!MakeRoom())
                        {
                            NotRecorded++;
                            return;
                        }

                        _evicted.Remove(key);
                        _records[key] = record;
                    }

                    if (record.LastSession != _session)
                    {
                        record.Sessions = (ushort)Math.Min(ushort.MaxValue, record.Sessions + 1);
                        record.LastSession = _session;
                    }
'''

NOTE_FULL_OLD = '''                    if (_records.Count >= MaxRecords)
                    {
                        return;
                    }
'''
NOTE_FULL_NEW = '''                    // RewindBox (adapt_variant_journal_room): a full journal gives up the first state of its eviction order not
                    // met this session (was: the new state was dropped, uncounted); every state held met this session:
                    // counted, not recorded.
                    if (!MakeRoom())
                    {
                        NotRecorded++;
                        return;
                    }
'''

NOTE_WRITE_OLD = '''                line = Encode(record, KindVariant);
            }

            ThreadPool.UnsafeQueueUserWorkItem(_ => Append(line), null);
        }
'''
NOTE_WRITE_NEW = '''                line = Encode(record, KindVariant);
                generation = _fileGeneration;
            }

            ThreadPool.UnsafeQueueUserWorkItem(_ => Append(line, generation), null);
        }
'''

USED_OLD = '''            byte[] line = null;

            lock (_lock)
            {
                ReadyBeforeUse++;

                if (record.LastSession != _session)
                {
                    record.Sessions = (ushort)Math.Min(ushort.MaxValue, record.Sessions + 1);
                    record.LastSession = _session;
                    line = Encode(record, KindVariant);
                }
            }

            if (line != null)
            {
                ThreadPool.UnsafeQueueUserWorkItem(_ => Append(line), null);
            }
'''
USED_NEW = '''            byte[] line = null;
            int generation = 0;

            lock (_lock)
            {
                ReadyBeforeUse++;

                // RewindBox (adapt_variant_journal_room): a replayed state given up earlier this session, used by a draw: back
                // in the journal, in the place of another state not met this session.
                var key = (record.Program, record.Id);

                if (_evicted.ContainsKey(key))
                {
                    if (!MakeRoom())
                    {
                        NotRecorded++;
                        return;
                    }

                    _evicted.Remove(key);
                    _records[key] = record;
                }

                if (record.LastSession != _session)
                {
                    record.Sessions = (ushort)Math.Min(ushort.MaxValue, record.Sessions + 1);
                    record.LastSession = _session;
                    line = Encode(record, KindVariant);
                    generation = _fileGeneration;
                }
            }

            if (line != null)
            {
                ThreadPool.UnsafeQueueUserWorkItem(_ => Append(line, generation), null);
            }
'''

COMPLETED_OLD = '''            byte[] line = null;

            lock (_lock)
            {
                _inFlight--;
'''
COMPLETED_NEW = '''            byte[] line = null;
            int generation;

            lock (_lock)
            {
                _inFlight--;
                generation = _fileGeneration; // RewindBox (adapt_variant_journal_room)
'''

COMPLETED_WRITE_OLD = '''                Append(line);
            }

            Pump();
'''
COMPLETED_WRITE_NEW = '''                Append(line, generation);
            }

            Pump();
'''

SUMMARY_OLD = '''                    $"{_inFlight}, still planned {planned} of {Planned} (adapt_pipeline_variant_replay).";
'''
SUMMARY_NEW = '''                    $"{_inFlight}, still planned {planned} of {Planned}. Journal: {_records.Count} of {MaxRecords} states, given up for " +
                    $"newer states {Evicted} (at the load {GivenUpAtLoad}), not recorded {NotRecorded}, compactions {Compactions}, " +
                    $"lines not written {LinesNotWritten} (adapt_pipeline_variant_replay, adapt_variant_journal_room).";
'''

APPEND_OLD = '''        private void Append(byte[] line)
        {
            lock (_fileLock)
            {
                try
                {
                    bool header = _rewriteHeader || !File.Exists(_path) || new FileInfo(_path).Length < HeaderBytes;

                    if (!header && new FileInfo(_path).Length + line.Length > MaxFileBytes)
                    {
                        return; // full until the next launch compacts it
                    }
'''
APPEND_NEW = '''        private void Append(byte[] line, int generation)
        {
            lock (_fileLock)
            {
                try
                {
                    // RewindBox (adapt_variant_journal_room): encoded before the last compaction, which holds its content.
                    if (generation != _fileGeneration)
                    {
                        return;
                    }

                    bool header = _rewriteHeader || !File.Exists(_path) || new FileInfo(_path).Length < HeaderBytes;

                    if (!header && new FileInfo(_path).Length + line.Length > MaxFileBytes)
                    {
                        // RewindBox (adapt_variant_journal_room): full: compacted from memory, this line's content included
                        // (was: dropped until the next launch). After a compaction that left less than an eighth of the file
                        // free (not reachable within MaxFileBytes' bound), a line that does not fit is counted.
                        if (_fileFull)
                        {
                            LinesNotWritten++;
                        }
                        else
                        {
                            Compact();
                        }

                        return;
                    }
'''

REWRITE_OLD = '''        // Compaction: the kept variants only, written to a temporary file then renamed over the journal.
        private void Rewrite(List<Record> kept)
'''
REWRITE_NEW = '''        // RewindBox (adapt_variant_journal_room): the order in which a full journal gives up a state, the first to go first:
        // states a next load would drop (last met RecentSessions sessions before `current`), then the others not met in
        // `current`, then those met in it; within each, met in fewer sessions, then met longest ago, then the lowest ranked
        // (Compare), then the program. A session gives up in its own order (`current` is that session: its states are never
        // given up); a load trims with the last session's order, so it gives up what that session gave up.
        internal static int EvictionOrder(Record a, Record b, uint current)
        {
            int order = Tier(a, current).CompareTo(Tier(b, current));

            if (order == 0)
            {
                order = a.Sessions.CompareTo(b.Sessions);
            }

            if (order == 0)
            {
                order = a.LastSession.CompareTo(b.LastSession);
            }

            if (order == 0)
            {
                order = Compare(b, a);
            }

            return order != 0 ? order : a.Program.CompareTo(b.Program);
        }

        private static int Tier(Record record, uint current) =>
            record.LastSession >= current ? 2 : (ulong)record.LastSession + RecentSessions <= current ? 0 : 1;

        // RewindBox (adapt_variant_journal_room): room for one more state (under _lock). A full journal gives up the next
        // state of this session's eviction order that it still holds and that was not met this session; false when none is
        // left (every state it holds was met this session). Each loaded state is examined once per session.
        private bool MakeRoom()
        {
            while (_records.Count >= MaxRecords)
            {
                if (_victims == null || _victims.Count == 0)
                {
                    return false;
                }

                Record victim = _victims[^1];
                _victims.RemoveAt(_victims.Count - 1);
                var key = (victim.Program, victim.Id);

                if (victim.LastSession < _session && _records.TryGetValue(key, out Record held) && ReferenceEquals(held, victim))
                {
                    _records.Remove(key);
                    _evicted[key] = victim;
                    Evicted++;
                }
            }

            return true;
        }

        // RewindBox (adapt_variant_journal_room): a full file in a session is rewritten from memory, under the file lock (no
        // line is appended meanwhile): every state the journal holds and every failure marker, as a load would keep them.
        // The journal lock only copies their fields and moves the generation on: a line encoded before it is not appended.
        // An I/O failure reaches Append's handler (the journal stops, logged).
        private void Compact()
        {
            List<Record> records;
            List<(ulong Program, ulong Id, uint Session, byte Strikes)> markers;

            lock (_lock)
            {
                records = new(_records.Count);

                foreach (Record record in _records.Values)
                {
                    records.Add(new Record
                    {
                        Program = record.Program,
                        Id = record.Id,
                        LastSession = record.LastSession,
                        Sessions = record.Sessions,
                        FirstSeenMs = record.FirstSeenMs,
                        CostMs = record.CostMs,
                        Variant = record.Variant,
                    });
                }

                markers = new(_failed.Count);

                foreach (var marker in _failed)
                {
                    markers.Add((marker.Key.Item1, marker.Key.Item2, marker.Value.Session, marker.Value.Strikes));
                }

                _fileGeneration++;
                Compactions++;
            }

            string temporary = _path + ".tmp";

            using (FileStream stream = new(temporary, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                stream.Write(Header());

                foreach (Record record in records)
                {
                    stream.Write(Encode(record, KindVariant));
                }

                foreach (var marker in markers)
                {
                    stream.Write(EncodeFailure(marker.Program, marker.Id, marker.Session, marker.Strikes));
                }
            }

            File.Move(temporary, _path, overwrite: true);
            _rewriteHeader = false;
            _fileFull = new FileInfo(_path).Length > MaxFileBytes - MaxFileBytes / 8;
        }

        // Compaction at a load: the kept variants only, written to a temporary file then renamed over the journal.
        private void Rewrite(List<Record> kept)
'''

PAIRS = ((COMMENT_OLD, COMMENT_NEW), (FILE_BOUND_OLD, FILE_BOUND_NEW), (FIELDS_OLD, FIELDS_NEW), (TRIM_OLD, TRIM_NEW),
         (PUBLISH_OLD, PUBLISH_NEW), (LOADED_OLD, LOADED_NEW), (NOTE_DECLARE_OLD, NOTE_DECLARE_NEW),
         (NOTE_GATE_OLD, NOTE_GATE_NEW), (NOTE_KNOWN_OLD, NOTE_KNOWN_NEW), (NOTE_FULL_OLD, NOTE_FULL_NEW),
         (NOTE_WRITE_OLD, NOTE_WRITE_NEW), (USED_OLD, USED_NEW), (COMPLETED_OLD, COMPLETED_NEW),
         (COMPLETED_WRITE_OLD, COMPLETED_WRITE_NEW), (SUMMARY_OLD, SUMMARY_NEW), (APPEND_OLD, APPEND_NEW),
         (REWRITE_OLD, REWRITE_NEW))


def apply(source):
    path = source / MANAGER
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, MANAGER
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
