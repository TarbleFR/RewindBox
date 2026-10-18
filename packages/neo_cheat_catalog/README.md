# Unified cheat catalogue runtime

`NeoUnifiedCheatCatalog` is one shared Foundation service for the Libretro,
ARMSX2, RPCS3 and Dolphin frontends. It stores data only; it never activates a
cheat, writes an engine configuration, or changes a game image.

The Flutter interface is `NeoCheatCatalog` (`neostation/cheat_catalog`, with
progress events on `neostation/cheat_catalog/progress`). Native callers import
`<neo_cheat_catalog/NeoUnifiedCheatCatalog.h>` and use `sharedCatalog`.

## Files and installation

Only the compressed `Resources/manifest.json.gz` index and labels are bundled with the application. Packs are
requested relative to the configured HTTPS `manifestURL`, whose default is the
`Claude/native/cheats/catalogue/manifest.json.gz` file of TarbleFR/neostation-ios.
The default cache is `Documents/NeoStation/Cheats/Unified`.

A bulk operation refreshes the manifest and installs all eligible packs with
at most two transports and two pack-processing workers. A valid local manifest
remains usable when refresh is offline. Each pack is SHA-256/size checked before
bounded gzip expansion; each embedded game is independently SHA-256/size checked
before an atomic write. A malformed game record or failed pack cannot remove a
successful sibling. Repeating the action verifies cached chunks and retries
missing data. Previous verified game metadata remains discoverable if a newer
pack fails. Main-thread notification `NeoUnifiedCheatCatalogDidInstallNotification`
is sent after a bulk completion, including partial successes.

Limits are 12 MiB compressed/64 MiB expanded for an index, 8 MiB compressed/16 MiB expanded per pack and
2 MiB per game chunk. Large games are represented as multiple complete parts;
the metadata fields `identity_group`, `part` and `parts` are retained. No runtime
request eagerly loads all code chunks. The active manifest lists sources actually used by its programs. The separate
research audit records unavailable sources and adaptation attempts.

`installAllWithProgress:completion:` progress reports `total_packs`,
`completed_packs` (processed attempts), `installed_packs`, `failed_packs`
(count), `total_bytes` and `completed_bytes` (successfully installed pack bytes).
The final dictionary replaces `failed_packs` with an array of pack IDs and adds
`errors` and `installed_games`. Partial success returns that dictionary and an
NSError; the Flutter bridge returns the dictionary with an `error` string so
successful work is visible. A failed refresh with an otherwise complete local
installation is described in `refresh_error`.

## Identity contract

An identity contains `system`, optional `title`, `regions`, `languages`,
`revision` and `identities: [{type, value, scheme}]`. Names are search candidates
only. Conflicting known languages, regions or revisions exclude a game even
when a hash matches. Values only compare within the same explicit type/scheme.
Thus an R4 header CRC, a full-ROM CRC and a PS2 executable CRC are different
identities. Do not populate region/language from the user's UI locale or a
filename alone.

Examples of exact anchors:

- `ps2_crc / pcsx2-executable-crc`.
- `md5`, `sha1`, `sha256`, `crc32` with `rom-full`.
- `ds_game_code / nds-header-gamecode` **and**
  `ds_crc / r4-header512-crc32-inverted` together.
- Dolphin `game_id / dolphin-disc-game-id` **and a known matching revision**.
- RPCS3 `ppu_hash / rpcs3-ppu-hash`, `serial / ps3-title-id` **and a known
  matching game version**.

Source-specific cartridge hashes (`nes-prg`, `bsnes-cartridge`,
`mesen-sha1-cheat`) only match the same scheme. A bare serial or game ID without
a known matching revision remains `candidate`, requiring user confirmation.
Games returned by lookups have `installed`; reading codes verifies actual
cached bytes again before returning them. Codes always return `enabled:false`.
Engine adapters must additionally enforce their dialect, opcode, line limits,
mastercodes/dependencies and unresolved parameter rules. Download availability
is not proof of in-game effect.

## Validation

`python3 test/unified_catalog_runtime_test.py` checks generated pack bytes on any
host and compiles/runs the actual Foundation manager on macOS. Its fixtures
exercise exact/candidate/conflicting identity, source-specific CRCs, cache
persistence, corruption recovery, two-request concurrency, duplicate transport
completion, partial failures/retry, malformed sibling isolation and main-thread
callbacks. Apple execution is explicitly skipped on Linux.

`python3 test/unified_catalog_ios_test.py` also compiles/links the actual package
against the iPhone SDK (including UIKit browser and Flutter declaration stubs).
`test/unified_catalog_ios_build.py:compile_catalog` is shared by the standalone
bridge/Simulator probes. These gates execute no commercial games and rebuild no
emulator core. Production builds use Flutter.framework, not the declaration stubs.

The parsed manifest, game records, ID/system lookups, and snapshots are shared
immutable objects. Queries copy only returned rows. The Flutter maintenance
channel sends a compact summary/sources rather than copying the entire index
through its codec. The macOS full-manifest probe opens ten consecutive menus,
checks that the snapshot/index pointers are shared, and reports actual process
footprint before/after; it never loads game chunks or emulator cores.
