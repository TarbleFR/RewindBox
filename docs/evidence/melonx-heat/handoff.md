# MeloNX heat and energy — Hogwarts Legacy first (13 Nov)

Session 01JA5QgKeoGVH5oVjNyhcj3D. Branch `work/melonx-heat-20261113` from `Claude` (Core 745 source `ced57c6d` +
`d17a29f2`), head `a0fea59e`. No contract frozen, no Core built, no IPA. Figures come from the private journals of
IPA 733 / Core 745 (iPhone binary `2943e064`, pid 61839); no raw line is reproduced. Nothing here was measured on an
iPhone after the change.

## Before: IPA 733, same process (seconds with frames presented)

| | Hogwarts (4AC66D23, 78 s) | Smash (0D5275AF, 110 s) | Hogwarts IPA 729 (126 s) |
|---|---|---|---|
| presented frames/s (mean / median) | 29.5 / 22 | 54.4 / 60 | 20.7 / 19.5 |
| engine fps (mean) | 20.5 | 55.2 | 18.4 |
| process CPU (% of a core) | 274 | 176 | 254 |
| CPU power, all / performance cores (W, `en=`) | 2.06 / 1.82 | 1.47 / 1.34 | 1.81 / 1.60 |
| context switches / system calls / interrupt wakeups per s (`sw=`) | 69 600 / 150 000 / 4 200 | 31 900 / 84 100 / 2 500 | 55 100 / 115 600 / 3 100 |
| thermal state (seconds) | nominal 57, fair 40 | fair 129 | nominal 67, fair 80 |

