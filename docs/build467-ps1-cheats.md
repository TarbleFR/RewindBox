# Build 467 candidate — direct PS1 cheat discovery

Follow-up to the maintainer's Build 466 report: FFVII/PS1 shows no codes or
useful source results. Work stays on `Claude`, preserving 464/465 skins and
all existing cores/engines. Private IPA and source pushes remain authorized.

## Confirmed gaps

- The session passes only the content path to the cheat menu, losing its
  existing `gameTitle`. Renamed CHD/container filenames therefore yield no
  candidates despite available library metadata.
- Raw-file hashes cannot identify compressed discs. BIN/CUE/ISO recognition
  did not inspect the PS1 boot serial, although the reviewed RDB has serials.
- The action labelled “Search cheats” filters already loaded codes, rather
  than searching source games. Catalogue selection gives no useful path for
  an unidentified game, and the root does not name available sources.
- Only Beetle PSX HW was accepted, although the software variant shares its
  reviewed libretro/GameShark handler.
- Reference coverage is limited: the pinned libretro tree has one FFVII
  cheat file, USA. French/Japanese/European metadata is not a substitute for
  regional code coverage. OpenEmu's reviewed ten-game XML has no PS1 codes.

## Changes

Pass library title as an explicitly unverified search hint, behind content
hash/serial identification. Add bounded ISO9660 SYSTEM.CNF boot-serial reading
for ISO and raw Mode 1/2 BIN/CUE data tracks, including a 150-sector pregap.
The reference projection now retains 4,266 PS1 serial identities from the same
reviewed, licence-compatible RDB. Serial matches remain candidates because
multiple revisions can share a serial. Identity cache schema changes; saved
content/core preference keys do not.

The first action finds cheats across every available source and names those
sources. Existing compatible results remain directly toggleable. An empty
match opens the title/version search across sources, prefilled from the game
label, without requiring catalogue choice. Filtering loaded codes has an
explicitly different label. Missing source/empty search has a translated
explanation in all twelve languages. Manual source picks remain uncertain
through activation confirmation, rather than silently becoming verified.

Both Beetle variants accept bounded 30/80 GameShark writes. The actual FFVII
reference has 19 entries: 17 supported, two repeat programs explicitly
unavailable. No core or memory-engine implementation is changed.

## Validation and limits

Tests use the unchanged official FFVII CHT, original synthetic ISO9660 metadata
and the production catalogue/menu. They cover renamed disc serials, pregaps,
misleading names/metadata, French-vs-USA exclusion, title hints for containers,
actual FFVII parsing/adaptation and UIKit activation/disable dispatch. Existing
NES/SNES/DS actual-core RAM and process-restart regression checks are retained.

CI results and delivery identity are pending. No FFVII commercial-ROM gameplay,
physical iPhone or PS1 core RAM effect is claimed. CHD/PBP decompression is not
implemented: these use library hints/manual version selection. A missing
regional catalogue cannot be filled by applying USA addresses to a different
version. No BIOS or game image is fetched or bundled.
