# Build 466 — automatic libretro cheats

Candidate on `Claude`, based on delivered 465 (`09c406c2`). Private test IPA
requested by the maintainer on 16 October 2026. No public release is authorized.

## Confirmed defect

463–465 `installSource` persisted source/console indices, but the game menu only
loaded them into `_installed`. No path called `matchGame` then `downloadGame`
and `merge` automatically: these only ran when a user tapped a catalogue row.
Consequently “installed” meant index installed, not codes loaded for the game.
The libretro tree has titles/paths/blob hashes, not ROM hashes. Previously only
ten games in the complementary XML carried content hashes; the rest relied on
manual title search, stripping all region/revision tags for candidates.

## Candidate behaviour

- Prepares identities and source indices after the game launches, off the main
  and emulation queues. The menu automatically loads every matching source.
- Bundled reference index: **22,746** `.cht` entries across 30 console keys,
  with **40,398** projected reference content identities. Aliases share data.
  Initial complementary XML: 10 games, 625 code-bearing entries, available
  offline. CHT bodies are downloaded per matching game and blob-checked/cached.
- MD5, SHA-1, SHA-256, CRC32; iNES/trainer, SNES copier headers and N64 byte order
  get canonical hash aliases. Preferences retain full original-content identity.
  CUE descriptors resolve their first local binary track.
  Unchanged regular files reuse an identity cache (path, console/core, inode,
  size and fractional modification timestamp); changed files are rehashed.
- Hash-derived canonical titles retain region and revision. Code-device tags
  are removed only from exact version comparison. Similar names never prove an
  identity. Conflicting regions/explicit revisions and XML hash mismatches are
  excluded. Uncertain candidates show their version and require confirmation
  for this exact content before enabling. No code is enabled by discovery.
- Exact semantic duplicates retain all source/licence attribution; uncertain
  versions have separate scopes. Individual switches, disable-all, retry,
  explicit restore and per-content preferences. Existing valid indices remain
  usable; corrupt indices fall back to the verified bundled index. Removal
  persists an opt-out rather than silently re-enabling a bundled source.
- Adapter profiles remain central. NES, SNES, GB/GBC, GBA and Genesis profiles
  are preserved; bounded DeSmuME Action Replay and simple Beetle PSX GameShark
  30/80 writes are added. Ordered programs stay intact; oversized/unsupported
  programs and RetroArch handler-1 memory operations remain unavailable.
- Logs distinguish identity resolution, index loading/recovery, match counts,
  resource parsing errors and validated programs dispatched to the host.
  `retro_cheat_reset` then `retro_cheat_set` execute on the emulation queue.
- All added labels are translated into the twelve supported languages. The
  menu explains no results, unsupported cores and effects needing a restart.

## Sources, redistribution and regeneration

- `libretro/libretro-database@12c21cf79f1e20eff6ac68b80875816c717d0a7a`,
  CC BY-SA 4.0. Adapted JSON data remains separately under CC BY-SA 4.0;
  original licence, credits, transformation notice and upstream link bundled.
- `skyzyx/openemu-cheat-database@5f1af6161ee30fddccc3942dfbcc20b253bcb152`,
  Unlicense. Original XML and licence bundled unchanged.
- `tools/cheats/build_bootstrap.py`: reviewed Git blob inputs and deterministic
  output manifest. Bundled resources: approximately 12 MB uncompressed,
  3.3 MB ZIP-compressed. No games, BIOS, firmware or keys included.
- Existing updater checks upstream commits, licence identity and data hashes;
  failed updates keep working indices and content-keyed preferences.

## Validation and limits

A dedicated second Simulator process keeps the installed app and its data, loads
the first process receipt and saved selection, asserts discovery with activation
off, then explicitly restores the selection and checks actual core RAM.

Local offline tests: manifest integrity, all index rows and identity hashes,
original XML/licence equality, twelve-language presence; Python compilation and
`git diff --check`. Native/macOS and Simulator results will be recorded after
actual execution. No physical iPhone test has been performed in this session.

The central catalogue can be consulted for any console/core. Native code
activation is offered only for reviewed adapters, not inferred from the two
mandatory ABI symbols (many cores implement stubs). Handler-1 memory operations,
unknown core formats, conditional PSX opcodes and over-budget programs remain
explicitly unavailable. Recognition of renamed compressed discs/CHD or playlist
wrappers is not established by raw-file hashes. Games absent from reviewed
metadata remain uncertain. Automatic loads are bounded to 64 files/4096 rows;
additional results remain in the searchable catalogue. Physical gameplay and
compatibility of a commercial game's codes still need the maintainer's test.

Skins, touch rendering/pressure/loading, other engines, the 34-core package and
baseline library sources are preserved. A shared Session change only starts
cheat discovery and reports enabled cheat counts/application diagnostics.

## Retained development results

- First candidate `74a28e27339d6d3c3d7bf4048fb9170c7f70621d`, focused run
  `38828551158`: native parsers/catalogues/automatic-index tests and resource
  integrity checks passed. Simulator compilation then failed on a duplicate
  local variable name in the new menu initializer; corrected before any IPA.
  This run is not a successful end-to-end validation.

- `534f2b6b`, focused run `38828865544`: 38 parser, 23 catalogue/offline,
  49 automatic-index and 15 live-source checks passed. UIKit passed original
  Ignited (128 checks), NES cheats/menu (31), four complete previews (10) and
  SNES memory effects (4); DS failed its activation-memory assertion (1/4).
  The synthetic DS image only looped; the source core processes AR only when
  ARM7 DISPSTAT requests VBlank IRQs. The corrected original ARM7 program
  enables DISPSTAT bit 3, retaining the same memory-effect assertion and the
  same pinned core. This is a fixture correction, not an emulator fix.
