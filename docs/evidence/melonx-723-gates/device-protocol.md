# MeloNX lot 9 — device protocol (IPA with Core 723)

Inputs to check first: the IPA's manifest names MeloNX Core 723 (contract in `run.json`), the same MoltenVK as Core 721
(rebuild of run 42822060210, binary sha256 `6f65b2a6…`, three markers), and a bridge with the memory breakdown
(`[MeloNX:memory]` lines, commit `b653a058` or later). The Core 721 protocol (`../melonx-721-gates/device-protocol.md`:
`pipelineCache mainDataMapped`, footprint at 5 s and in play) still applies. Settings unchanged between runs; caches and
saves kept; thermal state noted. Hogwarts Legacy, 1x, the same route as IPA 718/722, one session of 15 minutes or more.

## GC pauses (decides the gen0 budget; nothing changed in the collector)
1. `MeloNX-core.log`: the `gcPause ephemeral` lines (at most 48: the first 24 collections paused 20 ms or more, then every
   16th): generation, pause, promoted MiB, gen0 and gen1 size before->after, compacted, rank. At the close, one
   `gcPause summary` line: per generation the collections seen of those that ran, pause total, longest, promoted.
2. Read: average pause per gen0 and per gen1 (summary), and whether a gen0's pause follows its promoted bytes or its gen0
   size before (lines). Reference (718, fitted from the 5 s windows): about 29 ms per gen0, 135 ms per gen1.
3. `gcKeepAlive dormant` lines (F1): how many, with the fragmentation they report; the keep-alive summary's new
   "dormant after a fragmented skip" count.

## Render thread (Hogwarts in play)
1. "Vulkan pass and GPU detail" line: `descriptor sets written u/s/t/i` — the texture count against 718 (63 517 per 5 s
   in the 97-frame window of 03:41:20) for the same scene; then `texture array barrier passes N (storages visited M, sets
   rebuilt R over E elements, X ms), skipped unchanged K`.
2. "Render thread commands": SetTextureArraySeparate (718: 50 841 calls, 248.6 ms per 5 s), DrawIndexed, DispatchCompute;
   "GPU thread sync waits" (718: 519.6 ms per 5 s); FPS and presentation gaps (`tools/melonx/frame_report.py`).
3. Rendering: no missing, black, stale or flickering texture, in particular right after a scene change, a menu, a cut
   scene and in areas with render targets sampled later (water, shadows, UI over the game). Screenshots against 722 at
   the same places.

## Memory breakdown (bridge)
`[MeloNX:memory]` lines at t=30 s, in play and after 10 minutes: `footprint=`, `graphics=` (Metal/IOAccelerator memory
charged to the process), `compressed=`, the groups by tag and the six largest regions (the guest memory, the GC heap and
the JIT arena should stand out among them). They decide the next RAM lever after Core 721.

## What would refute
- Texture-set writes and SetTextureArraySeparate time unchanged against 718 on the same scene: the separate-array path
  is not where Hogwarts' writes come from (report the line as it is).
- `skipped unchanged` near 0 with passes unchanged: attachments are loaded or stored between almost every bind.
- A texture artefact seen only on 723 (not on 722 at the same place): report it with the time; adapt_array_barrier_epoch
  is the first suspect (barriers), adapt_extra_array_dirty the second (descriptor sets).