`en=` counts the CPU only (the kernel's energy accounting); the GPU's energy is in no journal line.

## Where the CPU goes (733 Hogwarts, symbolized with the Core 745 map of run 43344184896)

- **Spinning before a wait: 46-48 % of the busiest threads' running samples** in the three `[MeloNX:hot]` captures
  (RHIThread 75 %, AK__EventManager 85 %, RenderThread_1 61 %, MainThread 48 %, render thread 27 %, GPU thread 7-12 %).
  Over every capture of the journal, 44 % of all samples are in one kernel call, the yield of that spin
  (`ManualResetEventSlim.Wait` > `SpinWait.SpinOnceCore` > `Thread.Yield` > `PalSwitchToThread`), 0.5 % in its pause
  loop. The waits: `KThread.SchedulerWaitEvent` (guest scheduler: `KScheduler.Schedule`, `KCriticalSection.Leave`,
  under `SendSyncRequest`, `WaitProcessWideKeyAtomic`...), `ThreadedRenderer._galWorkAvailable` (render loop) and
  `_invokeRun` (synchronous invokes). Smash 733: 37-40 %. This explains the 150 000 system calls per second.
- Guest timer (`HLE.TimeManager` 3 %, `Common.Nanosleep.*` about 3.5 % of a core): no spin on iOS (a 1 ms wait
  replaces it in this tree). No change.
- Bridge diagnostics: two utility dispatch threads 4-5 % of a core each, the live recorder 1 %, stderr and logger
  0.7 % each; the engine report drain (300 ms) already skips unchanged reports. Not attributed per component; no
  change. The native heap sampler hooks every malloc and free during the first 120-145 s of a session: both measured
  Hogwarts sessions ran under it.
- 30 fps cadence: frame intervals are 33 ms, the engine is below 30 fps most of the time (median 22): no idle time
  between frames to save; nothing changed (lowering the rate is excluded).

## Change: `adapt_wait_spin_bound` (general MeloNX, every title; nothing specific to Hogwarts)

`AdaptiveSpinEvent` (appended to `Ryujinx.Common/AsyncWorkQueue.cs`) replaces the three events. It keeps the
runtime's spin (35 iterations) for an event whose waits end inside it, and keeps only the ten pause iterations for
one whose waits outlast it. The decision is made by a waiter that blocked: the setter stamps the time (only while a
waiter blocks) and passes its own wake delay when it was woken during that wait; the waiter compares the time its wait
needed with a full spin's length, measured once. A wait returns only once its event is set. No thread, priority,
timeout or frame pacing changes. A fixed bound was measured and rejected: it loses short handoffs (1 us: 560 000/s
against 72 000), and synchronous IPC is among the spinning waits.

Gate `wait-spin-bound` (42 checks; production Common, GAL and HLE built; the class against the runtime's event, two
threads handing over as `KScheduler` does, medians of five runs):

| CPU beyond the work per handoff / rate | Linux x64 host | macOS arm64 (run 43367431612) |
|---|---|---|
| 1 us handoffs | rate 102 % | rate 100 % |
| 5 us | rate 83 % | rate 96 % |
| 40 us (edge of a full spin on macOS) | -27 % | -66 %, rate 112 % |
| 100 us | -27 % | -54 % (45.1 -> 20.7 us) |
| 300 us | -24 % | -48 % (43.7 -> 22.6 us) |
| half 1 us, half 200 us | -3 %, rate 103 % | -25 %, rate 104 % |

A ring of eight threads loses no wakeup; a wait on an unset event stays blocked and returns at Set. The nine gates
that read the three files pass on the seven-adapter preparation (two taught the later edit).

## Expected on the iPhone, and what refutes it

Same save, route and settings as the 733 capture: `sw=` system calls per second at least halved (150 000), the share of
`[MeloNX:hot]` samples in the yield (`libsystem_kernel+0xd28`) at least halved (44 %), `en=` and `cpu=` lower; presented
fps and frame-time p95 unchanged. Removed if presented fps fall, frame-time p95 rises by more than 2 ms, or `sw=` and
`en=` do not fall. A lower thermal state is claimed only from the comparison below, never from CPU figures alone.

## Comparison protocol (before = the IPA without the change, after = the IPA with it; same device)

1. Same settings both times (1x, async shaders, host memory budget, MoltenVK choice), same save and route, same
   brightness, Low Power Mode off, not charging, other apps closed, device at rest 15 min (thermal state "nominal").
2. Note the battery percentage, launch Hogwarts, play 20 min on the route without pausing, note the battery percentage.
3. Send the journals. Read after 150 s (the heap sampler's window ends there) to the end: `en=`, `cpu=`, `sw=`, `th=`
   per second, presented fps and frame times (`tools/melonx/live_capture.py compare`), the `[MeloNX:hot]` yield share,
   battery drop per 20 min, and the time to the first `fair` and `serious` states.
4. Smash 5 min the same way, to check the other game's cadence (60 fps) and its `sw=`/`en=`.

## Handoff to main

Take the branch (wiring in `prepare_embedded.py`, `ORDER`, plan gate 105, contract 219 inputs / 215 members,
`FRESH_GATES` 105), number the Core (the branch says 747), freeze, Core CI, pin, IPA. Rollback: drop the adapter from
the preparation, `ORDER` and the plan.

## Core 747 CI (run 43423803238, macOS arm64): `wait-spin-bound` long100 failed; follow-up (local, not pushed)

Failure: at 100 us the candidate ended with the full spin in three runs of five (budgets [10,10] [35,35] [35,10] [35,35]
[10,10]) while the energy criteria held (CPU beyond the work 30.41 against 46.80 us, 7718 against 8000 handoffs/s).
The maintainer's 32d035149 / 7aa8d1512 then compiled the Core without fixture replay (build-smoke) and kept the
failure as unverified evidence.

Cause (reproduced on Linux x86_64 with three busy processes on four cores): not an inflated calibration (the class's
measured full spin stayed 8-16 us), but host contention. A wait that ends inside a spin whose yields another thread
stretched (it held the core) counts as short, by design: such a spin gave the core away rather than burning it. On a
saturated host the budgets move both ways (short handoffs reduce too) and the candidate's CPU equals the control's.
Refuted: timing the spin's yield phase to count stretched spins as long (it also reduced 5 us handoffs under load,
-20 % rate in one run); not kept.

Found on the way: the single calibration sample measured 387 us against 8-23 us in one loaded process of thirty; on
the iPhone that would count every wait shorter than it as short for the whole session. Product change: the shortest
of three samples (a stretched yield only lengthens one).

Fixture defect found on the way: the ring's stop was racy (the token holder's own Reset could erase the stop's single
Set and its predecessor's, then wait for ever: `joined` false once, independent of the class). The stop is now
signalled until every thread ends, and the ring must advance in every 250 ms window (a lost wakeup stops it for good).

Gate change: long100 asserts the energy criteria (CPU at most 85 %, rate at least 90 %) and one run or more ending
with the pause iterations on both events; long300 keeps five of five; the measured spin lengths are reported. Linux
x86_64, final preparation (Core 747 preparation with the three-sample calibration): 42 checks passed; CPU beyond the
work -25 % (40 us), -33 % (100 us), -23 % (300 us); rate 106 % (1 us), 92 % (5 us), 101 % (100 us); ring 2325 laps,
no stalled window, every thread ended. macOS: not run after the change.

## Heat lot 2: `adapt_darwin_timed_waits` (general MeloNX, Apple platforms; local, not pushed)

Evidence (IPA 733, Hogwarts, 44 s of play, `[MeloNX:stall]` per-thread CPU): HLE.TimeManager 3.0 % of a core, the
eight nanosleep helper threads 2.5 %, SurfaceFlinger.Composer 0.6 %, all user-interactive. On iOS a guest deadline
under a millisecond away is served by a helper thread that nanosleeps then signals the timer thread (two threads and
four kernel wakeups per deadline); the compositor wakes 150-300 us early and spins to each 60 Hz interval.

Change (PreciseSleepHelper.cs only): on Apple platforms the timer thread's event is one `dispatch_semaphore_wait` with
the deadline as timeout (Signal posts it), and the compositor's final approach is `mach_wait_until` on the same clock
before the unchanged spin loop. Same deadlines, same rate and cadence, no thread class changed; the helper threads
are no longer started there. Other platforms take the previous path.

Defect found in review and fixed before any build: the first version cleared the signal mark before draining the
semaphore; a Signal between the two left the mark set without a count, so later signals posted nothing and the timer
thread could sleep to its deadline or for ever. Now the waiter drains, then clears. A Signal after Dispose (KTimeManager
signals at shutdown while the timer thread may dispose the event) does nothing; the semaphore is released once by the
last holder.

Gate `darwin-timed-waits` (28 checks on Linux x86_64): static checks; production Ryujinx.Common and HLE built; the
event's protocol on every host with a stand-in semaphore (3 x 1 000 000 signals from two producers, none lost; the
first version lost one within 2 000-6 000 and its waiter never woke again; 5 000 signal/Dispose races: no exception,
no use after release, one release each; deadline, prior signal and coalescing semantics); the timer and compositor
loops against the control: on Linux the same path (NanosleepEvent with its helper threads). The Apple timing (lateness
within 100 us of the control's, lower CPU per deadline and per frame, no helper thread) runs only on macOS: not run.

Expected on the iPhone (same protocol as above): HLE.TimeManager plus Common.Nanosleep.* from 5.5 % of a core to under
2.5 %, SurfaceFlinger.Composer under 0.3 %; presented fps, frame times and audio lateness (`dsp=`) unchanged. Removed
if frame times or audio lateness worsen, or the timer threads' CPU does not fall.

Examined and not changed: guest thread priorities mapped to QoS classes (risky for synchronization, background
threads about 3 % of a core); the 30 fps pacing of Hogwarts (median engine rate 22 fps: no slack to remove); the
filesystem's SHA-256 (about 1 %: it verifies data); the bridge diagnostics (9-13 %, unattributed, MeloNX owner's
domain).

