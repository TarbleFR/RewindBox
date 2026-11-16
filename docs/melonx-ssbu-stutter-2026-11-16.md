# Super Smash Bros. Ultimate on the iPhone: where the stutter of IPA 760 comes from, and the lot that follows — 16 November 2026

Maintainer request: more recent journals of Super Smash Bros. Ultimate; go further and be done with the stutter.

Source: one session of IPA 760 (Core `127b72b9`, iPhone 16 Pro Max, 8 GB), 1 207 s, async shaders off, shader cache
on. The journals are private; everything below is counts and times. Tools: the per-second lines, the 5 s render-stage
and build-journal records, the `[MeloNX:freeze]` records decoded with the Core's symbol map, and MoltenVK's own
statistics where a session has them.

## 1. The session

- Frame rate: 60.0 FPS at the median, 58.6 on average. 203 presentation gaps of 50 ms or more, 28.8 s in all
  (118 of 100 ms or more, 27 of 250 ms or more, 5 of 500 ms or more).
- Not memory: footprint up to 5.0 GiB, but 43 pages decompressed per second at the median. Not heat: thermal state
  nominal. Not the processor in general: 182 % of six cores at the median.
- The stutter is not spread evenly: 28.2 s of the 28.8 s of gaps fall in 42 of the 238 windows of 5 s.

## 2. Causes, ranked

### 2.1 The first compile of a shader new to this device (largest)

- 345 programs were translated during play (shaders the 32 earlier sessions had never met). The build journal counts
  253 compiles of 50 ms or more on the compile threads, 24.8 s in all, 98 ms each.
- The render thread's time to obtain pipelines in draw preparation is 62 ms per 5 s window at the median and 38.7 s
  over the session: 25.7 s above the median, in the same 42 windows. Each compile is waited for in full: the draw
  that needs the shader cannot be made without it (no draw is skipped with async shaders off).
- Where the 98 ms go, from MoltenVK's statistics in the SSBU sessions of IPA 718 to 759 that have them: 3 to 4 ms per
  stage to convert SPIR-V to MSL, 24 to 34 ms per stage for Metal to compile the MSL into a library, 13 to 16 ms per
  pipeline for the rest. A vertex and a fragment stage, one after the other.
