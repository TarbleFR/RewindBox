# SSBU startup: observations and source correlation, 29 October 2026

The supplied log records **19.399 seconds from selection to the first confirmed
Metal presentation** for the recent Super Smash Bros. Ultimate v13.0.4 session.
Loading the 2,743 cached shader programs occupies **11.411 seconds**, or 58.8% of
that interval. The source below identifies a startup path worth correcting;
these observations do not measure a future correction on the device.

## Scope and clocks

`log-summary.json` binds the observations to upload SHA-256
`77052931caa3ada4184131eb6db69610dfe2cb7e204848c84486e6ccb7a40d4c`.
The new upload has 9,053 lines. Its first 5,827 lines are the exact byte and line
prefix from the previous upload. Only lines 5,828–9,053 are new. They contain
three application-log segments, beginning at lines 5,828, 5,977 and 6,321;
only the last contains a game selection. That recent game is SSBU, selected at
07:01:17.175754 UTC (line 6,383), with first presentation confirmed at
07:01:36.574814 UTC (line 8,221). The record ends on a background transition
at 07:01:48.541596 UTC (line 9,053), without a close or crash event.

Core JSON timestamps measure core stages. Native and launch messages often
mirror the same events later and must not be counted as additional stages.
For example, core file validation takes 3.043 ms (lines 6,399–6,400); the
delayed launch mirror does not show a second, one-second file validation.
Stderr wall timestamps are one hour ahead of adjacent UTC core markers in
both SSBU sessions. Cache times use the normalized stderr timestamps; their
millisecond precision explains the 1 ms difference from the elapsed counters.
The performance sampler's `t` is relative to engine start, not selection.

First presentation confirms that a drawable appeared. It does not establish
that a menu, gameplay or meaningful image content was ready. The log supplies
no such marker.

## Measured startup windows

The following windows do not overlap and add up to 19.399 seconds. Their
endpoint labels describe elapsed intervals, not exclusive CPU attribution.

| Recent SSBU interval | Seconds | Log lines |
| --- | ---: | --- |
| Selection → runtime ready | 0.193 | 6,383–6,393 |
| Runtime ready → first core preflight event | 2.066 | 6,393–6,399 |
| Core preflight → firmware ready | 0.175 | 6,399–6,416 |
| Firmware ready → JIT handshake complete | 1.006 | 6,416–6,442 |
| JIT complete → renderer setup | 0.759 | 6,442–6,476 |
| Renderer setup and content load → shader-cache start | 0.411 | 6,476–7,040 |
| Shader-cache load | 11.411 | 7,040–8,146 |
| Shader-cache end → first Metal presentation | 3.379 | 8,146–8,221 |

More specifically, the JIT arena takes 0.988 s, donor mapping receipts span
0.126 s, and view attachment receipts span 0.599 s. The game-content loader
takes 0.359 s. Horizon service readiness takes 0.125 ms and renderer
initialization takes 14.964 ms. Those last two operations do not account for
the long wait (exact markers and endpoints are in the JSON).

During cache loading, the eleven samples at `t=1..11` report zero presents
and zero FPS, total CPU of 101–120% of one core (median 116%), and
GPU.MainThread at 15–19% when visible. The listed .NET workers consume part
of the remaining CPU. Footprint rises from 1,237 to 2,383 MiB while process
headroom remains 4,272–5,418 MiB and device-available memory remains 23–37%.
All samples report nominal thermal state and low-power mode off. BGC is
absent from the six busiest threads in this interval; that does not establish
zero GC work (lines 7,085–8,076).

Just after the cache loads, the explicit memory report gives 2,459 MiB
footprint, 4,196 MiB headroom, 22% device-available memory and a 594 MiB
managed heap. Texture and buffer caches are still reported as zero bytes
used (line 8,174). These measurements do not support critical memory pressure
as the explanation for this particular startup wait.

