"""A pause rewrites the main pipeline cache only for 8 MiB of new content, as play does (Core 727 candidate).

IPA 724, Hogwarts Legacy (pid 49375, Core 723): paused at t=192-196 s, resumed at t=197; the pause checkpoint wrote
"pipelineCache written: main 793,10 MiB in 10909 ms" for "+1,06 MiB since the file was written 191 s ago" and held the
main cache lock while the game resumed: 0-0.3 FPS from t=197 to 205 (presentation gaps of 6 461 and 3 880 ms), the
per-second journal lines missing. The file is rewritten whole (the data of every library is serialized into a buffer
of the cache's size, then written), so the cost follows the cache's size, not what is new in it.

Change (PipelineCacheManager.cs, MainGrowthWorthWriting, every title): on pause the file is rewritten when the cache
holds MainCheckpointMinimumGrowthBytes (8 MiB) more than the file, the play rule without its 10-minute clause; play is
unchanged (8 MiB, or any growth 10 min after the last write), so less than 8 MiB of new content is still written by a
play checkpoint within 10 minutes, and at the close as before. What a kill in the background loses is at most 8 MiB of
libraries, compiled again at the next launch, whose states the variant journal replays.
Not measured on an iPhone. Fail closed on drift: the file must be the Core 725 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
BASELINE = {
    MANAGER: 'b4e716a3ec97718ce67ddb99dde69aa500160b4559196bf3ba0e8754478c9835',
}

RULE_OLD = '''            bool write = pause
                ? grown > 0
                : grown >= MainCheckpointMinimumGrowthBytes || (grown > 0 && sinceMs >= MainCheckpointStaleMs);
'''
RULE_NEW = '''            // RewindBox (adapt_pause_checkpoint_growth): a pause rewrites the whole file only for 8 MiB of new content (IPA 724:
            // 793 MiB in 10.9 s for +1.06 MiB, the game resumed into it); smaller growth waits for a play checkpoint or the close.
            bool write = pause
                ? grown >= MainCheckpointMinimumGrowthBytes
                : grown >= MainCheckpointMinimumGrowthBytes || (grown > 0 && sinceMs >= MainCheckpointStaleMs);
'''

PAIRS = ((RULE_OLD, RULE_NEW),)


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[MANAGER], old, new)
    return list(paths.values())
