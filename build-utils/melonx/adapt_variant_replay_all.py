"""Every recorded pipeline state is prepared at launch: the 512-replay session cap goes (Core 725).

IPA 724, Hogwarts Legacy (pid 49375, Core 723, journal at the pauses of 23:01:58 and 23:02:29 UTC): "replays built 512
(compile 2273 ms, queue wait 30149 ms), refused 0, temporary failures 0, cancelled 0, skipped 2, held for memory 0, in
flight 0, still planned 843 of 1357", and "late creations left 869 (4955 ms): new 160, planned not built yet 701, built
but missed 8". The replay stopped at PipelineVariantJournal.MaxReplaysPerSession (512) with the compile budget barely
used (2.3 s of 120 s) and no memory hold: 701 of the 869 states the render thread then had to create itself were
recorded states still waiting behind the cap (5.7 ms each on average; the performance journal shows windows with 1.3 to
3.7 s of pipeline builds between 73 and 106 s of play).

Change (PipelineCacheManager.cs only, every title): MaxReplaysPerSession is the journal's own bound, MaxRecords (2048
states of the last 8 sessions, 2 MiB): every state the journal holds is scheduled. Unchanged: the 120 s compile budget,
two replays in flight (one once they average 300 ms), the low priority on the existing background queue, the hold while
the device has 8 % of its memory or less, strikes and evictions, and a draw creating or joining the state it needs.
At 4.4 ms a replay (IPA 724), 1 357 states are about 6 s of background compilation.
Not measured on an iPhone. Fail closed on drift: the file must be the Core 723 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
BASELINE = {
    MANAGER: 'd10d5ad7a3eda7b5dc92ae2ac822d972bc1b532f45918990730c43f8eb756138',
}

CAP_OLD = '''        internal const int MaxReplaysPerSession = 512;
'''
CAP_NEW = '''        // RewindBox (adapt_variant_replay_all): every recorded state is replayed; the journal's own bound is the cap
        // (IPA 724: 843 of 1357 states were left planned at 512 and 701 of them were created late by the render thread).
        internal const int MaxReplaysPerSession = MaxRecords;
'''

COMMENT_OLD = '''    // and 2 MiB on disk, variants of the last 8 sessions only, 512 replays and 120 s of compile time per session, two in
'''
COMMENT_NEW = '''    // and 2 MiB on disk, variants of the last 8 sessions only, every one of them replayed (adapt_variant_replay_all)
    // within 120 s of compile time per session, two in
'''

PAIRS = ((COMMENT_OLD, COMMENT_NEW), (CAP_OLD, CAP_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[MANAGER], old, new)
    return list(paths.values())
