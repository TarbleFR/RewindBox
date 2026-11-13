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
