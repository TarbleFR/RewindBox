# MeloNX lot 10 — correction lots on the IPA 729 / Core 743 findings

State on 12 Nov, written by the lot's session for main and the MeloNX owner. Figures come from private journals
(IPA 729, pid 58475); no raw log is reproduced. Nothing here was measured on an iPhone after the changes.

**MeloNX lot 10: correction lots on the IPA 729 / Core 743 findings (Claude Code session 01JA5QgKeoGVH5oVjNyhcj3D, 12
Nov; owner: this session for the adapters, their gates, the capture tooling and the proposed wiring below; main owns
the Core number, the freeze, Core CI, the pin and any IPA; branch `work/melonx-lot10-20261112` from `Claude`
`e602b6aa`, head `8f71c4e1`; no contract frozen, no Core built, no pin; IPA 730-732 keep Core 743)** input IPA 729,
Core 743 (source `3d2645ea`, iPhone binary `b1957006…`), private journals, pid 58475: Hogwarts gen 1 (session
25431A89, 1x, async shaders on, host memory budget on, MoltenVK standalone `1bdc5159`), then Smash gen 2 in the same
process (session 854293EB). "Written", "host gate passed" and "wired" below do not mean "corrected on the iPhone": no
device result exists for any of them.

## Reference figures before (`tools/melonx/live_capture.py report`, whole sessions, loading included)

Hogwarts 147 s of play: 17.7 presented frames/s, frame time p50/p95/p99 50/117/200 ms, gaps over 100/250/500 ms
62.5/5.3/1.6 per minute, footprint 2 109-4 882 MiB, device available down to 4 %, 9.8 GiB decompressed per minute.
Smash 237 s: 52.9 frames/s, 17/17/17 ms, gaps 9.1/2.5/1.3 per minute. At t = 30 s (footprint under 4 GiB) Hogwarts
presents 142 frames in 5.03 s, all paced at 33 ms: its first limit after a minute is memory.

## L1 retention between games — `adapt_nifm_network_watch` (IGeneralService.cs, Library.cs).

Cause (source, reproduced on the host): nifm's general service subscribes an instance method to the runtime's static
`NetworkChange.NetworkAddressChanged` and unsubscribes only in `Dispose`; a closed session disposes its root object
only, so the event keeps the service, its `ServerBase`, the `KernelContext` and the `Switch` (729: 1/1 then 2/2).
Change: one static handler counts the changes, the cache compares the count where it is read. Gate `nifm-network-
watch` (42 checks; production Ryujinx.HLE and Ryujinx.Library of the final preparation built; real
IGeneralService/ServerBase/KernelContext/Switch chain on the host runtime): control keeps 11 Switches of 11 and 92.3
MB, candidate 0 and 6.7 kB; the cached interface is returned identically; one static subscription. Device, pending:
Hogwarts 5 min, close, Smash 3 min, close, Hogwarts 5 min, close, without leaving the app; each close must journal
`sessionRetention released` and "Nifm general services created C, disposed D" with C - D above 0 (this path held the
session). **L2 (another root):** no change; opened only if a close still journals `retained` with this Core, and then
from the `retentionChain` line of that capture. This does not address the growth during a first Hogwarts session.

## L5a submissions — `adapt_paced_strict_syncs` (GpuContext.cs, AutoFlushCounter.cs, Library.cs; Hogwarts only).

 729: 24-31 command buffers per frame; of 2 014-2 367 per 5 s, 1 314-1 335 are the strict host sync of a guest
syncpoint increment (913-1 041) or SetReference (213-276), 0-2 syncs per window waited for before their command buffer
was submitted. Change: those two sites keep a strict sync at most once per 4 ms, the others are created on the open
command buffer and submitted with it or when a reader waits (the engine's non-strict path); the two voluntary
submissions wait 4 and 8 ms; forced syncs, counter reports and every other site untouched; both flags off give the
control's decisions. Gate `paced-strict-syncs` (54 checks; production Vulkan, Gpu and Library assemblies built; the
production auto-flush counter of control and candidate on a fake clock replaying one 729 frame): 34 command buffers ->
10, longest gap 5.3 ms, every sync still created. Device, pending: command buffers per frame 24-31 -> 14 or fewer,
"same framebuffer again" halved; refuted and removed if "sync waits" exceeds 4 ms per frame or presented fps fall.

## L5b array walks — `adapt_array_sync_epochs` (Texture.cs, TextureBindingsArrayCache.cs; every title).

