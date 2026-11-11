# MeloNX lot 9 — device protocol (IPA with Core 725)

Inputs to check first: the IPA's manifest names MeloNX Core 725 (contract in `run.json`), the MoltenVK rebuilt from the
four-part recipe patch (`bfd4cd9b…`, four markers; with the three-part build of run 42822060210 the driver's load line
below is absent, everything else applies), and a bridge with the memory breakdown v2 (commit `0b7339ce` or later: the
`[MeloNX:memory]` line has `private=`, `unwalked=`, `sharedSmall=` and `zones=`). Settings
unchanged between runs; caches and saves kept (the variant journal of the earlier sessions is the input of the replay);
thermal state noted. Hogwarts Legacy, 1x, the same route as IPA 718/724, one session of 20 minutes or more, **without
pausing during the first five minutes** (a pause writes the 793 MiB pipeline cache: 10.9 s and its memory in IPA 724).

Export, after the session: `MeloNX-performance.log`, `MeloNX-core.log`, `MeloNX-stderr.log`, `MeloNX-launch.log`, and
`MeloNX-core.log.1` when it exists. From Core 725 a process's records stay in `MeloNX-core.log`; for the IPA 724
session (pid 49375) the first 415 records are in `MeloNX-core.log.1`, still wanted if the file is on the phone.

## Verdict (the maintainer's criteria, one command per session)
`python3 tools/melonx/playability_verdict.py MeloNX-performance.log --pid <pid>`. IPA 724 Hogwarts (pid 49375) for
reference: NOT PLAYABLE (median 13.4 FPS, gaps p95 183 / p99 500 ms, longest 4 284 ms, footprint 5 414 MiB).

## Pipeline variants (what Core 725 changes)
1. `MeloNX-core.log`, the last `pipelineVariants summary` line. IPA 724: "ready before their first draw 506 ... late
   creations left 869 (4955 ms): new 160, planned not built yet 701, built but missed 8 ... Replays: built 512 (compile
   2273 ms, queue wait 30149 ms), ... held for memory 0, ... still planned 843 of 1357".
2. Expected with Core 725: "Replays: built" near the number planned (about 1 500: 1 357 plus the 160 new states IPA 724
   recorded), "still planned" near 0, "planned not built yet" near 0, "late creations left" near the "new" count.
3. `MeloNX-performance.log`: the seconds between the first game frame and 110 s (IPA 724: 30 FPS at t=28-72 s, then
   windows with 1.3-3.7 s of graphics pipeline builds at t=73-106 s). `tools/melonx/frame_report.py` on that range.
4. Launch: time to the first game frame (IPA 724: 9 s after the session began) and the footprint at t=18 s (3 596 MiB):
   the replay adds about 6 s of background compilation on one worker.

## What would refute
- "held for memory" above 0 with "still planned" far from 0: the replay did not finish before the device fell to 8 %
  available (IPA 724: 8 % from t=27 s); report both figures and the second at which the device reaches 8 %.
- "built but missed" growing with the replays built: the recorded state is not the one the draw asks for.
- Late creations unchanged with replays built near the plan: the late states are new ones each session.

## Memory (decides the next lever; nothing in Core 725 lowers the footprint)
1. `MeloNX-core.log`, start of the process: `pipelineCache mainDataMapped` (present: the Core kept the main cache's file
   mapped for the driver; absent: say so) and the `memoryInventory` samples. `MeloNX-stderr.log`, same seconds:
   `[mvk-info] RewindBox pipeline cache load: N shader libraries from B bytes; compressed MSL copied|referenced in the
   caller's data; pNext types ...` (one line per cache loaded from data: the main cache is the one of about 790 MiB).
   Referenced by the Core and copied by the driver, or the reverse, names the side that fails. IPA 724 for reference:
   footprint 2 060 MiB at t=1, +1 078 during the 4 s of the read, +913 in the second of the merge, 3 596 MiB at t=18.
2. `[MeloNX:memory]` at t=30 s, in play, after 10 minutes: `private=resident+compressed`, `zones=` (malloc zones, MiB
   in use / MiB held), then the groups. Read first:
   `malloc.large` (a copied pipeline cache would be about 790 MiB there; referenced, it is not), `untagged` (GC heap and
   anonymous mappings), `unwalked=` (regions over 256 MiB: resident only), `file` (the mapped cache: resident pages only,
   not footprint), `ioaccelerator`. The ten largest regions name their group, share mode and size.
3. Unattributed in IPA 724: about 2.3 GiB (footprint 5.4 GiB less the 1 GiB JIT arena, 1.2 GiB of graphics and 0.8 GiB
   of managed heap). The breakdown must say which groups hold it before any change is designed.
4. Rejected on macOS (run 42925818096), not in this Core: Metal libraries compiled on demand (+55 MiB once the pipelines
   exist, creation twice as slow).

## Pause (seen in IPA 724, not changed by Core 725)
A pause writes the main pipeline cache when it grew (793 MiB in 10.9 s for +1.06 MiB); the write went on after the
resume and the game showed 0-0.3 FPS for 8 s (t=197-205). For this run: no pause in the first five minutes; later, one
pause of 30 s, then note the seconds of the resume and the `pipelineCache checkpoint` / `written` lines.
