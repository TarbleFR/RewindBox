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
unchanged from the already pinned package. The other catalogue session completed its verified final publication while this
fix was being built: `730e065ffb5d1b66735f6e440cbdbedc886c8163`, revision
`2026-10-20.8a38a79c72f0` (355 installable families, 164 one-tap / 191 manual).
This latest catalogue is retained, with the three new original archive checks
from runs `39449348701` and `39450675080`, confirmed successful. Local catalogue
generation/check and publication identity checks also pass. No further research
or unverified candidate is promoted for this delivery.
No public release is requested.

Validation must reproduce the observed self-collision against 496, then check
continuous ownership through 18 cycles, concurrent allocation pressure,
32/64/76 MiB RAM, partial startup failure and foreign mapping protection.
The real rebuilt core must pass seven production Simulator sessions, with the
alternative PSP bases deliberately occupied. This still does not establish
commercial-game or physical-iPhone GLES gameplay. Final run and IPA identities
are recorded only after the jobs succeed.

## Build and validation provenance

The native collision, 18-cycle ownership, partial failure, foreign-allocation
and iPhone SDK checks passed at `4d0a5b9ac250a44bbb4f935d99d1a47f066043e1`,
run `39452491166`, job `118730959458`. That job subsequently failed in the core
build; it is not classified as a successful run. Later runs reuse only its
successful native step after checking all native test inputs and the Xcode/SDK
identity. The completed rebuilt core and production session proof are still
required before delivery.

The upstream make recipe needs explicit Darwin/iOS configuration with Xcode
26.3: its generic `arm64` branch precedes iOS, its command-line link flags leak
into FFmpeg configure probes, and the mobile/Lua configuration is omitted.
The recipe now chooses `platform=ios` with the arm64 iPhone target, isolates
FFmpeg configure flags, uses upstream `MOBILE_DEVICE`/`LUA_USE_IOS`, and selects
CPU features' available `dlfcn` path rather than Linux's strong `getauxval`.
The memory patch and upstream revision remain pinned; these are build settings,
not modifications of the app's emulation preferences or saves.

## Successful targeted build

Source `ab9361c29f7c9ab769c4263dd8b7427fc4f4c036`, run `39455712245`, job
`118741920809`: successful. The rebuilt PPSSPP is 18,024,544 bytes, SHA-256
`a7d058581b657714e055dc9713e9a1252ad4acf6315b30610fcb2b1c81130b6f`.
The package validates all file hashes and preserves the 34 other cores and
system assets; the managed-memory ABI and KTX2 decoder exports are present.
The Makefile also restricts Adreno driver objects to Android, where they belong.

All seven production sessions completed and stopped, including six PSP sessions
alternating 32/64 MiB and one intervening other-core session. The complete probe
finished in 336 seconds on iPhone SE (3rd generation), iOS 26.2 Simulator.
Required logs confirm the managed ABI, use of the reserved memory base and
continuous reservation after shutdown. Rendering remains the Simulator's
software path; physical iPhone GLES and commercial-game gameplay are unconfirmed.

The delivery is pinned to this tested product plus the exact final 355-family
catalogue. Subsequent installer work on Claude is retained separately in the
branch history and is outside this IPA's frozen source tree. The workflow dispatched on Claude explicitly checks out the immutable delivery
commit `e999a5fdc98a42f5d1995ca85fdfa04479d7f77a`. Every shell step verifies that
checkout and records both workflow and source commits before passing the source
SHA to the existing build scripts. No tag or GitHub release is created.


## Verified delivery

IPA **0.0.8 (497)** was built from frozen source
`e999a5fdc98a42f5d1995ca85fdfa04479d7f77a` by workflow commit
`9319dc98176dcfd89dca3489569b1dbf23fd3ba4`, run `39458674086`.
Checks, native evidence and the cold Release job passed; the optional warm
benchmark was skipped. The cold job took 12 minutes 28 seconds.
The temporary immutable-checkout driver is restored to the ordinary workflow
after this delivery so later candidates cannot accidentally compile source 497.
The full receipt is `docs/evidence/psprelaunch497-delivery.json`.

`NeoStation-Build497-PSP-HD.ipa`: **168,217,798 bytes**, SHA-256
`3481881ea6f880595f736b7bebfed240def38887bae69f5972e9a420c81f58eb`.
This equals the exported checksum, signed-payload record and final structure
report. Independent inspection verifies every one of the 75 Mach-O payload
fingerprints, all six bundle versions, the exact 355-family catalogue, the
managed-memory bridge/core exports and the new PSP payload against its tested
core artifact. The other 34 libretro core payloads are identical to Build 496.
The CI verifies every ad hoc signature against the final exported IPA bytes;
installation uses the maintainer's usual SideStore Apple re-signing.

This is a source-level correction with successful native and Simulator
regressions, not physical-device gameplay confirmation. No tag or public release
was created. Do not reuse build number 497.

The identical IPA is also copied to the maintainer PC at
`C:\Users\Coren\Downloads\NeoStation-Build497-PSP-HD.ipa`; its final checksum
and size were verified there. The ephemeral delivery private key and transfer
password were removed after successful handover.