729 Hogwarts: arrayDelta 170-534 calls and 459-1 136 ms per 5 s window of the GPU thread, 0.9 ms per call at the start
of play, 2.8-6.7 ms after 100 s ("bindings", which contains it, 956-1 773 ms): each update of a pool array walks all
its textures three times (one SynchronizeMemory walk that only stamps the use clock on a texture that is not dirty,
two ValidateTextures walks). Change: SignalGroupDirty and every InvalidatedSequence move advance a process-wide epoch
(writers counted in flight); the array skips a walk when nothing was signalled since its last complete one, the use
clock (seconds) did not tick and the access is not a store, and synchronises only the textures added since. Gate
`array-sync-epochs` (97 checks, 21.6 million fixture checks; production Gpu assembly built; the production cache of
control and candidate against doubled pools and textures with the dirty flag and the use clock): 98 scenarios and 24
with cascading signals leave the same backend contents, stores, uploads and texture states at every step; an array of
3 200 bound textures: 3 200 synchronisations and 6 400 sequence reads per update -> 0 (quiet) or 6 and 3 (three
elements changed); a writer in flight makes the update walk. Three fixtures that compile the final cache with their
own texture double now carry the dirty flag (bindless-array-deltas' check "every bound texture synchronised" becomes
"no bound texture left dirty"), and remap-sweep-range follows the later adapter on Texture.cs. An independent review
of the first version found one defect, fixed and now a failing variant of the gate: SetScale can take a texture out of
the scale blacklist without any signal; its four assignments now signal it. It found no lost synchronisation or
validation race. Device, pending: arrayDelta under 200 ms per window after 100 s; refuted and removed if it stays
above 500 ms or a texture shows stale content.

## L6 warmed variants missed at the draw — `adapt_sibling_pipelines` (ShaderCollection.cs; every title).

729 Hogwarts: 49 late creations (356 ms) in 165 s, 13 of them "built but missed" (Smash 0). Cause (source): one guest
program is translated again, to the same code, for a specialization the stages do not read
(`ShaderSpecializationState.MatchesGraphics` compares the whole attribute type table and every fragment output type),
the variant journal hands a code's recorded states to the first host program only, and a pipeline lives in one
program's table until the session ends. Change: guest graphics programs of the same code (128-bit identity) on the
same pipeline layout entry take the pipeline a sibling holds for a key (one more reference on the same object, given
back at disposal) before creating it; journal line `pipelineSiblings` at the 1st, 8th, 64th... pipeline taken. Gate
`sibling-pipelines` (55 checks; production Vulkan assembly built; the production helpers with a stand-in program): one
creation instead of two, destroyed once whichever program goes first, nothing shared across codes, layout entries or
states, 8 threads with disposals: every pipeline destroyed exactly once, no retention. Device, pending (second launch,
same route): "built but missed" 13 -> 2 or fewer and a `pipelineSiblings` line; refuted if the count stays and no line
appears. Not treated: the 5 "planned not built yet" and the 31 new states of a session.

## L3 memory during a first Hogwarts session: nothing reduced on the device by this lot; per item


- *Graphics resources* (ledger 1 154-1 208 MiB: Vulkan images 445-458 MiB in 8 000-9 400 dedicated blocks, buffers
  244-307 MiB in 5 700; texture cache 155-169 of a 768 MiB limit, buffer cache 126-211 of 554): no change. The
  existing trims ran (cold buffers: 379 buffers, 6 MiB released in 7 passes, 44 MiB still above the target in use); no
  further safe release identified from this capture: next action is a per-age inventory of the bound array textures on
  the device before any release policy.
- *Native heap* (903-910 MiB, about 500 MiB MoltenVK and Metal shader and pipeline objects): handed to the MeloNX
  owner, lot below. `adapt_sibling_pipelines` avoids one pipeline per shared state: unmeasured, small.
- *Managed heap* (760-840 MiB committed; at t = 90 s LOH 478 MiB of which 190 MiB free, gen2 263 MiB): no change. The
  free LOH space appears during play (the first-frame compaction leaves 266 MiB). Sources not attributed: the journal
  gives allocation per GPU work area (texSync 7-16 MiB, arrayDelta 3-26 MiB per window), not per size class. Blocked
  on that attribution; no ceiling was lowered, no collection added.

## L4 GC freezes at the start of a natural background collection

mechanism not decided, no change. Host experiment with the same collector: the ephemeral collection that starts a
background one is not longer by itself (median 17-19 ms against 11-12 ms), so the 95-720 ms on the iPhone come from
its environment (compressed pages or scheduling). The measure that decides is already written: the `[MeloNX:freeze]`
records of the bridge capture (per-thread CPU time and places inside the gap, decompression counters); it needs the
next IPA.

## L7 heat and sustained performance

nothing claimed. To be read from a 20-minute Hogwarts run of the next IPA (presented fps, frame times, CPU per thread,
thermal state); a thermal change only if those figures ask for one.

## Capture while playing (bridge commits of the branch, in no IPA yet)

`MeloNXLiveCapture.swift`, menu entry "Live capture", `tools/melonx/live_capture.py listen|report|compare`; workflow
`melonx-live-capture.yml` run 43284521762 green on `041fbb53` (recorder compiled and run on macOS arm64, iOS
typecheck). The view controller's hooks are compiled only by the IPA build.

## Local gates (Linux host, .NET 10.0.100, 2 at a time)

