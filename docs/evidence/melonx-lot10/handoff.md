# MeloNX lot 10 — correction lots on the IPA 729 / Core 743 findings

State on 12 Nov, written by the lot's session for main and the MeloNX owner. Figures come from private journals
(IPA 729, pid 58475); no raw log is reproduced. Nothing here was measured on an iPhone after the changes.

**MeloNX lot 10: correction lots on the IPA 729 / Core 743 findings (Claude Code session 01JA5QgKeoGVH5oVjNyhcj3D, 12
Nov; owner: this session for the adapters, their gates, the capture tooling and the proposed wiring below; main owns
the Core number, the freeze, Core CI, the pin and any IPA; branch `work/melonx-lot10-20261112` from `Claude`
`e602b6aa`, head `d17a29f2`; no contract frozen, no Core built, no pin; IPA 730-732 keep Core 743)** input IPA 729,
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

## L3 memory during a first Hogwarts session: per item

- *Managed heap — `adapt_stall_compaction` (EmbeddedMemory.cs, WindowBase.cs, EmbeddedSession.cs; every title).*
  729 (pid 58475): the first-frame compaction ran at 12:47:47, LOH 519 MiB (253 free) -> 266 MiB (0 free), footprint
  2 903 -> 2 669 MiB, 80.5 ms. The game then went on loading: the GPU thread allocated 275 MiB in the 5 s window
  around t = 20-25 s (texture uploads 141 MiB, 128 MiB of them large pooled reads) and 216 MiB around t = 40-45 s
  (texture uploads 167 MiB; bound texture array storage 144 MiB in 11 calls). From the 30 s report on, the LOH is
  455-458 MiB with 165-234 MiB free for the whole session (memoryInventory reports 2-6; gen2 + LOH free after each
  collection 141-250 MiB), 2-4 background collections per 30 s notwithstanding: they sweep, and a swept free block
  stays committed and touched (gc.cpp `thread_gap` asks for a reset of gen2 gaps only, and `reset_memory` acts only
  at the 99 % memory load the Core configures). The host pause's compaction at the session's end: LOH 455 MiB (169
  free) -> 279 MiB, footprint 4 882 -> 4 576 MiB (306 MiB) with the device at 9 % available, 634 ms. So 170-300 MiB of
  the footprint during play was free managed space left by the loading. The session presents nothing during its 36th
  second and 0.9 frame during its 46th (loading), after each burst.
  Change: the render loop stamps each presented frame; the keep-alive's poll (250 ms) runs the existing compaction
  when no frame was presented for 700 ms, the first frame is 10 s old, gen2 + LOH had 128 MiB or more free at the
  last collection, the device has 15 % or less available, the last compaction is 8 s old, fewer than 3 ran in the
  session and no stop is requested. A host pause keeps its own rule (held 3 s): the poll does nothing while one lasts;
  a resume counts as a frame, and inside the compaction's gate the stamp the poll saw is compared again, so a frame, a
  resume or a pause that came in between cancels it; a session's run clears what an earlier session left. Each
  compaction writes the existing
  `memory heapCompacted` line with the reason `presentationGap <ms>`, footprint and heap before and after, and the
  pause. No periodic collection: none without a 700 ms presentation gap, three at most in a session.
  Gate `stall-compaction` (101 checks; production Ryujinx.Library built; the candidate's compaction class unchanged
  against the host's segments collector with the Core's settings): no compaction during 10.4 s of frames at 30 per
  second with 171 MiB free; one compaction 840 ms into a gap, free space 171 -> 0 MiB, resident 449 -> 283 MiB; none
  while the device is not short, while a stop is requested, in a host pause, right after a resume, after the session's
  end or before the next session's first frame when a frame of the closing one came after its end; the next session
  counts its own. The rule replayed on the 729 session (frames per second, free space per 5 s window, device
  share per second): fires in the loading stall of the 36th second (250 MiB free), in that of the 46th too (141 MiB
  free) if its single frame came at its end, never in the 76 s of play that follow; a third and last one in the 69th
  second if the seconds the journal has no record for were gaps.
  Device, pending: one or two `presentationGap` lines before play, each with its footprint before and after;
  `lohFreeAfterBytes` under 100 MiB from the 60 s report on (729: 165-187) if the second burst is followed by a gap;
  footprint at t = 150 s 150 MiB or more under 4 782 MiB. Refuted and removed if no such line appears with the free
  space still there, or if a line appears during play with gaps over 500 ms per minute above 1.6.
  Not treated (the source of the bursts): texture uploads allocate their large buffers when the pool has none of that
  length free (141 and 167 MiB in two windows), and the bound array storage of 11 calls took 144 MiB; reducing them
  would lower the peak itself. Not done here: it needs the allocation sites' lengths on the device.
