"""Pipeline cache (every title): a worker file of a cache's header alone no longer holds the workers' files.

IPA 764 / Core a80b212f, Hogwarts Legacy (private journals, pids 28304 and 28682; docs/melonx-ipa764-journals-2026-11-17.md):
both launches load the same 97.08 MiB main file with "1/1 worker snapshots (0,04 KiB) joined", the MoltenVK statistics
count the same 85 SPIR-V to MSL conversions and the main cache misses the same 47 worker creations, and the file never
grows. In the courtyard, 28682 made 14 conversions, 18 libraries and 30 pipelines (9 then 2 draws skipped while they
were compiled), none of them written: its pause refused to write the main file for +1.17 MiB (8 MiB,
adapt_pause_checkpoint_growth), 28304 was ended by iOS at 87 s, before the first play checkpoint (90 s, 8 MiB). Super
Smash Bros. Ultimate, closed normally, loads no worker file, writes its workers during play (1 to 14 ms for 1 MiB or less)
and its file grows from 121.6 to 128.9 MiB.

Read in the source (PipelineCacheManager.cs): a worker file beside a main snapshot loading in the background joins main and
sets _workerSnapshotsHeldUntil (adapt_pipeline_cache_room, adapt_pipeline_cache_background): no worker writes its file
again until main is written at that generation, so that the joined content is not lost. A file of a cache's header alone
(EmptyCacheBytes: 64; MoltenVK writes 40) holds no pipeline, yet joining it sets that hold, and nothing the session
compiles in the workers is written until main is (a play checkpoint for 8 MiB or after 10 min, a pause for 8 MiB, the
close): a session iOS ends before that keeps nothing, and the next launch reads the same empty file again.

Change (PipelineCacheManager.cs only): at startup, beside a main snapshot (the only case where a worker file joins main
and sets the hold), a worker file of EmptyCacheBytes or less is read as no file: it neither joins main nor holds the
workers, which write their caches during play as when no file is there (Super Smash Bros. Ultimate's case). Without a
main snapshot a worker loads its own file as before.

Not changed: what a cache holds, the pipelines and libraries, the files' format, when and how a cache is written (the
atomic replacement of a file, the play and pause checkpoints, the close), the hold of a worker file that holds pipelines,
the budgets.

Expected on the device: the launch line of Hogwarts Legacy reads "0/0 worker snapshots", the workers write their files
during play, and the next launch makes fewer conversions and misses (85 and 47 at each launch now). No frame rate effect
outdoors is claimed. Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
# The preparation of Core a80b212f (IPA 764).
BASELINE = {MANAGER: '005e7a72450b38167361e135aeeffbfc72c4476506a85ddadbdbfc9225bdcda2'}

OPEN_OLD = '''                MappedSnapshot workerSnapshot = OpenSnapshot(workerCachePaths[index], workerBudget);
'''
OPEN_NEW = '''                MappedSnapshot workerSnapshot = OpenSnapshot(workerCachePaths[index], workerBudget);

                // RewindBox (adapt_empty_worker_snapshot): beside a main snapshot, a worker file of a cache's header alone holds
                // no pipeline: read as none, it neither joins main nor holds the workers' files until main is written.
                if (workerSnapshot != null && _pendingMainSnapshot != null && workerSnapshot.Length <= EmptyCacheBytes)
                {
                    workerSnapshot.Dispose();
                    workerSnapshot = null;
                }
'''

PAIRS = [
    (MANAGER, OPEN_OLD, OPEN_NEW),
]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