three-adapter preparation (nifm, paced syncs, sibling pipelines): 101 gates of 101 passed (one, hogwarts-dma-copies,
only when run alone: a 6 ms bound on a slept present fails under load; ten were run again after the session's disk
filled). Four-adapter preparation (plus array walks; it differs in Texture.cs and TextureBindingsArrayCache.cs only):
the ten gates that read those two files passed (array-sync-epochs, bindless-array-deltas, binding-data-snapshots,
array-rebuild-allocations, bindless-retention, cold-texture-release, released-texture-flush, remap-sweep-range,
fragmented-reads, hogwarts-dma-copies); the other 92 were not run again on it. Contract test: its helper checks pass
(55); the composition checks need the freeze. Independent review of the sibling pipelines: no lifetime, locking or
bind-validity defect; two statistics-only effects kept and known: a replay or a warm-up of one program that finds its
state at a sibling counts as a replay of 0 ms and may count the state "ready before its first draw".

## Handoff to main (nothing below is done by this session)

review and take the branch (wiring proposed in `prepare_embedded.py`, `ORDER`, the plan's gates `nifm-network-watch`,
`paced-strict-syncs`, `sibling-pipelines` and `array-sync-epochs`, the contract test's expectations and `FRESH_GATES`;
`origin/Claude` has not touched these files since the branch point); choose the Core number (the branch says 745) and
whether the fourth adapter goes in now (its wiring is the branch's last three commits; without them the branch at
`40cba346` is the three-adapter proposal); freeze, Core CI, pin; next IPA (the 733 queue) with that Core and the
bridge capture commits; record which Core binary the IPA holds (the journals' `coreSHA256`). Rollback of any lot: drop
its adapter from `prepare_embedded.py`, `ORDER` and the plan, freeze again.

## Device protocol for that IPA (same save, same route, 1x, async shaders and host memory budget as on 729)

 (1) cold start of the app, Hogwarts 5 min on the 729 route, close; Smash 3 min, close; Hogwarts 5 min, close; (2)
Hogwarts again, 20 min without pause; (3) send the journals (or the live capture). Read with `live_capture.py compare
<729 capture> <new capture>`: presented fps, p50/p95/p99, gaps over 100/250/500 ms per minute, footprint, and per lot
the lines named above.

## Lot handed to the MeloNX owner (MoltenVK and Metal objects): what the native heap holds in Hogwarts

Evidence, IPA 729, pid 58475, `[MeloNX:heap]` record of 12:49:39Z (window 120 s, sampling interval 256 KiB, 1 553
stacks, 0 dropped, 0 unwalked): 723 MiB live in the sampled heap, DefaultMallocZone 903/1 004 MiB in use/reserved
(910/1 008 at t = 150 s). The four largest live stacks hold 409 MiB, unsymbolicated in the journal (offsets in the IPA
729 binaries, standalone MoltenVK `1bdc5159`):

- #1 205 MiB (779 samples): `libc++abi+0x161c4` (operator new) < `MeloNXMoltenVKStandalone+0xd5780` < `+0xc6778` <
  `+0x77be0` < `+0x131a0` < `MeloNXCore+0x7dade8` (a Vulkan call made by the Core);
- #2 130 MiB (523): `Metal+0x23088` < `+0x27a14` < `+0x17c914` < `+0x17e198` < `+0x17fae4` < `+0x13ae84` <
  `AGXMetalG17P+0x39d334` < `MeloNXMoltenVKStandalone+0xc6b08` < `+0xcb4cc` < `libdispatch+0x1ccc` (a block MoltenVK
  runs on a dispatch queue);
- #3 40 MiB (162): `libc++abi+0x161c4` < `MeloNXMoltenVKStandalone+0x8a60` < `+0x13f44` < `MeloNXCore+0x8106f4`;
- #4 34 MiB (139): `Metal+0x23088` < `+0x27a14` < `+0x255ec` < `AGXMetalG17P+0x2cc78` < ... <
  `MeloNXMoltenVKStandalone+0x962f4` < `+0xcb4cc` < `libdispatch+0x1ccc`.

Further MoltenVK stacks: #5 24, #7 16, #11 11, #14 8 MiB. Reading (not established): shader module and pipeline
objects (SPIR-V copies, generated MSL, reflection data, Metal libraries and pipeline states) kept for the 1 786
replayed pipelines and their modules. **Asked:** (1) symbolicate the eight stacks against the dSYM of that binary and
name the object each one keeps; (2) for each, either release what Vulkan allows to release once the pipeline exists (a
shader module's SPIR-V and MSL after its last pipeline creation is not possible while new variants are still created:
say so with the count of late variants per module), or show it is needed; (3) no draw skipped, no pipeline evicted
that a draw still uses, no change of the pipeline cache contents. **Validation:** same save and route, same
`[MeloNX:heap]` window: live bytes of each treated stack, DefaultMallocZone in use, footprint at t = 150 s (4 782 MiB
on 729), `pipelineBuilds` and `pipelineVariants` lines unchanged or better, no new "compiled again". What this lot's
`adapt_sibling_pipelines` saves there is one pipeline per state two programs of one code both draw: not measured,
expected small.
