"""The pipeline variant journal holds 4096 states (was 2048), in 8 MiB on disk at most (was 4 MiB), and a load reads no
more than that bound: a title whose last 8 sessions drew more than 2048 states no longer gives up recorded states for
new ones (every title).

Evidence (private core logs of IPA 816-821, "pipelineVariants" loaded and summary lines; counts and durations only):
- IPA 821, Hogwarts Legacy, session 40 of the title (174 s of play): "2028 variants of 426 programs planned (dropped: 33
  older than 8 sessions, 0 given up for newer states; 3330 lines read)", then at the close "Journal: 2048 of 2048 states,
  given up for newer states 378, not recorded 0, compactions 0, lines not written 0", with "late creations: new 211,
  planned not built yet 853" and "built for skipped draws 502". The 378 are not states the session failed to record
  (not recorded 0): they are states loaded for it that it had not met yet, removed one by one to make room.
- The cause is one constant: PipelineVariantJournal.MaxRecords = 2048, a count of states per title (one journal file
  per title; not a bound per session, per program, in lines or in bytes: the file bound, 4 MiB, was not reached, no
  compaction and no line lost). The session started with room for 20 and met 398 states the journal did not know (211
  created late by a draw, the others built for skipped draws): 398 - 20 = 378 evictions (MakeRoom), and 2028 + 398 =
  2426 states known at the close for 2048 places.
- Nothing old was left to give up instead. The load had already dropped the 33 states not met for 8 sessions, so every
  one of the 2028 states had been drawn in the title's sessions 32 to 39; the eviction order (adapt_variant_journal_room)
  already takes first the states a next load would drop, then those met in the fewest sessions, then longest ago. The
  retention rule was doing its work; the count bound was cutting into what the rule keeps.
- The same journal was full at the close of 5 of the 7 sessions logged before it (IPA 816-821, sessions 35 to 39): 36,
  3, 105, 1 and 15 states given up (91 more at session 38's load), 1989 to 2048 states loaded at each launch. Super
  Smash Bros. Ultimate held 1321 to 1506 states in those logs, under the bound (2034 in IPA 740, with 251 lost then).
- A given-up state is not replayed at the next launch: where the player returns to it, a draw creates it late on the
  render thread (IPA 821: 1064 late creations, 18994 ms) or skips until a worker has built it (2027 draws skipped).
- A state's cost: its line is the variant (PipelineState.WriteVariant: 196 bytes of fields, 16 per vertex attribute, 12
  per binding, 40 per colour attachment, 16 to 20 more: about 360 to 480 bytes for 5 attributes, 2 bindings and 1 to 4
  targets, 1444 at most) plus 39 bytes of framing; 3313 lines fitted in 2 MiB in IPA 740 (633 bytes a line at most on
  average). On the heap, the variant, a Record and its table entries: about the line's size again.

Change (PipelineCacheManager.cs, PipelineVariantJournal; every title):
- MaxRecords 4096. The bound stays a safety limit; what a title keeps is decided by RecentSessions (the states its
  last 8 sessions drew), and a full journal still gives up in EvictionOrder. 4096 is 1.69 times the 2426 states of the
  session above and leaves room for 1670 more: four more sessions that each bring as many new states as that one
  (398, the most of the 7 sessions logged; their median is 52), before any state leaves by age.
  MaxReplaysPerSession follows (it is MaxRecords since adapt_variant_replay_all): every recorded state is still
  scheduled, in the same order (more sessions first), within the same 120 s of compile time and the same memory hold.
- MaxFileBytes 8 MiB. Same rule as adapt_variant_journal_room: a compaction holds at most 4096 x 1483 bytes + 9 x 4096 x
  28 bytes of failure markers + 16 = 7 106 576 bytes, 84.7 % of 8 MiB, under the seven eighths that would make it the
  session's last. At the measured average line the 4096 states are 2.6 MB at most and a session's file about twice that.
- Load reads MaxFileBytes at most (ReadBounded; was File.ReadAllBytes, whatever the file's size). No build writes a
  longer file; of a longer one (foreign or damaged) the lines before the bound are read (they are framed and
  checksummed), and the load compacts it. The loaded line says "file cut at its bound" then.
- The loaded line adds how the kept states were reused: "N met in one session only; last met 1 to 8 sessions ago:
  a/b/c/d/e/f/g/h" (two counters at the load, no state kept for them). The logs do not tell how many of the states kept
  are never drawn again; these counts will, before RecentSessions or the eviction order is changed on evidence.
The file's format is unchanged (magic, version 1, schema, framed lines): this build reads the journals on the devices as
they are, and the 378 states session 40 gave up are still in that file (their lines stay until a compaction), so the
first launch of this build loads them. A build without this adapter reads this build's file whole and trims it to
2048 states in the last session's eviction order, as it does today (rollback: drop this adapter from
prepare_embedded.py and ORDER). A file of another version, schema or magic is ignored and restarts empty, as before.

Bounds. Disk: 8 MiB per title (was 4), checked before every append. Heap: at most 4096 states held and 4096 given up in
the session (each about 0.5 KiB, 1.6 KiB at most: 2.5 MB usually, 13 MB in the worst case; half of that before) and two
sets of at most 16 384 keys (the session's noted states). Load: one read of at most 8 MiB on the journal's thread-pool
thread, off the startup path as before, then two sorts of at most 4096 states. On the gate's host a full journal of
4096 usual states after a session that refreshed each (3.8 MB) loads in 19 to 30 ms, its compaction included (10 ms for
2048), allocates 10.8 MB and holds 2.5 MB (616 bytes a state); the offers of 426 programs sort the ready list for 50
to 85 ms in all, on thread-pool threads (host times, not an iPhone's). A compaction writes a temporary file beside the
journal before replacing it, as before: up to twice the bound on disk for that moment.
Pipelines: a replay builds every recorded state, so up to 4096 pipelines instead of 2048 when a title has that many
(Hogwarts: 2426 at the next launch, 378 more than today). The replay order builds the states met in the most sessions
first and stops while the device has 8 % of its memory or less (IPA 821, Hogwarts: 35 % available 30 s into the
session, 13 % at 60 s, 8 % from 120 s on).

What else bounds the replays at a launch (read, not changed; none is a count below the journal's size): 120 s of
replay compile time per session (ReplayWorkBudgetMs); two replays in flight, one once they average 300 ms; none while
the device has 8 % of its memory or less, resumed only by a later offer, a replay's completion or the build summary
(after a compilation of 50 ms or more, once a minute at most); with Hogwarts' policy, none before the main cache's
snapshot is merged (193 ms in IPA 821); and a program must come from the shader disk cache with its modules compiled to
offer its states. In IPA 821 the two replays in flight stayed queued behind the cached programs' warm-ups for the whole
session (built 2 of 2028); adapt_render_thread_compile_relief gave them their own queue since.

Expected on the device (pipelineVariants lines): at the first Hogwarts launch, "loaded ... 0 given up for newer states"
with more than 2048 variants planned when the last session of the previous build gave some up; in every summary
"Journal: N of 4096 states, given up for newer states 0 (at the load 0), not recorded 0, compactions 0, lines not
written 0". Not measured on an iPhone; no FPS, heat or memory figure is claimed. Fail closed on drift: the file must be
the Core 825 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
# Core 825 preparation (after adapt_shader_code_table_load; no later adapter edits this file).
BASELINE = {MANAGER: '1d3707317c60f8b67527178fcb2f0c93f0a68c2c435a9417fd169d9371b81ac2'}

COMMENT_OLD = '''    // (ShaderCollection.TryWaitForBackgroundGraphicsPipeline) instead of creating a second one. Bounded: 2048 variants
    // (adapt_variant_journal_room: a full journal gives up the first state of EvictionOrder not met in the session for a
    // new one) and 4 MiB on disk (a full file is compacted from memory), variants of the last 8 sessions only, every one
'''
COMMENT_NEW = '''    // (ShaderCollection.TryWaitForBackgroundGraphicsPipeline) instead of creating a second one. Bounded: 4096 variants
    // (adapt_variant_journal_capacity; adapt_variant_journal_room: a full journal gives up the first state of
    // EvictionOrder not met in the session for a new one) and 8 MiB on disk (a full file is compacted from memory, a load
    // reads no more), variants of the last 8 sessions only, every one
'''

BOUNDS_OLD = '''        internal const int MaxRecords = 2048;
        // RewindBox (adapt_variant_journal_room): 4 MiB (was 2 MiB, which a full journal's session passes: about 3500 lines).
        // A compaction holds at most MaxRecords lines of the largest variant (1444 bytes, 1483 with its framing) and the
        // failure markers of 9 sessions of at most MaxReplaysPerSession refused replays (28 bytes each): 3 553 296 bytes, so
        // it always leaves room for lines.
        internal const long MaxFileBytes = 4L * 1024 * 1024;
'''
BOUNDS_NEW = '''        // RewindBox (adapt_variant_journal_capacity): 4096 states (was 2048). A safety limit: what a title keeps is decided
        // by RecentSessions (the states its last 8 sessions drew). IPA 821, Hogwarts Legacy: 2028 states loaded, each met in
        // one of the last 8 sessions, and 398 new ones in 174 s of play: 2426 states for 2048 places, 378 given up. A state
        // costs its line on disk (its variant and 39 bytes: 1483 at most, about 0.5 KiB usually) and as much on the heap.
        internal const int MaxRecords = 4096;
        // RewindBox (adapt_variant_journal_room, adapt_variant_journal_capacity): 8 MiB (4 MiB for 2048 states). A compaction
        // holds at most MaxRecords lines of the largest variant (1444 bytes, 1483 with its framing) and the failure markers
        // of 9 sessions of at most MaxReplaysPerSession refused replays (28 bytes each): 7 106 576 bytes, so it always
        // leaves room for lines. A load reads MaxFileBytes at most (ReadBounded).
        internal const long MaxFileBytes = 8L * 1024 * 1024;
'''

LOCALS_OLD = '''            int read = 0, invalid = 0, stale = 0, failed = 0;
            bool rewrite = false;
'''
LOCALS_NEW = '''            int read = 0, invalid = 0, stale = 0, failed = 0;
            bool rewrite = false;
            bool cut = false; // RewindBox (adapt_variant_journal_capacity): the file is longer than MaxFileBytes
'''

READ_OLD = '''                    byte[] data = File.ReadAllBytes(_path);
'''
READ_NEW = '''                    // RewindBox (adapt_variant_journal_capacity): MaxFileBytes at most (was: the whole file, whatever its size);
                    // a longer file is compacted below.
                    byte[] data = ReadBounded(_path, out cut);
                    rewrite |= cut;
'''

REUSE_OLD = '''            rewrite |= failed != 0 || stale != 0;
'''
REUSE_NEW = '''            rewrite |= failed != 0 || stale != 0;

            // RewindBox (adapt_variant_journal_capacity): how the kept states were reused, for the loaded line: those met in
            // one session only, and the states by the number of sessions since they were last met (1 to RecentSessions).
            int metOnce = 0;
            int[] ages = new int[RecentSessions];

            foreach (Record record in kept)
            {
                metOnce += record.Sessions <= 1 ? 1 : 0;
                ages[(int)Math.Clamp((long)_session - record.LastSession, 1, RecentSessions) - 1]++;
            }
'''

LOADED_OLD = '''                $"{RecentSessions} sessions, {invalid} unreadable, {givenUp} given up for newer states; {read} lines read) " +
                "(adapt_pipeline_variant_replay, adapt_variant_journal_room)");
'''
LOADED_NEW = '''                $"{RecentSessions} sessions, {invalid} unreadable, {givenUp} given up for newer states; {read} lines read" +
                $"{(cut ? ", file cut at its bound" : "")}; {metOnce} met in one session only; last met 1 to {RecentSessions} " +
                $"sessions ago: {string.Join("/", ages)}) " +
                "(adapt_pipeline_variant_replay, adapt_variant_journal_room, adapt_variant_journal_capacity)");
'''

HEADER_OLD = '''        private byte[] Header()
        {
'''
HEADER_NEW = '''        // RewindBox (adapt_variant_journal_capacity): the journal's bytes, MaxFileBytes at most. No build writes a longer file
        // (Append, Compact and Rewrite stay under the bound): a longer one is foreign or damaged. Its lines are framed and
        // checksummed, so those before the bound are read as they are, and the load compacts the file.
        private static byte[] ReadBounded(string path, out bool cut)
        {
            using FileStream stream = new(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            long length = stream.Length;

            cut = length > MaxFileBytes;

            byte[] data = new byte[(int)Math.Min(length, MaxFileBytes)];

            stream.ReadExactly(data);

            return data;
        }

        private byte[] Header()
        {
'''

PAIRS = ((COMMENT_OLD, COMMENT_NEW), (BOUNDS_OLD, BOUNDS_NEW), (LOCALS_OLD, LOCALS_NEW), (READ_OLD, READ_NEW),
         (REUSE_OLD, REUSE_NEW), (LOADED_OLD, LOADED_NEW), (HEADER_OLD, HEADER_NEW))


def apply(source):
    path = source / MANAGER
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, MANAGER
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