- *Graphics resources* (ledger 1 154-1 208 MiB: Vulkan images 445-458 MiB in 8 000-9 400 dedicated blocks, buffers
  244-307 MiB in 5 700; texture cache 155-169 of a 768 MiB limit, buffer cache 126-211 of 554): **no change, nothing
  saved.** The existing trims ran (cold buffers: 379 buffers, 6 MiB released in 7 passes). Open question the capture
  cannot answer: the Vulkan images hold 2.9 times the texture cache's guest bytes; either render targets and
  auxiliary images, or guest formats decoded to wider host formats. No release policy without the image bytes by
  kind (sampled guest texture in its own format, decoded to a wider format, render target, other) on the device.
- *Native heap* (903-910 MiB, about 500 MiB MoltenVK and Metal shader and pipeline objects): **no change by this
  session**; handed to the MeloNX owner, lot below. `adapt_sibling_pipelines` avoids one pipeline per shared state:
  unmeasured, small.

## L4 GC freezes — `adapt_collection_class` (EmbeddedSession.cs; every title)

729 Hogwarts (gcPause journal): ephemeral collections that promote almost nothing stop the engine for hundreds of
milliseconds (gen0 363.9 ms for 2.2 MiB, 447.6 ms for 0.1 MiB, 720.6 ms for 1.1 MiB; 33 pauses over 33.3 ms).
Cause: the workstation collector runs a blocking collection on the thread whose allocation triggered it; the guest's
CPU threads, the render thread and GPU.MainThread are user-interactive since Core 733 and the guest's threads run
translated code a collection does not stop; the other engine threads are in a lower class. IPA 725 snapshot: the
thread inside the collector had priority 20 and received 15.6 ms of CPU in 961 ms.
Change: the runtime's restricted callouts for the start and the end of a collection are registered once per process;
at a start the collecting thread, unless user-interactive already or outside the QoS classes, receives a
user-interactive override, ended at the collection's end, at the next start, or by the keep-alive's poll when the
collection goes on in the background. Each collection is accounted by the class of the thread that ran it (count,
wall and CPU time, the longest with its CPU time): one journal line at the session's close (`gcPause class`). No
collection is added, requested, delayed or resized; `CollectionClass.RaiseCollectingThread = false` keeps the
accounting alone.
Gate `collection-class` (91 checks; production Ryujinx.Library built; the class text compiled ahead of time for the
host with the runtime's real callouts and the fixture's platform functions): 25 of 25 collections of a utility
thread raised, user-interactive and unclassified threads never, 0 bytes allocated inside three collections, every
override ended, never two at once; overrides left by collections that go on in the background ended by the next
collection, the background thread or the poll; nothing registered on another platform, nor when the platform gives
the registering thread no override; refused and reported on a runtime without the registration.
macOS arm64 (workflow `melonx-collection-class.yml`, as an interactive job): scheduling probe (run 43315146893):
20 ms of CPU on a utility, default or background thread under cores + 2 busy user-interactive threads takes
107-120 ms, 20.0 ms with a user-interactive override (by the thread or by another), 108-188 ms once it is ended.
The adapter's class with the real runtime (run 43323499544: the fixture compiled ahead of time for osx-arm64, cores + 2
user-interactive threads in native calls of several hundred milliseconds each, as guest threads in translated code):
the runtime accepted both callouts; the collections a utility thread triggered took 10 197.8 ms for 492.7 ms of CPU
with the raising off (the longest 890.4 ms for 31.3 ms of CPU: the device's signature) and 510.8 ms for 491.6 ms with
it on; 33 collecting threads raised, none refused, every override ended; 73 ends for 64 starts (the end callouts of
background collections ran on the background thread). The same on the class as hardened after review (run
43326597266): 9 838.5 ms for 478.5 ms of CPU off, 535.9 ms for 530.9 ms on. Two earlier runs showed nothing and say why:
collections of 1.8 ms fit in one scheduling quantum (43321698351), and busy threads that come back to managed code
every 2 ms are parked by the collection and stop competing (43322419039: 475.9 ms for 390.6 ms of CPU off, 412.2 ms
for 412.0 ms on).
Device, pending: ephemeral pauses that promote under 5 MiB stay under 33 ms; `gcPause summary` "over 33.3 ms" 33 ->
10 or fewer; the `gcPause class` line shows wall within 1.5 times CPU for every class. Refuted and removed if the
long low-promotion pauses stay while that line shows wall near CPU (the time is then inside the collection: memory,
not scheduling), or if presented fps fall.
Not treated: the parts of a background collection its own thread runs with the engine stopped, the gen1 collections
that really promote 15-104 MiB, a collecting thread outside the QoS classes (counted "unspecified").

## L7 heat and sustained performance

Nothing changed for heat and nothing claimed. What 729 recorded: thermal state "nominal" for 67 one-second samples and
"fair" for 317 over the two sessions (6 minutes), never "serious". A 6-minute capture cannot show sustained behaviour.
To be read from a 20-minute Hogwarts run of the next IPA (presented fps, frame times, CPU per thread, thermal state
per second); a thermal change only if those figures ask for one. The lots above lower CPU work (array walks,
submissions) and memory traffic (free heap space): whether that lowers heat is not shown.

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
Five-adapter preparation (plus the collection class: EmbeddedSession.cs only) and six-adapter preparation (plus the
stall compaction: EmbeddedMemory.cs, WindowBase.cs, EmbeddedSession.cs): the twelve gates that read those files passed
on the six-adapter one (stall-compaction, collection-class, performance-diagnostics, bgc-keepalive,
bgc-fragmentation-guard, gc-keepalive-dormant, gc-pause-journal, teardown-phase-marks, teardown-cache,
safe-point-compaction, display-native, retention-chain); the other 92 were not run again on it. Two existing gates
were taught the later edits: display-native compares EmbeddedMemory.cs without the new entry point (and compiles the
final file), performance-diagnostics undoes the two adapters' lines of the session file before its comparison.
The Core CI runs the gates on macOS arm64: both new gates have a `--fixture-only` mode (their executed part and its
checks, without a preparation) that the workflow `melonx-collection-class.yml` runs there (run 43331900586: 24 and 18
checks). It found three things the Linux host could not: the first form of the collection-class gate published its
fixture for Linux, used Linux clock identifiers and expected "not this platform" in the plain run; and on macOS arm64
the runtime never starts a background collection without a collection before it (20 000 large allocations), so no
override is ever left for the poll there (on Linux x64 within a few hundred). Third measurement of the class on that
run: 9 206.2 ms for 489.9 ms of CPU with the raising off, 481.4 ms for 451.9 ms with it on.
Independent review of the two new adapters: collection class: no proven defect; two hardening changes
made (the end callout is registered before the start one; nothing is registered when the system gives the registering
thread no override, which would have left the end function to be bound inside a collection); the reviewer's open point,
the end callout of a background collection on the background thread, is exercised on both runtimes (macOS arm64: 73
ends for 64 starts; host: 7-11 overrides ended by the background thread per stress). Stall compaction: no proven defect
(a compaction cannot start or go on after a resume returned, two cannot overlap, no deadlock found); two risks fixed (a
frame of a closing session after its end left state for the next session: the session's run now clears it; the poll
also compacted inside host pauses, around their 3 s rule: it now does nothing in a pause); kept and known: a
compaction another path ran while the poll waited for the gate counts against the session's three.

## Handoff to main (nothing below is done by this session)

review and take the branch (wiring proposed in `prepare_embedded.py`, `ORDER`, the plan's gates `nifm-network-watch`,
`paced-strict-syncs`, `sibling-pipelines`, `array-sync-epochs`, `collection-class` and `stall-compaction`, the contract
test's expectations (218 preparation inputs, 214 prepared members) and `FRESH_GATES` 104; `origin/Claude` at `14272228`
has not touched these files since the branch point); take the head `d17a29f2` (the four commits after `7040c3e1`
change tests only and are needed for the gates to pass on the Core CI's macOS host); choose the Core number (the branch says 745) and which adapters go
in: each one is independent of the others except `adapt_stall_compaction`, which is applied after
`adapt_collection_class` (it adds its poll line after that adapter's); the branch at `8f71c4e1` is the four-adapter
proposal, at `d3d83cc0` the five-adapter one. Freeze, Core CI, pin; next IPA with that Core and the bridge capture
commits; record which Core binary the IPA holds (the journals' `coreSHA256`). Rollback of any lot: drop its adapter
from `prepare_embedded.py`, `ORDER` and the plan, freeze again.

## Device protocol for that IPA (same save, same route, 1x, async shaders and host memory budget as on 729)

 (1) cold start of the app, Hogwarts 5 min on the 729 route, close; Smash 3 min, close; Hogwarts 5 min, close; (2)
Hogwarts again, 20 min without pause; (3) send the journals (or the live capture). Read with `live_capture.py compare
<729 capture> <new capture>`: presented fps, p50/p95/p99, gaps over 100/250/500 ms per minute, footprint, and per lot
the lines named above.
Lines to read first, per lot: `sessionRetention` at each close (L1); command buffers per frame and "sync waits" (L5a);
arrayDelta per window (L5b); `pipelineVariants` "built but missed" and `pipelineSiblings` (L6); `gcPause ephemeral`
lines, `gcPause summary` and the new `gcPause class` line (L4); `memory heapCompacted` lines with the reason
`presentationGap`, then `lohFreeAfterBytes` and the footprint of the memoryInventory reports (L3); thermal state and
presented fps per second over the 20 minutes (L7).

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
