# MeloNX lot 10 — device protocol (IPA with Core 729 and the five-part MoltenVK)

Core 729 is Core 727 plus one adapter (`adapt_pipeline_cache_compact`) and is bound to the MoltenVK recipe patch with its
fifth part (cache keys, patch `560669f0…`, five markers). The protocols of [Core 725](../melonx-725-gates/device-protocol.md)
and [Core 727](../melonx-727-gates/device-protocol.md) apply unchanged (route, export with `MeloNX-core.log.1`, verdict,
pipeline variants, the pause, the memory breakdown, the Vulkan memory samples). This page lists what lot 10 adds.
Nothing here was run on an iPhone: every device figure below is IPA 724's, for comparison.

Inputs to check first: the IPA's manifest names Core 729 (contract in `run.json`) and a MoltenVK rebuilt from the
five-part patch (with an older MoltenVK the load line below lacks "resource bindings", the file is not written again and
nothing of this lot applies); the bridge has the `vm=` field (`[MeloNX:perf]` lines, from the second line on).
**Two sessions, the same route, without deleting anything between them**: the first one migrates the cache file.

## Reference to compare with (IPA 724, Hogwarts, pid 49375), one command
`python3 tools/melonx/frame_budget.py MeloNX-performance.log --pid <pid> --window 52-72 --window 88- --window 107-`
(seconds of the play that can be controlled; adjust the first second to the session: the first line with `in=` after the
load). IPA 724: 52-72 s 38.7 ms per frame (25.8 presented FPS); after 88 s 89.0 ms, excess +55.6 = stutters +36.2
(220 gaps over 100 ms) + slow frames +19.9 - 0.5; after 107 s 93.9 ms; the session ended at t=217 without an end line.
Inside the 121.8 s after 88 s (the engine's 5 s windows; overlapping measures, not to be added): GC pauses 14.6 s (seven
windows with 0.6 to 3.1 s, two of them at the pause and its resume: 1.35 and 3.13 s), pipeline builds on the render
thread 7.3 s, the 6.2 s after the resume (15 frames, one gap of 4 283 ms).

## 1. The cache file and the driver's load (both sessions)
- `MeloNX-stderr.log`: `[mvk-info] RewindBox pipeline cache load: N shader libraries from B bytes, resource bindings R
  read K kept; compressed MSL referenced in the caller's data; pNext types 0x52425831.` First session: B about 792 MiB,
  R several millions (1 305 per vertex or fragment library of a two-stage program), K a small fraction. Second session:
  B the new file's size, R = K.
- `MeloNX-core.log`: first session `pipelineCache compact: main's data X of a 792 MiB file: written again now`, then
  `pipelineCache written: main X in N ms`; second session `pipelineCache loadedSize: main's data X of a X file`.
- `MeloNX-stderr.log`: "Vulkan main pipeline cache loaded in the background: ... in N ms" (IPA 724: 4 388 ms).
Would refute: K equal to R (the driver kept the tables: wrong MoltenVK), or no `compact` record with K far below R.

## 2. Memory at the load (first seconds of `MeloNX-performance.log`, `mem=` first value)
IPA 724: 2 060 MiB at t=1, 4 149 at t=6 (+1 078 during the read, +913 in the second of the merge), 3 596 at t=18,
4 496 at t=30, up to 5 414 in play. Expected: no step of that size at t=1-6 (the tables were about 775 MiB per copy, two
copies at the merge), and a footprint lower by several hundred MiB afterwards. The macOS measure (run 42943460686, 780
libraries): +334.5 MiB after the load with whole configurations, +66.7 MiB with keys. What the iPhone gives is unknown
until this run: report the same seconds.

## 3. Pipeline creation (what the cache keys change besides memory)
- `MeloNX-stderr.log`, "Worker pipelines found in the main cache: N": IPA 724 found 64 pipelines every 0.3 s (4.7 ms
  each, 2 560 in 12 s). Expected: several times faster (macOS: one more pipeline of a cached program 5.6-9.0 ms with
  whole configurations, 0.25-0.46 ms with keys).
- `MeloNX-core.log`, last `pipelineVariants summary`: "late creations left N (M ms)": IPA 724 869 creations, 4 955 ms
  (5.7 ms each on the render thread). Expected: a lower time per creation; compilations of shaders never seen before
  (MoltenVK "Compile MSL into a MTLLibrary" beyond the load's count) keep their cost.
- `python3 tools/melonx/frame_report.py MeloNX-performance.log MeloNX-core.log --pid <pid> --stderr MeloNX-stderr.log
  --from 73 --to 110`: "pipeline builds" per window (IPA 724: up to 3 738 ms in one 5 s window).

## 4. Memory activity per second (new `vm=` field)
`vm=C/D/F/P`: MiB newly compressed, pages decompressed (16 KiB each), page faults, page-ins over the second. Read with
`fps=` and `cpu=`: seconds where FPS falls while D is in the tens of thousands are the process pulling its own memory
back from the compressor. This is the measure that says how much of the remaining slowdown is memory: report D and C
over the windows of section "Reference" (median and maximum), and the `[MeloNX:memory]` lines (`private=R+C`, `zones=`,
the groups) at t=30, in play and after 10 minutes.

## 5. Pause and close
As the Core 727 protocol: after five minutes, pause 30 s and resume. With the small file a write that does happen
(8 MiB of new libraries or more) is short: report `pipelineCache checkpoint` / `written ... in N ms` and the ten seconds
after the resume. Close the game normally at the end (the end line of the performance journal).
