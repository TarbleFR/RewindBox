# MeloNX lot 11 — device protocol (IPA with Core 731)

Core 731 is Core 729 plus one adapter (`adapt_cold_buffer_trim`): while only the device is short of memory, a trim of
the GPU buffer cache gives back the buffers nothing used for a minute of play instead of a quarter or a half of the
buffers in use. It ships with the same five-part MoltenVK as Core 729. The protocols of
[Core 729](../melonx-729-gates/device-protocol.md) (two sessions, the same route, nothing deleted between them),
[Core 727](../melonx-727-gates/device-protocol.md) and [Core 725](../melonx-725-gates/device-protocol.md) apply
unchanged; this page lists what lot 11 adds. Nothing here was run on an iPhone: every device figure below is IPA 724's,
for comparison.

## What IPA 724 showed (Hogwarts Legacy, pid 49375), one command
`python3 tools/melonx/buffer_trim_report.py MeloNX-stderr.log MeloNX-core.log MeloNX-core.log.1 --pid <pid>`

IPA 724: 24 trims in 150 s (the device at 4 to 9 % available, 1.3 GiB or more of headroom in this process), about
986 MiB "released" from a cache that every 30 s report finds at 85 to 127 MiB again.
- 5 s windows with a trim (20, 104 s): 867 to 7 026 buffers created (median 3 816), 70 365 in all in 7.6 s of the
  render thread; 46 747 disposed in 0.85 s (listed after the Critical trims only).
- windows without (16, 92 s): 0 to 1 724 created (median 223), 6 834 in 0.49 s; none disposed in the list.
- the window of the 4.3 s gap after the pause: 2 565 buffers disposed, 805 created (3.2 s, a collection suspended the
  thread meanwhile).
These times are the journal's (a command's time includes what suspended its thread). The end-to-end share of the
frame time is not known: neither thread is saturated in those windows.

## 1. The cycle is gone (both sessions)
- Same command. Expected: the windows with a trim or a `coldTrim` record create about as many buffers as the others
  (hundreds, not thousands), and `BufferDispose` leaves the lists.
- `MeloNX-core.log`: `bufferCache coldTrim: pass N: released B buffers (X MiB) unused for 60 s of play, left Y MiB
  above the target in use; cache C of L MiB; so far ...`. The first pass, then at most one record every 10 s while
  passes release something and one a minute otherwise (160 at most). Expected in play: small or zero releases, Y near
  a quarter or a half of the cache.
- `MeloNX-stderr.log`: "Host reported ... released N MiB of GPU caches" now counts textures and cold buffers only; a
  pass that releases nothing writes no such line (the `coldTrim` records count the passes).
Would refute: thousands of buffers created in the windows with a `coldTrim` record whose releases are small (the
creations then have another cause), or `coldTrim` records releasing most of the cache every few seconds (the game's
buffers are not used within a minute: the age is wrong for this title).

## 2. What the cache then holds
`memoryInventory` records (every 30 s): `bufferCacheBytes`. IPA 724: 85 to 133 MiB under the trims. Expected: what the
game used within the last minute; unknown until this run. To report: its median and maximum in play, with the
footprint and the device's available share of the same records. Would call for a shorter age: a cache staying above
about 250 MiB while the device is at 5 % or less.

## 3. Frame times
`python3 tools/melonx/frame_budget.py MeloNX-performance.log --pid <pid> --window 52-72 --window 88- --window 107-`
(seconds adjusted to the session as in the Core 729 protocol). Reference, IPA 724: after 88 s 89.0 ms per frame,
excess +55.6 = stutters +36.2 (220 gaps over 100 ms, six over 1 s) + slow frames +19.9 - 0.5. This lot and lot 10 are
measured together in this IPA: the tools above say which mechanism is gone, the frame budget says what the frame
gained; neither is attributed a share without a run that separates them.

## 4. How the CPU time is served (new `hw=` field of the bridge, with `vm=`)
`hw=G/I/P/W` on each per-second line from the second one on: the clock of the process's CPU time (cycles per
nanosecond of CPU time, GHz), instructions per cycle, per cent of the CPU time on performance cores, and the time its
threads were ready to run without a core, per cent of the CPU time used. `frame_budget.py` prints, per window, their
medians, the instructions executed per presented frame, and the `vm=` totals (MiB compressed and decompressed).
What it settles, which IPA 724 could not (no stage of the chain is saturated while the FPS halves after 88 s, and the
CPU time per frame doubles on every thread):
- instructions per frame about the same in 52-72 s and after 88 s, instructions per cycle lower: the threads wait on
  memory (to read with the decompressed pages of `vm=`);
- instructions per cycle the same, clock or performance-core share lower: the threads are served by slower cores
  (scheduling or heat; `th=` says which);
- ready-without-a-core high: more runnable threads than cores;
- instructions per frame higher: the scene asks for more work.
`pc=a,b,...`: for each thread listed in `cpu=`, in its order, the per cent of that thread's CPU time on performance
cores ("-" when unknown; the field is absent if iOS refuses the per-thread counts to the app, which is itself the
answer that this measure is not available). IPA 724 lists the guest's own threads (`<MainThread>`, `<RenderThread_1>`,
`<RHIThread>`) at priority 31 and the engine's GPU and render threads at 47; `frame_budget.py` prints each steadily
listed thread's median share of a core, its priority and its median share on performance cores. A guest thread mostly
off the performance cores while they are not full (`hw=` ready-without-a-core low) is what would justify raising the
guest threads' class in the next Core; the same share for every thread would not.
The two ratios of `hw=` that use times (performance cores, ready without a core) assume the kernel counts those times
in one unit. The first cannot exceed 100: if it does, the units differ and both ratios are to be reported as such,
not interpreted (the second may exceed 100 by itself: threads that wait longer than they run).
To report: the `frame_budget.py` lines of each window, for both sessions.

## 5. The resume after a pause
As the Core 727 protocol (after five minutes, pause 30 s, resume). IPA 724: one gap of 4 283 ms, 15 frames in the
6.2 s after the resume, with the 793 MiB cache rewrite (10.9 s) still running and 2 565 buffers disposed then created
again. Expected: no rewrite (Core 727 and 729), no buffer disposal at the resume (a pause ages nothing); to report: the
gaps of the ten seconds after the resume and the window's `CreateBufferAccess` / `BufferDispose`.