Freeze (both lots, build-smoke route of 32d035149): one prepare_embedded pass on a copy of pristine upstream 13700519
(tree 82a29e6f), identical to the tested candidate preparation and differing from Core 747's only in AsyncWorkQueue.cs
and PreciseSleepHelper.cs. Receipts: Core 747's for the unchanged gates; fresh on the final preparation for
`wait-spin-bound`, `darwin-timed-waits` and the nine gates that iterate the adapter order. freeze_dma_core.py with the
delivered 614 archive: 220 inputs, 216 members, 102 changed files, 106 gates, contract SHA-256
5c22b28358f3885452255de5ef63a49ec174f52544f65e33eec3ad8cc4040f8a; contract test with the archive: 533 checks passed.
Open: the Apple timing of both fixtures on macOS arm64 (the Core route no longer runs them; the Core's two simulator
sessions execute the Apple path); the Core pin and an IPA; the iPhone comparison.

## Delivered: private IPA 735 (13 Nov)

Core c4a25b94 (run 43450861032, both heat lots, build-smoke: NativeAOT and ABI verified, two simulator sessions) pinned
in 89cdde162; IPA 735 (run 43454088313, base 733 like 734, MeloNX replaced, every other engine reused with its verified
fingerprint, Flutter/native groups not-run) downloaded, decrypted and verified offline (IPA SHA-256 b353de8b, 330 025 005
bytes), handed to the user, receipts in `docs/evidence/rewind735/`, recipient key deleted. Not yet run on an iPhone:
the 20-minute comparison above (734 or 733 before, 735 after) is what tells whether the heat fell.