The first logged guest service call follows cache completion by 41 ms
(lines 8,146–8,148). The guest MainThread reaches 99% of one core at `t=14`
before first presentation (line 8,197). The first sample with presentation
is `t=16`, with 37 presents; its initial FPS/frame-time aggregate is not usable
(line 8,229). `t=17` reports 60.3 FPS. A later gap around `t=19..20` precedes
samples at 60.0–60.3 FPS with movie/Nvdec workers active (lines 9,034–9,048).
This short post-launch observation is not a gameplay performance benchmark.

## Comparison with the previous SSBU session

This comparison uses only the older **SSBU** session, beginning at
02:47:13.999037 UTC (line 1,933), already present in the previous upload.
The Hogwarts sessions are not part of this comparison.

| Metric | Older SSBU | Recent SSBU |
| --- | ---: | ---: |
| Selection → first presentation | 29.055 s | 19.399 s |
| Selection → shader-cache start | 4.742 s | 4.609 s |
| Shader-cache load | 20.749 s | 11.411 s |
| Cache end → first presentation | 3.564 s | 3.379 s |
| Cached shader programs | 2,743 | 2,743 |
| Primitive-restart warnings during cache load | 1,084 | 1,084 |
| Main Vulkan pipeline-cache data at initialization | 0 KiB | 0 KiB |
| Worker pipeline snapshots recovered | 2/2 | 2/2 |
| JIT arena | 512 MiB | 512 MiB |
| Gameplay async shaders | false | false |
| MoltenVK SHA-256 prefix | `e16c98f057d7fbfd` | `1ede50b4eeff3620` |

The observed total reduction is 9.656 s (33.2%); 9.338 s of that difference
falls within the cache-loading window. The older session explicitly rebuilds
2,743 shaders, with 1.468 s between rebuild-start and success and another
1 ms before cache-loaded (lines 3,704–3,708). It also shows GPU translation
workers in the busiest-thread list. The recent session has no rebuild
announcement and its cache samples show .NET workers instead.

Neither log identifies an application build/IPA or engine commit. A different
MoltenVK component identity and different cache history prevent a controlled
engine comparison. Snapshot recovery alone does not establish per-pipeline
cache hits or avoided Metal compilation. The unchanged 512 MiB SSBU arena
must not be confused with the 1,024 MiB arena in the Hogwarts sessions.

## Relationship between async=false and pipeline warnings

The static review concerns the available adapted source, whose file hashes
and line references are recorded in the JSON. It does not establish that this
exact engine binary produced the log.

1. `ShaderInfoBuilder.Build` computes `EnableAsyncCompile` from the gameplay
   async setting and the presence of a pipeline state, including when
   `fromCache=true`. Both host-cache loads and guest recompilation supply
   shader information through that builder.
2. `VulkanRenderer.CreateProgram` passes that flag to `ShaderCollection`.
   For a program with an initial pipeline state and async=false, the
   constructor calls `BackgroundCompilation` and returns before setting
   `_detachedWarmUp`.
3. That branch waits for shader modules and then creates an initial compute
   or graphics pipeline. Blocking `CheckProgramLink` can wait for this task;
   the disk-cache loader performs blocking validation. The existing detached
   warm-up handling covers the async=true path.
4. `GpuContext.InitializeShaderCache` signals the GPU-ready event only after
   cache initialization returns. `ArmProcessContext.Execute` waits for that
   event before executing guest CPU code. The render loop likewise initializes
   the cache before processing frames.

This source path explains how initial pipeline work can still delay startup
when gameplay async shaders is false. It is consistent with the 1,084
MoltenVK messages during cache loading. Both sessions have 1,086 such messages
in total, with two additional messages after cache loading. The message says
Metal does not support disabling primitive restart; its `VK_ERROR` spelling
occurs in a warning record. The count is a count of log lines, not distinct
pipelines, successful compilations or failed compilations.

The log does not separate shader module creation, driver compilation, cache
I/O and logging costs. It cannot show how much time removing the repeated
messages would save, nor justify claiming that every cached shader was
recompiled. It does identify the cache-loading barrier and a source path
through which optional initial pipeline work remains on that barrier. Any
change should be validated without treating a gameplay async-setting change
or skipped draws as an established fix.
