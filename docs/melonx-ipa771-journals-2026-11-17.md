# MeloNX after IPA 771: Hogwarts Legacy, castle grounds — 17 November 2026

Private journals of the maintainer's test of IPA 771 (Core 1df78c52, MoltenVK eight-part patch; launch fingerprint
69132b93, IPA 767's was 50cd62f2). One Hogwarts Legacy session, pid 35052, 12:41:49 to about 12:43:50 UTC. Counts and
times only; no raw journal in Git. Maintainer's report: sent back to the home screen again in the castle grounds; frame
rate very unstable, above all in open spaces.

## 1. How the session ended

- No fatal signal and no crash line for pid 35052 (the crash journal's last entry for it is its session note): the
  process was ended from outside, as in IPA 764 and 767.
- Device available memory: 30 % at the session's start (before the game), 10 % at 12:42:31, 5 % at 12:42:39, 4 % from
  12:43:32. Footprint 1 468 MiB before the game, 3 398 MiB at t = 45 s, **4 409 MiB at t = 46 s** (+1 011 MiB in one
  second, 2 229 MiB newly compressed and 35 817 pages decompressed in that second; IPA 767 had the same jump at t = 46 s),
  4 911 MiB at 12:43:32 with 2 068 MiB still available to the process. iOS ended it with room left in its own limit:
  the device ran out.
- At t = 30 s (breakdown line): 2 096 MiB of the 3 610 MiB footprint were compressed; the guest memory lease (16 shared
  regions of 256 MiB) held 968 MiB resident, the 163 107 small shared regions 3 134 MiB of address space (residency not
  walked), private memory 1 025 + 466 MiB compressed, graphics 542 + 110 MiB, malloc in use 532 of 624 MiB held.
- What the engine reports at 12:43:02 (footprint 4 391 MiB): managed heap 761 MiB committed (LOH 428 MiB of which 145
  free, gen2 285 MiB), Vulkan device memory 705 MiB (images 493, buffers 211), texture cache 156 MiB, buffer cache 126
  MiB, mirror copies 48 MiB. From 12:42:31 to 12:43:02 these grew by about 500 MiB; the footprint by 1 013 MiB.

## 2. Why the frame rate varies

- When the device is not thrashing, the game holds 30 frames per second (paced 2 x 16.7 ms): t = 24-30 s and 39-45 s.
- The drops line up with memory compression: t = 31-38 s (a 1 317 ms gap, then the engine's presentationGap compaction,
  158 ms pause, 355 MiB given back), t = 46-47 s (the +1 GiB second, 1 258 ms gap), and from t = 49 s on, per-second
  lines arrive 7 to 16 s apart (the sampler itself is starved), with 47 000 to 228 000 pages decompressed per interval.
- Engine calls of the stall watch took 1.6 s, 2.5 s and 5.1 s to return; 24 managed collections paused 40 to 135 ms
  (gen0 135 ms for 0.3 MiB promoted at 12:42:28: the collector marking memory iOS had compressed).
- So memory is the cause of both the kill and most of the instability.

## 3. Problems found and their fix

| Problem (these journals) | Fix | Status |
| --- | --- | --- |
| The native heap report (120 s window) never closed before the kill, and no footprint breakdown was written at the memory warning: the part of the 1 GiB jump that is not managed or Vulkan (about 500 MiB) has no owner in the journals | The breakdown and the heap window observe the memory warning themselves (8ee65d65), so f365bf01 no longer depends on the deferred RSwitch renaming of the session screen | Implemented; journal test 64 checks; Swift on macOS (melonx-host); for the next IPA |
| The footprint before the game is already 1 468 MiB (unexplained since IPA 764) | The breakdown's start line (f365bf01, now deliverable) writes its regions and malloc zones at the journal's start | Same |
| The large object heap keeps 145-183 MiB free in play; adapt_loh_compaction_request needs 256 MiB, and the collector ran no blocking collection after 12:42:29, so a request would not have been consumed | Not changed: lowering the threshold gives nothing without a blocking collection, and forcing a compaction in play is excluded | Recorded; the start and warning lines will say whether this free space matters next to the unexplained part |
| The engine's presentationGap compaction ran once in play (12:42:28, 355 MiB back); the 1 258 ms gap at t = 47 s found only 51 MiB free (under its 128 MiB) | Rule unchanged (it worked when there was space) | Recorded |
| ServiceBsd WriteBsdResult EBADF repeated 512 times or more (the game's network calls on a closed socket) | Logging only (counted, exponential back-off); no memory or frame cost measured | Recorded, not changed |
| The device starts the session at 30 % available (other apps, system caches) | Advice to the maintainer: restart the iPhone and close other apps before a Hogwarts session; it moves the device's starting point, not the engine | Advice |

No iPhone gain is claimed. The next test with these lines should name what fills the +1 GiB second and the 1.47 GiB
before the game; the memory fix follows from them.
