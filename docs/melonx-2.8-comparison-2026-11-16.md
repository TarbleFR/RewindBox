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
| On-screen controls | Melo-Controller with fixes up to `b16a8e39` | Melo-Controller `c049ce88` (+ opacity) | **Taken**: `build-utils/melonx/controller-b16a8e3/` (source only, next freeze) |
| Layout editor | Per game, import/export `.meloLayout`, copy from a game, toggle, slide between buttons, D-pad as a stick | Same editor (vendored), D-pad switch not honoured by the buttons | Fixed by the controller lot |
| Steam Controller | Bluetooth LE | Game Controller framework pads | Niche; large app-side work |
| Shortcuts | "Launch <game>" App Intent | None | App-wide (every console), not MeloNX-specific |
| External display | AirPlay library view and external display scene | External display service | Equivalent |
| Online | LAN / local multiplayer (local-network permission) | No LAN option exposed; Nextendo lot ready (servers awaited) | Nextendo: RewindBox ahead (none in 2.8); LAN: small candidate (engine option exists in 2.7) |

## Taken now

- Melo-Controller `b16a8e39` (public, GPLv3, same licence file): stuck toggled buttons, sticks per touch, stick scale,
  per-game D-pad switch, no main-queue hop. Prepared as a source-only lot because the controller revision is part of
  the Core's source identity; it goes in with the next Core freeze. Checks: `build-utils/melonx/controller-b16a8e3/`.

## Candidates for engine lots (MeloNX session's freeze), in order

1. Zero-page sharing for guest memory (LazyZero design): addresses the measured memory pressure; needs a fault path
   on iOS and device measurements of footprint and decompression.
2. Uniform descriptors with dynamic offsets: GPU-thread time; measure descriptor work in the journal first.
3. MetalFX presentation upscaling: a player option, not a default.
4. Play without JIT: largest; needs on-device signing and an AOT link of guest code; separate project.
5. KosmicKrisp as an experimental driver: only with an A/B against MoltenVK on the same titles.

## Not proven

Everything about 2.8 comes from names and strings in its binaries, not from running it. Nothing here is measured on
an iPhone; the controller lot is checked on Linux (vendoring, existing tests, delivery contract) and not compiled for
iOS yet.
