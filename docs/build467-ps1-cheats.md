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
The reference projection now retains 3,978 PS1 serial identities from the same
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

## Local checks

Five bootstrap/IPA-resource tests, all 23 delivery-pipeline guards, the frontend
UI and routing contracts, Python compilation and `git diff --check` passed.
The final source closure contains 2,632 identical inputs per UIKit suite
(including its workflow); these are identity checks, not physical-device tests.

Initial source `3903f033d6a505ed25828bb51ccc73e46297c9c4` has passed its
Dart job `116911897914` (578 + 245 + 4 tests) and catalogue job
`116911926449` (39 PocketArch associations / 78 native checks). Its remaining
jobs are pending at the time of this entry. These results are not substituted
for the query/status regression source `e82dd916c42c404875258156a505eea9c1299410`.

## Retained initial failure and performance correction

Cheat run `38882361802` / `116911884682` failed. Its 38 parser, 23 catalogue,
72 automatic-index and 23 real-source checks passed. The Simulator passed
Ignited 128, previews 10 and real NES/SNES/DS base RAM effects, but menu
initialization and automatic/PS1 resolution exceeded their unchanged deadlines;
second-process startup also produced no result. Artifact `12038289164`,
SHA-256 `acd57a891950036cd3b649d28a33352790eb12589a7673bf114d8cacbac09109`,
was retained and inspected. Logs show delayed identity/index completions around
09:50:15–23, after Nestopia stopped at 09:50:09, including the actual FFVII
resource parsed with 19 entries. This is a failed run, not UI validation.

The two cheat queues ran at Utility QoS below the user-interactive emulation
thread. They now use UserInitiated QoS off-main, and repeated SHA/title pattern
construction is removed. Candidate matching no longer computes exact version
keys when the content has no canonical hash title. Assertions and deadlines
remain unchanged; a fresh complete run is required.

Additional-source review: DuckStation chtdb has French FFVII data, but its
LICENSE reserves cheat/patch copyright to original authors and licenses only
processing scripts under MIT. It is not integrated or redistributed as a
blanket MIT-licensed cheat collection.

The `e82dd916` runs (38882905507, 38882909335, 38882913738) were cancelled
as superseded by the priority fix. The initial engine run retained successful
native/Dart jobs; its still-running skin job is superseded by the complete
priority-corrected revision. Neither cancelled suite is recorded as a pass.
Initial loading job `116911908389` also failed with no candidate/relaunch
result before its deadline; artifact `12038821044` is retained separately
(SHA-256 `801ebe867457c83835504cd160af55218af4d157037292896f9f39a4b3621872`).
The absence of a candidate result does not establish a product skin regression.

## Phone layout

The results follow only two primary actions: Find cheats and Disable all.
Import, manual editing, filters and saved-choice tools remain available after
the results. A UIKit regression checks the actual FFVII section arrangement;
code rows keep their existing section identity and native switch handling.

## Downloaded-but-empty legacy index

A further reproducible installed-data gap: `validatedCatalog` accepts an empty
`games` array. `loadSource` then preferred that downloaded index over the
nonempty bundled reference, leaving a source marked installed with zero games.
Loading now recovers a verified nonempty reference in that case, preserving
the existing files and preferences. Sources genuinely lacking a console remain
empty. A regression writes exactly this valid legacy index and requires
offline recovery, alongside the existing malformed-index recovery case.

## Exact regeneration

The complete bootstrap generator was rerun offline against every cached,
Git-blob-verified upstream RDB, cheat tree and original licence/XML resource.
It reproduces all thirty indices; PS1 retains **3,978** serial-bearing identity
rows. The initial partial data update had collapsed multiple metadata rows with
the same name/hash, losing some release serials and filling absent fields.
The final data is the generator's per-row projection, preserving distinct
release aliases and missing serials instead of inventing identity metadata.
All other console outputs remain byte-identical. Five bootstrap/IPA-resource
tests pass, including the serial shape and exact reviewed row count.