- Not a thread priority matter, which was the first reading: in 16 of the 35 gaps of play the freeze watch sampled,
  no thread of the process runs at all (the compile thread, the render thread and the GPU thread all wait: the work
  is in Metal's compiler, outside the process), and the 3 compiles the render thread made itself, at priority 47,
  took 116 ms each.
- One after the other. By size, the gap time is 11.2 s in gaps under 150 ms (one compile), 6.7 s in gaps of 150 to
  250 ms and 10.4 s in gaps of 250 ms or more: two compiles or more in the same frame.
- Already in place and working: a second visit is cheap. The programs are written to the disk shader cache (345 of
  345), the pipeline states to the variant journal, and at launch 2 047 variants were rebuilt in 2.6 s (1.3 ms
  each, Metal's own cache). 683 pipeline states new to a known program cost 1.4 s in all.

### 2.2 The game's own main thread, busy for 100 to 230 ms

In 14 of the 35 sampled gaps the game's main thread runs for more than half of the gap, in translated game code (34
of 35 samples), with little kernel time. This is the game working when new content arrives, in the same windows as
the new shaders. Nothing in the engine waits there. Not addressed by this lot.

### 2.3 Background collections

In 3 of the 35 sampled gaps the background collector runs for 92 to 177 ms. The session had 236 collections that
stopped the engine, 5.1 s in all, the longest 279 ms.

## 3. Why the compiles of one frame ran one after the other

Read in the source of the prepared engine:

- A program is created by the render thread: by its CreateProgram command, or earlier by `ProgramQueue.ProcessQueue`,
  which creates every program the GPU thread has queued so far. While the render thread waits inside a draw for the
  first program's pipeline, the GPU thread goes on translating the frame and queues the next programs, and nothing
  creates them. Their compiles start only when the wait is over.
- A program's first pipeline is scheduled high priority, not demanded. The one pipeline worker of a 6-core iPhone
  takes it at once. The demand thread takes demanded compiles only, and the draw's promotion of a compile a thread has
  already taken changes nothing. So in a burst the worker compiles every program in turn and the demand thread waits.

## 4. The change: `adapt_draw_wait_lanes`

- The draw's wait creates the queued programs. `BackgroundCompilationScheduler.WaitForPipelineAtDraw` replaces the
  plain wait of a draw and of a dispatch for a pipeline compile: on the render thread it runs the program queue's own
  `ProcessQueue`, then waits in slices of 4 ms and runs it again after each. The programs the GPU thread queues during
  the wait exist at once and their compiles are scheduled.
- A second thread compiles during the wait. While the draw waits and the compile it promoted is one a thread already
  runs, the demand thread, when no demanded compile is queued, takes the first high priority compile instead of
  waiting. A draw whose compile is not queued yet leaves the demand thread free for it, as before.
- The render-stage journal line gains the draws that waited for a compile, the time, the programs created during
  those waits and the compiles the demand thread started ahead.
- Not changed: which pipelines are built, their keys, the draw that binds each and when it is made; no draw or
  dispatch is skipped and none is made before its exact pipeline exists; async compile skip; the order in which
  programs are created; teardown; the shader module queue.
- What it costs. Two pipeline compiles run at once during those waits, and the render thread wakes every 4 ms. After
  such a wait the demand thread can still be busy with the compile it started ahead when a draw demands another one;
  that one then goes to the worker if it is free, or waits for the first of the two to end. The compile started
  ahead is the next program created, which is the next program drawn. Two programs of the same code that arrive in
  the same wait can both compile a pipeline the second used to take from the first (8 pipelines were taken that way
  at one launch of Hogwarts Legacy, none in this SSBU session).
- Reviewed. An independent reading of the first version found no hang, no lost wake-up and no draw without its
  pipeline, and two cases where the second thread started ahead when it should not (a draw whose compile was not
  queued yet; after the awaited compile had ended). The rule above closes both; each has its scenario in the gate.

### Status

| Step | State |
| --- | --- |
| Implemented | Yes: adapter, wiring, journal clause |
| Tested | On Linux, the real scheduler and the real program queue with a timed compile of 200 ms in place of Metal (gate `draw-wait-lanes`, 128 checks): a frame with five new programs goes from 1007 ms to 604 ms, with two from 402 ms to 209 ms, with one it stays 201 ms; every pipeline is compiled once, by the worker or the demand thread; no draw precedes its pipeline; a demanded compile keeps its precedence; without a draw waiting, or for a draw whose compile is not queued yet, the demand thread takes nothing else; off the render thread the wait is the plain one; a failed compile is thrown as before. The 111 gates of the Core pass on the final preparation and the contract is frozen (`9563a0bc`) |
| Compiled | Yes: Core `a80b212f` (run 43968706324, build-smoke: NativeAOT compile for the iPhone and the simulator, exported ABI, two simulator sessions). The iPhone binary holds `WaitForPipelineAtDraw`, `RenderThreadPrograms.CreateQueued`, the queue's `BeginDrawWait`/`EndDrawWait` and the journal clause. Pinned (artifact 14278297391, iPhone binary `368895c6`, packaged fingerprint `f74a9313`, contract `9563a0bc`, 111 gates) |
| Delivered | Yes, privately: IPA 764 = IPA 763 + this Core (run 43972478592, IPA `0b235a9f`, 331 357 290 bytes; verified offline after download: 97 native images, the MeloNX Core's packaged fingerprint `f74a9313`, 48 retained fingerprints). Flutter and native test groups not run |
| Observed on a device | No |

Expected on the iPhone, in a session that meets new shaders: the render-stage lines show programs created during the
waits and compiles started ahead; the render thread's wait for compiles falls below the compile threads' total of the
build journal (they were equal: 25.7 s against 24.8 s); the gaps of 150 ms or more shorten. Refuted, and the adapter
removed, if no program is created during the waits or if those gaps do not shorten. No frame rate gain is claimed.

What this lot does not do: a gap made by a single compile (11.2 s of the 28.8 s, 98 ms each at the mean) keeps its
length. Whether Metal's compiler serves two requests at once as fast as one is not known here.

## 5. Leads not taken

- The two stages of one pipeline compiled at the same time inside MoltenVK (24 to 34 ms saved per new program if
  Metal serves both at once). MoltenVK converts and compiles the vertex stage, reads its result, then does the
  fragment stage; the second depends on flags of the first. A change inside MoltenVK, to be proven on macOS first.
- A second pipeline worker on six cores (three compiles at once). It also doubles the background compiles at launch
  and in play, and adds a worker cache; to be weighed after the device reading of this lot.
- The option "async shaders" of the game's settings removes these waits by drawing a new object a few frames late.
  It is the player's setting; nothing here changes it.
- The variant journal holds 2 048 states and gave up 700 for newer ones in this session. Those states are rebuilt in
  2 ms each when met again; raising the bound costs memory and launch time for 1.4 s per session.

## 6. Delivery 764: the images that changed without being declared

The verification of IPA 764 lists four bridge images whose fingerprints differ from the base's while their sources
are the base's (the 17 effective differences from IPA 763 are this lot's engine preparation, test and note files):
`dolphin_internal_bridge` (`35db8bc4`, base `f3614b8f`), `libretro_internal_bridge` (`0cb53f3e`, base `da21cb1c`),
`melonx_internal_bridge` (`c029bdcf`, base `e8a0bf4e`) and `rpcs3_internal_bridge` (`f852400e`, base `5cfa0b5b`).
Each of the four values is one an earlier delivery already carried with the same sources: 759 and 757 for the first,
758 and 757 for the second, 761 and 756 for the third, 761 and 760 for the fourth. The receipts show each bridge
alternating between two fingerprints from build to build. For the MeloNX and RPCS3 bridges the two files were
compared section by section on IPA 761 and 763 (RPCS3 session, 16 November): one byte of `__stubs` and one byte per
stub of `__objc_stubs`, two neighbouring import slots bound to the same symbol in one order or the other. No clear
copy of IPA 763 exists here (its recipient key is deleted), so the comparison was not made again; nothing to classify.
