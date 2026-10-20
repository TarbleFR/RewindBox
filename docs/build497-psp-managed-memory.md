# Build 497 — PSP memory ownership at the core boundary

The maintainer confirms that Build 496 still fails when closing a PSP game
and opening another. The newly supplied app log adds a successful GLES session
of Assassin's Creed: Bloodlines, a completed close at 15:30:09 UTC on
20 October 2026, and four failed attempts within the same process.

The first failed attempt includes `vm_remap failed (3)` from backing address
`0x17c204000` (offset `0x204000`) into RAM destination `0x17c000000` for
`0x1f00000` bytes. The backing arena begins at `0x17c000000`: it occupies
the RAM view the core subsequently tries to map. This establishes an arena/view
self-collision. The app log still lacks the beginning of the rolling native
log, so the precise allocator history before that placement is not known.

Build 496 protected unused view tails after boot but still released the views
and an arena slot before the core allocated memory. Its simulator sessions
had many alternative free bases. That was insufficient evidence for the crowded
iPhone process; the supplied device result supersedes the hypothesis that 496
resolved this user-visible problem.

Build 497 introduces a versioned C callback table between the existing host
and PPSSPP's Darwin allocator, rebuilt from the same upstream revision
`1bd28b0d634d4ec31acb7092563f3e1e247d1e9c`:

- The complete no-access view reservation remains held while the core allocates
  its backing arena. The arena cannot overlap those addresses, regardless of
  allocator placement or graphics allocations.
- The core uses the explicitly reserved base. Each view atomically replaces
  only a range fully owned by the host. The source must lie within this session's
  backing arena. Foreign targets, foreign sources and already live views are
  refused, never overwritten.
- Unmapping a view restores its no-access reservation atomically. Masked mirror
  aliases can be released repeatedly without releasing the reservation.
- Closing or aborting a setup reclaims every mapped view and releases the
  backing arena. Larger RAM configurations can grow the reservation before boot.
- The old allocator remains available when this core is used without the host
  callback table. NeoStation still supports an unmodified core via its legacy
  path; the new delivery requires the managed-memory export.

Only PPSSPP is rebuilt. The other 34 libretro cores and system assets are copied
unchanged from the already pinned package. The catalogue stays at
`2026-10-20.d64e1ff29d79` (352 installable families); ongoing research-only
source records from another session do not become bundled catalogue changes.
No public release is requested.

Validation must reproduce the observed self-collision against 496, then check
continuous ownership through 18 cycles, concurrent allocation pressure,
32/64/76 MiB RAM, partial startup failure and foreign mapping protection.
The real rebuilt core must pass seven production Simulator sessions, with the
alternative PSP bases deliberately occupied. This still does not establish
commercial-game or physical-iPhone GLES gameplay. Final run and IPA identities
are recorded only after the jobs succeed.
