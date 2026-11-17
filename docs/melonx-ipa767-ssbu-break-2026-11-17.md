# MeloNX, IPA 767: Super Smash Bros. Ultimate stops by its own break, not by memory — 17 November 2026

Private journals of the maintainer's second SSBU test of IPA 767 (Core 58319c2c, pid 33274, 10:03:15 to 10:32:14 UTC).
Counts and times only; no raw journal is kept in Git. Maintainer's report: SSBU crashed and the app went back to the
home screen.

## What ended the process

- At 10:32:14.979 the Core journal reads "KernelSvc Break: The guest program broke execution!", then every other guest
  thread's wait returns TerminationRequested, then the crash line: GuestBrokeExecutionException, unhandled, thrown by
  Syscall.Break. The game itself called svcBreak; Ryujinx ends the process on it (TerminateCurrentProcess, then the
  exception), and an unhandled exception ends the app.
- It was not iOS ending the process for memory. The per-second line of that same second reads footprint 4 995 MiB,
  1 660 MiB still available to the process, device 9 % available, 237 pages read from files, 60 frames per second.
  The last memory warning was at 10:18:41. The frame before the break was a normal 5 s window (300 frames, 1.1 s of
  render thread work).
- Why the game broke is not in any journal. Upstream prints the guest stack and registers at Info level; the Core
  journal keeps warnings and errors only, and the stderr capture had used its 2 000-line budget for lines without the
  NSLog banner by 10:06:46 (826 of the lines kept are MoltenVK's statistics, printed every 300 frames; the stack trace's
  continuation lines are in the same budget). The guest's break reason and info bytes are not printed by upstream at all.

## Memory in this session (for the lot after IPA 767)

- Footprint 4 971 MiB at the first warning (39 s in), 5 500 to 5 587 MiB from 10:09 to 10:22 with 1 068 to 1 187 MiB
  available and 37 memory warnings; the device at 7 to 10 % available.
- 10:22:36: the engine's safe-point compaction (adapt_safe_point_compaction, in a 760 ms presentation gap) took the
  footprint from 5 546 to 4 500 MiB: committed managed heap 1 716 to 747 MiB, large object heap 733 MiB (427 free) to
  238 MiB, gen2 903 MiB (432 free) to 468 MiB; pause 1 179 ms. The footprint then grew back to 4 995 MiB in ten minutes.
- Vulkan device memory 434 to 563 MiB; pipeline cache 134 to 138 MiB, referenced in its mapped file.
- The large object heap's free space is what adapt_loh_compaction_request gives back at the collector's next blocking
  collection under pressure, without waiting for a gap (docs/melonx-ipa767-journals-2026-11-17.md, section 3).

## The change for the next IPA

| Change | Why | Implemented | Tested | Compiled | Delivered | Observed on a device |
| --- | --- | --- | --- | --- | --- | --- |
| Core, adapt_guest_break_context (every title, diagnostics): before the game's own break ends the process, one Core journal line (stage guestBreak, status context) with the break reason and kind, the info address and size and up to 256 bytes there (a 4-byte info also read as a result code, module-description), the guest thread, FP, LR, SP and PC, and the guest stack (34 lines, 3600 characters, 250 ms) | This crash has no cause in any journal | Yes | Gate guest-break-context: static order in Break (after the Exiting check, before the error line, the termination and the exception), bounded reads, no other register; production Ryujinx.HLE builds; the class executed on a real KThread, KProcess, debugger and address space, through the real journal | Core build | Next IPA | No |

It does not stop the game from ending: it says why it ended, which is what the next fix needs. If the game breaks
again, the line names the failing result code (for example a file system or memory error) and the game code that
called svcBreak.