## IPA 736 on the iPhone (13 Nov): what the journals show, and the lot that follows (no probe added)

Private journals, read with `tools/melonx/live_capture.py` and the per-second, freeze, hot and core lines. Hogwarts
Legacy: IPA 733 (pid 61839, 97 s) against IPA 736 (pid 2349, 186 s; same Core as 735). Smash: IPA 732 against 736.

| | 733 | 736 |
|---|---|---|
| Hogwarts, presented frames per second (whole session) | 23.7 | 26.4 |
| frame interval p50 / p95 / p99 | 33 / 100 / 183 ms | 33 / 83 / 133 ms |
| thermal state | nominal 57 s, then fair | nominal for the 186 s |
| before the world loads: CPU power, context switches, system calls per second | 1.71 W, 37 976, 139 406 | 1.57 W, 23 312, 86 258 |
| in the world, at the same decompression (92-94 MiB/s): the same three, and fps | 1.60 W, 57 686, 102 710, 20.0 | 1.31 W, 36 674, 79 656, 22.8 |
| Smash in play (nominal in both): CPU power, system calls per second | 0.68 W, 78-79 k | 0.64 W, 45.7 k |

Both sessions are too short for a heat verdict (the 20-minute protocol above stays open); what is measured is the CPU
power and the kernel traffic. Against the lots' own expectations: system calls fell by 22-38 %, not by half (lot 1);
the timer threads went from 5.6 % to 3.7 % of a core, not under 2.5 % (lot 2: the nanosleep helpers are gone, the timer
thread itself stayed).

Why the frame rate swings (both IPAs): when the world loads (t = 47 s) the footprint goes from 3.6 to 4.4 GiB in one
second and the device has 4-8 % of its memory available from then on (127 of 140 s; 9-11 % in the others); iOS
compresses and decompresses the process's memory without pause (30-500 MiB per second). Frames per second by
decompression in the same second, IPA 736: 29.9 under 5 MiB/s, 24.6 at 20-60, 21.9 at 60-150, 18.8 above 150. At
t = 210 s: 1.19 GiB resident, 5.5 GiB (logical) compressed; graphics 1.41 GiB, malloc 1.0 GiB, managed 0.67-0.8 GiB (650 MiB
live), guest lease up to 4.0 GiB. The memory itself is the cause; what follows are the aggravators the journals show.

The lot (four changes, each general; expectations are for the same save and route as the 736 capture):

