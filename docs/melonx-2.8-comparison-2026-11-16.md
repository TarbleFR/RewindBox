# MeloNX 2.8 against RewindBox's MeloNX — 16 November 2026

Maintainer request: analyse the latest MeloNX IPA, add what is useful to RewindBox's version, and compare.

## What was analysed

- The MeloNX 2.8 IPA the maintainer provided (bundle 2.8, build 1; memory extension 2.7; iOS SDK 27.2, minimum
  iOS 15). Analysed locally only: no part of it, its signing profile or its developer paths is committed.
- MeloNX's public source stops at 2.7 (`13700519`, 11 October 2026), the base of RewindBox's engine. 2.8's source is
  not published, so 2.8 was read from its binaries: exported engine functions, NativeAOT symbol names (type and method
  names), engine and app strings, compared with the 2.7 source. Nothing was decompiled or copied; anything taken from
  2.8 is either public source (Melo-Controller) or a design to reimplement and measure.
- 2.8's engine is a rebase on a newer Ryubing tree.

## Comparison

| Area | MeloNX 2.8 | RewindBox (Core 030cc14f, app) | For RewindBox |
| --- | --- | --- | --- |
| Engine base | 2.8, Ryubing rebase, source unpublished | 2.7 (`13700519`) + reviewed adapters (109 gates) | — |
| Play without JIT | Experimental: every loaded code segment recompiled at launch, signed on the device with the user's certificate (.p12 from SideStore or LiveContainer), no recompilation in play; ARM32 unstable | JIT required (StikJIT / BreakpointJIT) | Most visible feature for players; very large; candidate lot, design to redo |
| Guest memory (LazyZero) | Zero pages share one template and are made private on the first write; counters of shared bytes and write faults | No | High value: memory pressure is RewindBox's main open limit (Hogwarts at 4-8 % free); candidate lot, to measure |
| Extra RAM | Memory-donor extension, several donor processes | Own donor extension, lease and memory graph | Equivalent approach; compare on device before taking anything |
| Vulkan driver | KosmicKrisp (Mesa's Vulkan on Metal) selectable next to MoltenVK | MoltenVK 1.4.2 with RewindBox's patch | Experimental option; large (loader, ICD, 12.5 MB); RewindBox's pipeline-cache work targets MoltenVK |
| Uniform descriptors | Dynamic offsets for used uniform bindings, descriptor cache with namespaces, push descriptors by template | Descriptor deltas, sets kept per program, extra-set binds | Possible GPU-thread lot; measure first |
| Pipeline cache | Persistent with a budget and recycling | Per title, 1 GiB, checkpoints in play, mapped and compacted, shared by workers, states replayed at launch | RewindBox equal or ahead |
| Waits and threads | Contains the adaptive spin event, the dispatch-semaphore timed waits and the QoS boost under the same names as RewindBox's adapters | Adaptive spin, timed waits, QoS (`adapt_wait_spin_bound`, `adapt_darwin_timed_waits`, QoS adapters) | Same design; nothing to take |
| Bindless texture arrays | Per-slot entries in the array cache | Per-element deltas, dirty log, barrier and reference deltas | Same direction; RewindBox measured |
| Presentation | MetalFX upscaling with bilinear fallback | Present pacer; MetalFX callbacks deliberately off | Candidate (resolution / cost), measure |
| Diagnostics | Environment-variable performance JSON, GPU timestamps, per-thread CPU | Per-second journal, GPU windows, hot profiles, GC and memory journals, offline tools | RewindBox ahead |
| On-screen controls | Melo-Controller with fixes up to `b16a8e39` | Melo-Controller `c049ce88` (+ opacity) | Input fixes, not performance: prepared, then withdrawn (maintainer's decision) |
| Layout editor | Per game, import/export `.meloLayout`, copy from a game, toggle, slide between buttons, D-pad as a stick | Same editor (vendored), D-pad switch not honoured by the buttons | Not performance |
| Steam Controller | Bluetooth LE | Game Controller framework pads | Niche; large app-side work |
| Shortcuts | "Launch <game>" App Intent | None | App-wide (every console), not MeloNX-specific |
| External display | AirPlay library view and external display scene | External display service | Equivalent |
| Online | LAN / local multiplayer (local-network permission) | No LAN option exposed; Nextendo lot ready (servers awaited) | Nextendo: RewindBox ahead (none in 2.8); LAN: small candidate (engine option exists in 2.7) |

## Maintainer's decision (16 November): performance only, nothing experimental

The "For RewindBox" column above was written before this decision. Kept from 2.8: nothing. Row by row:
- Experimental in 2.8 itself, so excluded: play without JIT ("Enable (Experimental) JIT-Less Mode"), KosmicKrisp
  (environment variable), the memory helpers ("Experimental: the helpers can be killed...") and their 512 MiB
  GPU-buffer reserve ("Experimental, requires a game restart"); MetalFX is a player option, not a speed-up by itself.
- Not performance: the controller update (Melo-Controller b16a8e39, input fixes) was prepared in 143b86bc2 and then
  withdrawn; Steam Controller, Shortcuts, external display, LAN.
- Uniform descriptors with dynamic offsets: 2.8 logs that it bypasses the shared Vulkan pipeline cache for them
  ("Shared Vulkan pipeline cache bypassed for MoltenVK dynamic uniform offsets"). RewindBox's persistent, shared
  pipeline cache is its largest measured GPU-side gain (Hogwarts pipeline creation on the render thread: 199 s in a
  21-minute session on IPA 666, 356 ms after 165 s on IPA 729), so this trade is not taken.
- Waits, timed sleeps, QoS and per-slot bindless arrays: 2.8 carries RewindBox's own designs under the same names.
- Pipeline cache, GC, DMA copies, diagnostics: RewindBox goes further (measured on its journals).
- Zero-page sharing (LazyZero): the only 2.8 performance change RewindBox lacks that is not marked experimental (no
  option visible; it reports shared bytes and write faults). Not taken: iOS already leaves untouched guest pages
  without physical memory, 2.8's own log says its shared-bytes count "is not a measurement of saved footprint", and it
  would change the guest memory fault path. A lead only if RewindBox's journals ever show zeroed guest pages behind the
  memory pressure.

Verdict: on everything that can be compared, RewindBox's engine is equal or ahead; nothing in 2.8 is a proven,
non-experimental performance gain for it.

## Not proven

Everything about 2.8 comes from names and strings in its binaries, not from running it. No FPS comparison between
the two apps was run on an iPhone.
