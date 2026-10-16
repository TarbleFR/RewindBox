# Build 466 — automatic libretro cheats

Private test Build 466 on `Claude`, following delivered 465 (`09c406c2`).
Requested by the maintainer on 16 October 2026. No public release is authorized.

## Confirmed defect

463–465 `installSource` persisted source/console indices, but the game menu only
loaded them into `_installed`. No path called `matchGame` then `downloadGame`
and `merge` automatically: these only ran when a user tapped a catalogue row.
Consequently “installed” meant index installed, not codes loaded for the game.
The libretro tree has titles/paths/blob hashes, not ROM hashes. Previously only
ten games in the complementary XML carried content hashes; the rest relied on
manual title search, stripping all region/revision tags for candidates.

## Implemented behaviour

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
`git diff --check`. Successful native/macOS, Simulator and actual IPA results
are recorded below. No physical iPhone test was performed in this session.

The central catalogue can be consulted for any console/core. Native code
activation is offered only for reviewed adapters, not inferred from the two
mandatory ABI symbols (many cores implement stubs). Handler-1 memory operations,
unknown core formats, conditional PSX opcodes and over-budget programs remain
explicitly unavailable. Recognition of renamed compressed ROM archives, CHD/disc containers or
playlist wrappers is not established by raw-file hashes. Games absent from reviewed
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

The final review also found that resolving a CUE to its real track changes the
old preference key. Descriptor-keyed 463–465 choices are recovered without
deleting the old file. They remain disabled/unverified unless the complete code
program matches a current exact-content source. Matching choices retain their
selection and attribution; the end-to-end CUE fixture and second process cover
this upgrade path. This product change requires fresh shared native/UI gates.

The optional broad emulator probe `38830357263` / job `116747907319`
retained its one known `ppsspp-crowded` reserved-address observation failure:
PSP content actually launched and closed, but chose another usable base. This
is the already classified Simulator probe limitation, not a demonstrated
launch regression (see AGENTS.md). No assertion or runtime was changed for it.
Its remaining historical/unrelated probes were cancelled to free runners for
the mandatory current cheat/skin suites; that broad workflow is not a pass.

A final UI lifecycle check also covers returning from a catalogue before its
async game-file transfer finishes. The root cheat table now refreshes even if
the last nested controller has gone; the test inspects the actual table row
count with that stale child reference cleared. No shared menu/skin controller
source or touch input is changed.

## Mandatory acceptance coverage

| Requested case | Executed proof |
| --- | --- |
| New catalogue installation and real indexing | Native install/validation/offline round-trip; live official-source probe |
| Launched and renamed game detection | Content hashes and bundled RDB identity tests; UIKit CUE/renamed-content fixture |
| Automatic visible rows | Actual root table after async discovery, including return from a nested page |
| Several sources and exact duplicates | Cached `.cht` plus inline XML-style records, complementary codes, retained attribution |
| Real activation and disabling | Pinned Nestopia, Snes9x and DeSmuME core memory observations, after observed frames |
| Persistent per-game choices | Object reload, then a second actual Simulator process without reinstall/data reset |
| Regional/revision safety | USA/Europe and explicit revision conflicts, mismatching hashes, uncertain legacy choices |
| Unsupported formats/cores | Bounded native adapters, handler-1 and unreviewed core rejection; visible disabled UIKit row |
| Already downloaded installations | Valid legacy indices, corrupt/incomplete index recovery from bundled data; descriptor-keyed preference migration |
| Diagnostics and packaging | Stage diagnostics, complete bundled byte manifest and verification inside the actual final IPA |

These fixtures use original synthetic content. They demonstrate the catalogue,
UI, persistence and native dispatch chain; they do not establish commercial
code correctness for every game or physical iPhone behaviour.

## Validation of the delivered sources

Runtime/test/data source: `cc594d40a751be462dad0e3ef437c4ade5e2fc80`.
Delivery-only pins and report: `ff70cc9df1fe30a28cf1fc53e7dfdc2c56738624`;
the closed native/UI inputs are byte-identical (2,630 inputs plus each suite's
workflow). No independent fixture exclusion is used.

- Engine `38832178562`: native job `116753195961` passed all 19 frontend
  executables, 1,133 pressure-pixel and 6,025 tracker assertions, shaders,
  compiled/linked 74 iPhone objects and real Flutter codec current/historical
  negative tests. Dart job `116753195780` passed analysis and launch/library
  suites. Skin job `116753196120` passed **27 sessions / 2,840 checks**.
- Installed skins `38832181302` / `116753203949`: exact 463 negative followed
  by **53** upgrade/menu/orientation/fallback and **10** new-session checks.
- Catalogue `38832183687` / `116753221277`: **109** Flutter tests and **39**
  original PocketArch associations / **78** native resource/render checks.
