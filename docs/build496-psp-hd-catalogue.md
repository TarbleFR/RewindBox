# Build 496 — consecutive PSP sessions and final HD catalogue

Requested on 20 October 2026: stop expanding the HD catalogue, preserve the
completed work, fix closing one PSP game and opening another, and deliver a
testable IPA. Work remains on `Claude`; no public release is requested.

## Evidence and scope

The supplied screen recording shows Assassin's Creed: Bloodlines starting,
closing through Quit game, and Naruto Shippuden: Ultimate Ninja Impact failing
to launch. The supplied app log also records a successful PSP session followed
by `LIBRETRO_CORE_STOPPED`, repeated `vm_remap failed (3)`,
`MemoryMap_Setup: Failed finding a memory base` and `Memory init failed`.
The log's last PSP session is at 14:38 UTC; the recording filename is 16:36
local time. They establish the same failure pattern, not necessarily one
identical launch. No crash report or external device log is required.

The reservation code left all view holes open while a game ran. A 32 MiB
commercial title only occupies the lower half of the 64 MiB RAM window;
allocations in the unused half can prevent the full reservation from being
restored. The earlier native fixture mapped 64 MiB even for its 32 MiB case,
so it did not exercise that gap. The sparse app log does not expose the
reservation journal of the failed session: this source defect is demonstrated
separately, and physical-device confirmation remains necessary.

`LibretroAddressSpace.m` now retains exact ownership of view pieces. Once
PPSSPP's live views are observed at a stable base, it reserves only unmapped
pieces of the unused views. Closing a game adds its released views to those
already owned; the next boot releases only those owned pieces. Foreign
allocations are never overwritten or freed, including when moving a window.
The arena and existing running-game mappings remain intact. No timeout,
automatic retry, game setting, save, library or emulator core is changed.

## Frozen HD catalogue

Index `2026-10-20.d64e1ff29d79`, from source
`3b56d406534aa174818566dd4fc24f490399383d`, is included byte for byte in both
the hosted and bundled manifests. It has **352 installable families**,
**437 installation profiles**, **161 one-tap families** and **191 families
with a verified original archive for manual import**. Variants count once.

| Console | Installable families |
|---|---:|
| PSP | 90 |
| Nintendo 3DS | 47 |
| Wii | 43 |
| GameCube | 77 |
| PS2 | 76 |
| Nintendo 64 | 14 |
| PlayStation | 2 |
| NES / Mesen | 5 |

Two families shared by GameCube and Wii are counted once in the global 352.
The last pass added 57 families to the previous 295. NES/Mesen from Build 495
is retained; Nestopia remains the default. Sources, credits, exact regional
limits, verified downloads and manual-import requirements remain intact.
The 400-family research target is closed at the maintainer's request.
Switch references remain research-only; no DS texture support is invented.
No complete French/PAL Fire Emblem GC/Wii pack or downloadable Call of Duty:
Roads to Victory pack was validated by that research.

## Validation and delivery

Baseline: successful Build 495, source
`fee67e4d0aeede934bfed722f8dd9b43fb6d2ff5`, run `39384517903`.
Targeted source: `4b12e244d9093564a6d57a30b72900030f0733e5`,
run `39444272536` (`build496-checks.yml`).

- Native regression compiles the same new test against the old reservation
  and the candidate. The old code must fail `PSP_RELAUNCH_UNUSED_RAM_PROTECTED`;
  the candidate must pass, including three 32 MiB cycles, unchanged live bytes,
  the same restored base, and preservation of foreign mappings.
- The changed Objective-C source compiles against the iPhone ARM64 SDK.
- Seven production Simulator sessions alternate PSP ISO (32 MiB), PRX
  (64 MiB), and another libretro core in one process, checking startup, frames,
  full shutdown, return and relaunch. These use the unchanged pinned core
  package, not commercial game images. They are not iPhone gameplay tests.
- The final generated catalogue, publication/region regressions, verification
  parser boundaries and all registered original CI records are checked.
- Unchanged Dart, other native modules, emulator cores and prior validation
  are reused from successful delivery 495 with exact source comparison.
  The delivery gate allows exactly the reservation source and two manifests
  as product changes; packaging/signature checks remain unchanged.

Final run status, IPA identity and delivery hash are recorded after success.