1. *`adapt_wait_spin_bound`, the yields bounded in time (AsyncWorkQueue.cs).* 40 % of the running samples of the
   busiest threads are still inside the spin's yield (11-13 % at the start, 42-61 % in the slow phases; RHIThread 75-86 %,
   AK::EventManager 79-88 %), and `hw=` counts 210 % of a core's time waiting for a core in the world (27 % before): on a
   device whose cores are taken a yield returns late, the event is often set meanwhile, the wait counts as short and
   the full spin stays. Now the yields of one spin stop once they have lasted twice a whole spin on a free core, and
   the wait's length is counted from its real start. Expected: the yield's share of running samples in the slow phases
   under 20 %, `sw=` system calls lower; refuted if frame gaps or audio lateness rise. Host, for information (Linux
   x86_64, 4 cores taken by 4 busy processes, 8 interleaved runs, median handoffs per second before and with the bound):
   partner answering in 1 us 3 400 and 79 000, in 5 us 64 300 and 91 600, in 1 or 200 us 3 000 and 7 500; on a free host
   the gate's figures are unchanged.
2. *`adapt_timer_earliest_wake` (KTimeManager.cs).* The guest timer thread (3.7 % of a core, mostly in the kernel) was
   signalled at every new deadline; it is now signalled only by a deadline earlier than the one it sleeps for. Deadlines
   and their order are unchanged. Expected: HLE.TimeManager's CPU and context switches lower; refuted if a guest wait
   with a limit ends late.
3. *`adapt_keepalive_memory_hold` (EmbeddedSession.cs).* All 17 gen2 collections of the play were the keep-alive's
   requests (one per 13 s). The samples with the background collector running decompress 26.2 MiB per 100 ms against
   10.1 and are inside a frame gap over 100 ms in 17 % of cases against 5 % (733: 21.5 against 10.4, 21 % against 8 %).
   With 8 % or less of the device's memory available no request is made (a held window stays held under 12 %); Smash
   plays at 9-15 % and keeps its requests. Cost, stated: the runtime's own gen2s are one to three minutes apart, 22 %
   of those after an idle exit of the collector's thread ran blocking (100-950 ms, docs/melonx-bgc-fallback-2026-11-05.md),
   and between them the heap keeps what a request would have freed (the LOH's free space fell by 5-65 MiB between two
   requests). Expected: `vm=` decompression and gaps over 100 ms per minute lower in the world; refuted and removed if
   gaps over 250 ms per minute exceed the 736 figures (1.14-8.66) or the footprint in the world rises by more than
   150 MiB.
4. *`adapt_buffer_last_hit` (BufferCache.cs).* Buffer.OverlapsWith is the largest single place of GPU.MainThread
   (7.4 % of its running samples): three binary searches of the buffer list per use of a range. Sixteen slots remember
   the last buffers returned; a range one of them contains is answered without a search; every removal from the list
   empties them. Expected: that share under 2 %; the same buffer is returned for every range.

Seen and not changed in this lot: the ephemeral collections (131 gen0 and 95 gen1 in 250 s, gen0 about 23 ms and gen1
about 60 ms each, 30-70 ms of pause per collection in the world; 12-19 MiB allocated per second, 2-8 of them on the GPU
thread, 1-7 on the render thread, the rest on threads the windows do not attribute; gen1's budget is fixed at 6 MiB by
the concurrent collector); the stall compaction that ran 436 ms inside a 1.9 s gap (three at most per session, it gave
150 MiB back); the occlusion query readback (77-220 ms per second, a user setting); MoltenVK's descriptor pools and
shader modules (330 MiB of malloc, cold: about a third would be physical gain); the shared array pool, emptied at every
gen2 because the memory load (94 %) is above 90 % of the configured threshold (change 3 lowers the number of gen2s).

Gates: no new one. The existing gates that bind the four files were run again on the final preparation and adapted to
the new composition where they name the later adapters of a file (cold-buffer-trim, evicted-buffer-recreate, which now
executes the last-hit members with its evictions, host-thread-class, collection-class, performance-diagnostics,
hogwarts-dma-copies, kernel-timer-allocations: the final timer manager gives the delivered one's functional digest
over its 195 scenarios). Not measured on an iPhone: every expectation above is for the next capture.