- Cheat `38832175806`, attempt 1 / `116755206620`: 38 parser, 23 catalogue,
  49 automatic-index and 15 live-source checks passed. Both Simulator launches
  produced no application progress or result before their deadlines. Launch
  output eventually contained PIDs but no app traces; no functional assertion
  was reached. Retained artifact `12018716506`, SHA-256
  `13d5636b8d99095b51a497e00ef081beb8352cc52d30832d36463e359a047300`.
  This is a failed run, not validation. The same source and assertions are
  retried; the cause of the silent Simulator startup is not conclusively known.

The earlier `ed78ab11` complete cheat run `38830357209` passed NES (33), DS (4),
SNES (4), Ignited (128), previews (10), then a second actual process (4).
It establishes the corrected original DS fixture and migration behaviour, but
is not substituted for the final root-table navigation check.

Cheat attempt 2 / job `116761076526` **succeeded**, same exact source and
assertions. Native/live checks: 38 / 23 / 49 / 15; packaged-bootstrap unit checks
also passed. UIKit/core checks: Ignited 128, NES 34 (including the actual root
table after stale-child navigation), complete previews 10, DeSmuME 4, Snes9x 4,
then a second process with retained app/data 4. Actual RAM activation and disable
were observed in all three cores; automatic aggregation, CUE migration and
process-restart explicit restore passed. Verdict `problems: []`, physical-device
validation false. Retained artifact `12018614232` (3,056,654 bytes), ZIP SHA-256
`ba98e92253abb730de8663e033216f51b798eb11ca634ce76227280feeb5d5d1`.
The archived JSON was independently downloaded and inspected. Attempt 1 is
retained separately above and is not counted as a pass.

Private full delivery `38835740295` dispatched from
`ff70cc9df1fe30a28cf1fc53e7dfdc2c56738624`, build 466, benchmark disabled,
recipient `build-utils/delivery-424-recipient.pem`. The Release build and
independent verification succeeded; exact binary identity is recorded below.

## Delivered private IPA — 0.0.7 (466)

- Source **`ff70cc9df1fe30a28cf1fc53e7dfdc2c56738624`**, full delivery
  [38835740295](https://github.com/TarbleFR/neostation-ios/actions/runs/38835740295):
  checks, native and cold iPhone Release succeeded. The optional warm benchmark
  was intentionally disabled. No deployment or public release was created.
- Final sealed IPA: **218,599,277 bytes**, SHA-256
  **`1eabef6e3ac7b6b0d47ec591cc18a335d583acf39eeff1f7ead3744b51167d3e`**.
  Filename: `NeoStation-Build466-ff70cc9d.ipa`. The app and all five extensions
  contain version 0.0.7 / build 466. This is 3,337,079 bytes more than sealed 465.
- Encrypted CI artifact **12019654684**, 220,185,501 bytes, ZIP SHA-256
  `b89d5c1cb7311fcb3ee5bec21bf21ad4c42d5a861136b6a2d553b0b694f8927d`, retained until 2026-10-30T01:56:20Z.
- Independent verification of the downloaded/decrypted final ZIP: ZIP CRCs,
  both sealed integrity records, exact source stamps, all **76** compiled
  code/data/ABI fingerprints, complete image membership and **34** core images.
  The actual bridge contains all six new runtime markers, including identity
  resolution, `_rootPage`, disable-all, CUE recovery and bundle discovery.
- Actual `NeoStationCheats.bundle`: **34** verified
  resources / **12,260,537 bytes**, including the exact reviewed
  indices, original XML and licences. Both source revisions match the pins above.
- Windows Downloads receipt verified independently after transfer:
  `C:\Users\Coren\Downloads\NeoStation-Build466-ff70cc9d.ipa`, same bytes
  and SHA-256. Previous deliveries remain separate.

SideStore Apple re-signing is required. No physical iPhone gameplay, upgrade,
controller, latency or commercial-code compatibility observation is claimed.
Activation remains limited to reviewed formats/adapters; unsupported memory
operations, unknown cores and uncertain containers retain the explicit limits
above. **Do not reuse build number 466.**

## Physical iPhone acceptance still pending

Upgrade without deleting the app/data and verify the existing DualShocked
selection in both orientations. Launch an owned, reference-identifiable game:
rows should populate without installing sources or choosing a catalogue entry,
with every switch initially off. Check one appropriate code in gameplay,
several simultaneous choices, disable-all, then close/relaunch and explicitly
restore. Repeat offline after the game resources have been cached. Turning a
code off stops its writes; a code's previous irreversible game-state changes
may require a reset or a clean save, as explained in the in-game effects help.
No such physical-device observation is claimed by these automated results.
