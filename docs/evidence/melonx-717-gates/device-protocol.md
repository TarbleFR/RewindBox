# Hogwarts Legacy 1x on iPhone 16 Pro Max: device protocol for lot 8 (Core 715 / Core 717)

Nothing here is measured yet on the device. The gates proved equivalence and removed work with doubles, and the Metal
library measure ran on the macOS runner's real Metal device; neither is an iPhone frame time.

## Builds to compare

- Reference: the last device baseline, IPA 694 (Core 699), or the IPA carrying Core 713 if one is delivered first.
- Candidate: the IPA carrying Core 717 (target). Core 715 is the validated fallback; an IPA with it isolates the two render
  CPU fixes from the library sharing if the 717 result needs to be split.
- The same iOS version, device, settings (1x, async shaders as in the baseline, precise math as delivered), charge level
  and thermal state (start cool, plugged or not the same way). The same save.

## Caches

- Keep every cache: do not delete the pipeline cache, the shader cache or the variants journal between builds. The MoltenVK
  revision is unchanged, so the pipeline cache identity (pipelineCacheUUID) and the files stay valid across the update.
- The first launch after the install is recorded but read apart (the system Metal cache may be cold after an update).

## Sessions

1. Launch 1 (after install): launch to the save, record the load, then route A, then quit cleanly from the menu.
2. Launch 2 (same build, caches warm): route A, route B, quit cleanly.
3. Launch 3: route A again (comparable to launch 2), then a long session of at least 30 minutes of free exploration with
   one pause (app to background 1 minute, back), one fast travel and one combat, then quit cleanly.
4. Same three launches on the reference build, same order, same save.

- Route A, exploration: from the save point, a fixed walk of about 3 minutes through the castle courtyard and a corridor
  change of area (same path, same camera turns).
- Route B, effects: a fixed combat or spell sequence of about 2 minutes (same enemies, same spells).

## What to read (aggregates only; journals stay private)

| Priority | What | Where |
| --- | --- | --- |
| 1 | Load time to control | launch journal (gpuStartup phases, mainPipelineCache), "Vulkan main pipeline cache loaded in the background ... in N ms" |
| 2 | Compilations left | MoltenVK statistics: "Convert SPIR-V to MSL", "Compile MSL into a MTLLibrary", "Compile MTLFunctions into a pipeline" (counts and totals, first and last report); "Pipeline compilations (...)" build journal lines; "Worker pipelines found in the main cache: N (not in it: M)"; Core 717: "Worker libraries shared with the main cache (...): merges, longest, not shared busy/memory/budget" |
| 3 | Long frames | frame interval and present gaps from the performance log (frames over 50 ms and over 100 ms per minute, the longest) |
| 4 | Render-thread waits | pass detail line: draw and compute prepare, descriptors (against 1 121 / 394 ms per 108 frames at IPA 694), array reference passes and references added, array current binds, descriptor sets written; pipeline waits on the render thread |
| 5 | Memory | tools/melonx/memory_report.py over the same windows (first game second as origin), peak footprint, memory warnings |
| 6 | Correct image | screenshots at three fixed points of route A and one of route B, compared between builds: no missing effect, no black or white patch, no flicker |

## Reading the result

- Fewer MSL library compilations or conversions in play on the candidate with the same route is the 717 effect; the
  runner showed 40 -> 27 for its synthetic pattern, not a Hogwarts figure.
- The 166-185 ms the runner spent under the main lock are a total over its scenario (pipeline states of variants served
  from main, moved from the worker caches): whether render-thread creations wait for them in play is read from the
  render-thread pipeline waits and the long frames, not assumed.
- A lower render-thread prepare time and fewer array references on the same route is the 715 effect.
- No FPS figure is stated from this lot until these launches exist; a regression on any priority, or a wrong image, is
  reported with the build, the launch and the window.

## Other games (no regression)

The three changes apply to every title. One launch each, caches kept, 5 minutes of play, quit cleanly, on the candidate
and the reference: Super Smash Bros. Ultimate, and every other title installed on the device (the maintainer's list).
Read: load to control, long frames, image at two fixed points, memory peak, no stop or crash.
