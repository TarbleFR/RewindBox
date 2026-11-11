# MeloNX lot 12 — device protocol (IPA with Core 733 and the lot 12 bridge)

Lot 12 comes from the first device run of lots 9 to 11 (IPA 725, Hogwarts Legacy, pid 51986, one session of 182 s
sampled; private journals, aggregates only). It changes who runs what, not what is rendered:

| Change | Where | What it acts on |
| --- | --- | --- |
| Engine calls of the host's utility queues are made by one user-interactive thread | bridge (`MeloNXEngineCallClass`) | a collection triggered by those calls no longer runs at priority 20 |
| The diagnostics snapshot keeps its bytes | Core 733 (`EmbeddedLaunchDiagnostics`, the `neostation_melonx_diagnostics` export) | the 300 ms poll no longer allocates (about 0.9 MiB each time with a ring of long records, host runtime) |
| Guest threads, HLE service threads, the kernel's timer and preemption threads, the sleep pool, the compositor and the audio workers ask the user-interactive class | Core 733 (`adapt_host_thread_class`) | they ran at priority 31, 20 to 35 % of their time on performance cores in the slow stretches |
| `hw=` writes the time waiting for a core and both clocks; `[MeloNX:hot]` profiles | bridge (measurement) | says where the time of the slow stretches goes |

Nothing here was run on an iPhone. The protocols of [Core 731](../melonx-731-gates/device-protocol.md) and before apply
unchanged (two sessions, the same route, 20 minutes, a pause after five); this page lists what lot 12 adds.

## What IPA 725 showed (reference for this lot)
`python3 tools/melonx/frame_budget.py MeloNX-performance.log --pid 51986 --window 103-180 --window 127-146 --window 149-158`
- t=103-180 (the part of the session the export holds): 1 713 frames in 78.0 s, mean 45.5 ms (22.0 FPS), median 33.3,
  p95 83.3, p99 166.7, longest 3 033 ms; excess +12.2 ms = stutters +5.5 (47 gaps over 100 ms, 11.0 s) + slow frames
  +7.2 - 0.6. IPA 724 after 88 s: 89.0 ms, excess +55.6 (another session, a comparable period, not the same route).
- t=127-146: 20 s on target (mean 33.8 ms, 29.6 FPS, p95 33.3, one gap over 100 ms): about 239 million instructions
  per frame, 64 % of the CPU time on performance cores.
- t=149-158 and 103-118: 22.3 and 20.8 FPS with 456 and 531 million instructions per frame, 48 % on performance
  cores; `<MainThread>` 46 to 50 % of a core at priority 31 with 33 to 36 % of it on performance cores, the render
  and GPU threads 52 to 55 % of a core at priority 47 with 80 to 95 %.
- The 3 033 ms gap: a gen0 collection of 2 673.6 ms. The stall record resolved with the Core's symbol map: the
  thread of the host's diagnostics queue (priority 20) in `gc_heap::garbage_collect` (`mark_through_cards_for_segments`,
  from `GCHeap::Alloc`), 15.6 ms of CPU in 961 ms, 148 threads waiting for it.
- Collections: 4 619 ms of pause in the 83.5 s of the 5 s samples (2 788 ms in the window of that gap; 20 to 208 ms
  in the others); 16 background collections in 188 s.
- The engine's own timers in the slow stretches (5 s samples): GPU thread dispatch 3.0 to 3.8 s of 5.1 s for 995 to
  1 488 draws a frame, of which texture binding commits 1.2 to 1.6 s and compute dispatches 0.8 to 1.0 s; render
  thread 2.5 to 3.4 s. In the 20 s on target: 277 to 395 draws a frame, dispatch 1.9 to 2.2 s.
- The buffer cache cycle of lot 11 is gone (windows with a trim create 0 buffers at the median; 11 `coldTrim` records).

## 1. No collection run at a utility priority
- `[MeloNX:stall]` records: with the symbol map (`Ryujinx.Library.symbols.txt.gz` of the Core artifact), the thread in
  `gc_heap::garbage_collect` must not be at priority 20 or 4. The engine calls of the journal now come from the thread
  `RewindBox.MeloNX.EngineCalls` (priority 47).
