# RetroAchievements game identification: more games recognized (1 November 2026)

Maintainer request: "peut-on améliorer le hashage des jeux pour trouver plus de
succès ?", then "apporte tous les correctifs et plus si tu trouves d'autres
solutions supplémentaires". Target: **IPA 612** (source only for 611, which
was frozen at `6f4244a0`).

RetroAchievements identifies a game by a hash of the file, computed with a
console-specific rule, and only recognizes the dumps listed for each game.
Nothing in the app can make an unlisted file count. What the app can do is
compute the right hash for every format and stop missing games RetroAchievements
does know.

## What was wrong

| Where | Problem | Effect |
| --- | --- | --- |
| In game, retro emulators (libretro) | rcheevos' default disc reader reads `.cue/.bin`, `.gdi` and raw `.iso` only; `.chd` and `.cso` were hashed as raw images | PS1, Saturn, Mega-CD, PC Engine CD, Dreamcast, Neo Geo CD games in `.chd`, PSP games in `.cso` or `.chd`: never recognized |
| Library (achievements in the game details) | Dart re-implementation of the hashes: discs (PS1, PS2, PSP, Saturn, Mega-CD, PC Engine CD, Dreamcast, Neo Geo CD, 3DO, GameCube, Wii…) were hashed as a whole-file MD5; files over 512 MB were skipped | Disc games never matched by hash; only an approximate title match remained |
| Library | PC Engine copier headers not removed | Headered HuCards not matched |
| Library | Only the hash list bundled with the app (17,819 hashes, 11,618 games, newest entry 4 July 2026, no PS3) | Games and dumps added since never matched |
| Library | A title match looked like a recognized game | The tab showed achievements for a file that may not track in game |

## What changed

1. **`.chd` and `.cso` readers for rcheevos** (`Classes/RBDiscHashReader.c`,
   NEOSTATION_RA_DISC_READER_V1), with a pinned libchdr
   (`ThirdParty/libchdr`, commit `47d79415`, BSD-3-Clause; LZMA SDK public
   domain; zstd BSD; dr_flac public domain/MIT-0, see its
   `NEOSTATION_NOTICE.md`):
   - CD CHD (all chdman codecs: cdlz, cdzl, cdfl, cdzs), with chdman's track
     layout (4-frame padding, stored and implicit pregaps, postgaps), raw or
     cooked MODE1/MODE2 sectors, byte-swapped audio, and the GD-ROM
     high-density area at sector 45000 (Dreamcast);
   - DVD CHD (PS2, PSP);
   - CSO v0/v1 (zlib); v2 (LZ4) is refused, a truncated file is refused;
   - every other format keeps rcheevos' default reader unchanged.
   The in-game libretro client installs it with `rc_client_set_hash_callbacks`.
2. **The library hashes with the same code** (iOS): the libretro bridge
   answers `retroAchievementsHash {path, consoleId}` on a serial background
   queue with rcheevos + the reader above. Discs of any size are hashed (only
   the needed sectors are read). Hashes left by the older Dart code are
   recomputed once (`ra_rom_identity.algorithm` = 2). Elsewhere (desktop), the
   Dart code stays, with the PC Engine header rule and the `famicom`/`fds`
   folders fixed.
3. **RetroAchievements is asked about hashes the bundled list does not know**:
   the same public request as rcheevos (`dorequest.php`, `r=gameid&m=<hash>`),
   with only the hash (no username, token or key). Answers are cached
   (`ra_hash_lookup`): known games 30 days, unknown hashes 3 days; offline or
   server errors are not cached. Used by the game details, the achievements
   dialog and the secondary display.
4. **The library learns from launches**: libretro and RPCS3 now publish the
   loaded RetroAchievements game id (ARMSX2 already did); when the game a file
   launched is recognized, the library remembers it for that file
   (`ra_rom_identity.source = launch`) and shows its achievements whatever
   its format. Dolphin reports no RetroAchievements id and is not covered.
   The file path stays on the Dart side; it is never sent to the engines.
5. **The achievements tab says how the game was identified**
   (NEOSTATION_RA_IDENTIFICATION_V1):
   - recognized by the file (launch, bundled list, online): nothing more;
   - found by title or recent history only: "Found from the title: this
     exact file may not be recognized in game" and a link to the game page;
   - not recognized: "RetroAchievements does not recognize this file", the
     file's RetroAchievements hash (selectable, with a copy button) to compare
     with the files the game accepts on retroachievements.org.
   Seven new strings in the 12 locales.

Order of identification: learned at launch → bundled hash list → online
(cached) → title / recent history (systems without a specific hash rule).

## Validation

- `test/ra_disc_hash_reader_test.py` (11 tests): builds rcheevos, libchdr and
  the reader with AddressSanitizer/UBSan; synthetic discs converted with
  chdman (MAME 0.264) and a CSO writer; each `.chd`/`.cso` gives exactly the
  hash rcheevos computes for the original `.cue/.bin`, `.gdi` or `.iso`, and
  the default reader alone fails on it: PlayStation (+ `.m3u` of a `.chd`),
  Saturn, Mega-CD, PC Engine CD (stored and implicit pregap), Dreamcast
  GD-ROM, PlayStation 2 (DVD CHD), PSP (CSO v0/v1 with alignment 0/2/4, DVD
  CHD); damaged, foreign, truncated and CSO v2 files fail cleanly; wiring
  contracts (podspec, syntax check, channel, published game id, launch paths).
- `test/retro_achievements_identification_test.dart` (15 tests): native hash
  path and one-time recomputation, PC Engine rule, online lookup (request
  content, cache durations, errors not cached, only MD5 sent), identification
  order, a replaced file not reusing a launch id, launch learning (path never
  sent natively), the three states of the tab note.
- Dart suites touching the changed code (RetroAchievements, libretro, RPCS3,
  ARMSX2, library): 359 tests, all passing; `flutter analyze` on the changed
  files: no issues; 12-locale coverage script: pass.
- The new Objective-C method was syntax-checked with clang (ARC, blocks) and
  minimal Foundation stubs. `test/libretro_ios_syntax_test.py` now compiles and
  links the reader and libchdr for iPhone; it runs on macOS in CI and was
  **not run here**.

Not executed: Xcode/iPhone build, the macOS syntax/link check, anything on a
device (in-game recognition of real `.chd`/`.cso` games, library display).

## Handoff for 612

Product sources only (no Core): `packages/libretro_internal_bridge` (reader,
libchdr, plugin method, published game id, podspec), `packages/rpcs3_internal_bridge`
(`Rpcs3Achievements.mm`: published game id), Dart services/screens/l10n listed in
the commit, tests and this document. The libretro and RPCS3 bridges are rebuilt
with the application; the Flutter, native (libretro syntax/link) and
`test/ra_disc_hash_reader_test.py` groups must run (the last needs gcc, zlib,
chdman and genisoimage; it skips otherwise).
