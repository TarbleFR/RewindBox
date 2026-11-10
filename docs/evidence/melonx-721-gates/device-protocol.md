# MeloNX lot 9 — device protocol (IPA with Core 721 and the mapped-cache MoltenVK)

Inputs to check first: the IPA's manifest names MeloNX Core 721 (contract `9eb112f1…`, see `run.json`), the
MoltenVK rebuild of run 42822060210 (binary sha256 `6f65b2a6…`, three markers, the third "RewindBox mapped cache data:
compressed MSL referenced in the mapped file, not copied"). Without that MoltenVK the Core change does nothing (MoltenVK
ignores the unknown structure and copies as before); with the MoltenVK but an older Core, nothing changes either.
Settings unchanged between runs; caches and saves kept (no deletion of the player's caches); thermal state noted.
The protocol of IPA 720 (`../melonx-719-gates/device-protocol.md`) still applies for the crash, the skin and the stutters.

## RAM, Hogwarts Legacy (1x, async shaders on, the player's caches)
Reference, IPA 718 (pid 44597): footprint 2 090 MiB at 1 s, 4 256 MiB at 5 s (pipeline cache load), about 3 600 MiB
after, +700 MiB at game entry, 5 400-5 526 MiB in play with 4-9 % of the device available, 14 memory warnings, thermal
`serious` from about t=96 s with 8-13 FPS.
1. Same route as IPA 718: launch, title screen, load the save, walk the same area 5 minutes. A first launch after the
   install, then a second launch (warm caches).
2. From `MeloNX-core.log`: one `pipelineCache mainDataMapped` line per launch with the main cache's size (absent: the
   MoltenVK or the Core is not the expected one; stop there). `pipelineCache` load line, then no new error.
3. From `MeloNX-performance.log` (`mem=` footprint/available/percent): the footprint at 5 s (expected: no 4.2 GiB peak;
   the main cache is no longer copied twice), at the title screen, at game entry, and the in-play maximum and slope;
   memory warnings count; the thermal state over time (`th=`); FPS short windows and presentation intervals
   (`tools/melonx/frame_report.py`).
4. Pause (in-game menu) then resume, and the close: no crash, a `pipelineCache` checkpoint written as before, the next
   launch reads the cache (no rebuild of the pipelines: render-thread compilations comparable to the warm 718 launch).
5. One session of at least 15 minutes for the long slope; one with a loss/return of activity (Control Centre).
What would refute the gain: the same footprint as 718 at 5 s and in play with the line present (then the pages are
counted after all and the iPhone result is reported as it is).

## Not changed by this Core
GPU memory (textures, buffers), the managed heap, the JIT arena. Their share of the 5.4 GiB is the next lever and must be
read in the same journals (`gpu`/`managed` columns of the core-performance records).