- `MeloNX-core.log`, `gcPause summary` at the close: longest gen0 and gen1 pause (IPA 725: 2 673.6 and 213.7 ms), the
  count over 33.3 ms (37) and the total pause (4 623 + 2 119 ms seen).
- `gcEvent background` records: IPA 725 has 16 in 188 s. The snapshot no longer allocates in the large object heap at
  every poll; expected: fewer. Would refute the link: the same rate.
- `cpu=`: the thread of the diagnostics queue (an unnamed `threadNNN` at priority 20, 5.1 s of CPU by t=120 in IPA 725)
  should use much less.
To report: the stall records if any (thread, priority, top frames), the `gcPause summary` line, the count of
background collections and the session's length.

## 2. The threads of the frame chain in the user-interactive class
- `cpu=`: `<MainThread>`, `<RenderThread_1>`, `<RHIThread>` and the other `<...>` threads at priority 47 (31 in
  IPA 725), as `AudioProcessor.Worker`, `HLE.TimeManager`, `SurfaceFlinger.Composer` when listed.
- `MeloNX-core.log`: a record `hostThreadClass refused` means the system refused the class to a thread (written once,
  with the thread's name and the error): to report as it is.
- `pc=`: their share of CPU time on performance cores (IPA 725: 20 to 61 %). With two performance cores and five busy
  threads at the same priority the shares cannot all be high: to report per thread, with the render and GPU threads'.
- `hw=` (six values now): the fourth is the time the process's threads waited for a core, per cent of the CPU time
  (IPA 725, corrected: 137 to 182 % at the median of the windows above); the fifth and sixth the clocks of the
  performance cores and of the others.
- `dsp=`, `out=`: late DSP episodes and audio starvations (IPA 725: 1 965 episodes and 349 starvations in 182 s).
- `th=`: the thermal state (IPA 725: fair throughout). More work on the performance cores can heat the device: a
  state of serious or critical after some minutes is to report first.
Two points the independent review left to the device: `SurfaceFlinger.Composer` spins up to 2 ms before a vertical
blank and now does so at the engine threads' priority (its share in `cpu=`, if it is listed, and the stall records say
whether that matters); a stall record showing raised threads waiting while a thread at priority 31 holds the guest
kernel's lock would be a priority inversion to report with its frames.
Would refute the change: the guest threads still at 31 (the class is not applied), or at 47 with the frame times of the
slow stretches unchanged and the render and GPU threads' share on performance cores fallen as much as the guest's rose
(the cores are full: only less work per frame helps).

## 3. Where the time of the slow stretches goes (new `[MeloNX:hot]` lines)
`python3 tools/melonx/hot_spots.py MeloNX-performance.log --pid <pid> --symbols Ryujinx.Library.symbols.txt.gz --binary Ryujinx.Library.dylib`
(both files are in the Core artifact the IPA was built from). A profile is taken after three lines in a row under
26 FPS ("slow", at most four) and after three at 28.5 FPS or more ("base", at most two): the six busiest threads, 300
samples 10 ms apart. The tool prints, per thread, the share of the samples running, where they are by image (translated
guest code, the engine, MoltenVK, system libraries), the engine's functions with the most samples and, for each call
site, caller -> callee with the samples spent under the call. This is the measurement the next optimisation of the GPU
and render threads will be chosen from: nothing is to be interpreted on the device, the lines are to be sent with the
journal.

## 4. Frame times
`python3 tools/melonx/frame_budget.py MeloNX-performance.log --pid <pid> --window 60- --window <slow stretch> --window <stretch on target>`
The verdict's criteria are unchanged (mean and median at 29.5 FPS or more, p95 40 ms, p99 50 ms, no pause over 1 s,
20 minutes, a normal end, footprint 4 GiB, slope 5 MiB a minute). IPA 725 does not meet them (22.0 FPS over the 78 s
exported, one pause over 1 s, footprint up to 4 795 MiB); what this lot gains is not known until the run.
To send: the whole `MeloNX-performance.log` **and its rotated file** if the export offers one (IPA 725's export began
at t=103: the first 102 s were in a file that was not sent), `MeloNX-core.log`, `MeloNX-stderr.log`.
