# Growing the catalogues (16 November 2026)

RewindBox has four catalogues: the unified cheat catalogue, the Cheats &
Enhancements catalogue, the HD texture catalogue and the shader catalogues.
Each is generated from pinned sources by its own builder. This page says how
to find what moved upstream, how each catalogue takes new content without
breaking what a player has installed, and what was added on 16 November 2026.
The figures come from `tools/catalogues/report.py`, which reads only the
generated files.

## Two tools for every catalogue

```sh
python3 tools/catalogues/watch.py [--only shaders,textures,enhancements,cheats] [--delta]
python3 tools/catalogues/report.py [--compare <commit>] [--json]
```

- **`watch.py`** lists every pinned source and asks its upstream whether it
  moved.
  - A git source costs one `git ls-remote` (the advertised head; nothing is
    cloned). An HTTP source costs one conditional request (`If-None-Match`,
    `If-Modified-Since`).
  - Answers are kept in `build/catalogue-watch/cache.json`. A source asked
    less than `--max-age` hours ago (20 by default) is not asked again, two
    requests to one host are at least `--pace` seconds apart, and a host that
    refuses is not asked again in the run.
  - `--delta` adds, for a moved git source, the names of the files that
    changed between the pin and the head (a blobless fetch of the two
    commits: no file content is downloaded).
  - It changes no catalogue. A moved source is refreshed by its builder,
    which reviews and pins the new input.
  - It lists 62 pins. On 16 November 2026 it asked 33 hosts once and found 15
    moved pins; a second run made one request.
- **`tools/textures/discover.py --cache <file>`** keeps its answers between
  runs. In `github` mode a repository that was not pushed since its cached
  description is not read again; in `links` mode a URL that answered "ok"
  less than `--max-age` days ago is not asked again.
- **`report.py`** prints the counts of the four catalogues from the published
  files, for the working tree or a commit, and the difference between two
  states. It checks every enhancement shard against its index while counting.

## How each catalogue takes new content

| Catalogue | Reaches the app | A refresh keeps | Refresh command |
| --- | --- | --- | --- |
| HD textures | `native/textures/catalogue/manifest.json.gz`, refreshed from the HD page; bundled copy | installed packs (the store lists them from the device, not from the index); reviewed fields of imported entries | `tools/textures/import_ps2ktxpak.py` (three-way merge), then `tools/textures/build_catalogue.py` |
| Cheats & Enhancements | `native/enhancements/catalogue/r/<revision>/`, adopted by "Check for catalogue updates"; bundled index | every published revision (immutable folders); unchanged shards are not downloaded again | `tools/enhancements/build_enhancement_catalog.py [--reuse-engines …]` |
| Shaders | bundled with the app (`slang-catalog.json`, `dolphin-catalog.json`) | installed presets (the pinned commit does not move; later presets are "additions") | `tools/shaders/build_slang_catalog.py --extend` |
| Unified cheats | `native/cheats/catalogue/v2/manifest.json.gz`; packs named by their SHA-256 | every installed chunk (packs are immutable) | `tools/cheats/unified_catalogue.py`, then `tools/cheats/origin/` (see below: not refreshed in this change) |

Nothing here runs when the app starts. The app reads the index it bundles,
and fetches a newer one or a game's data only when the player opens the page
that needs it.

### HD textures

- **ps2ktxpak refresh is a merge.** The reviewed file carries fields the
  upstream catalogue does not know (a verified download, a scope, corrected
  serials). `import_ps2ktxpak.py` rebuilds the previous import from the commit
  its report names and keeps, per entry and field, the reviewed value wherever
  it differs from that previous import. An entry with a verified download
  keeps the games it was verified for. New upstream packs are appended as
  page links. An entry leaves only when ps2ktxpak now records a restriction
  (withdrawn, permission revoked, paid, creator removed) or a duplicate.
- **`generated_at` moves with the content.** The app keeps the later
  `generated_at` between the index it bundles and the one it refreshed. The
  date used to be that of the latest verification record, which does not move
  when page links are added: an updated app would have kept an older
  refreshed copy. It is now the day the content changed; a rebuild of
  unchanged sources still gives the same bytes.
- **Thread authors.** `research.py` read the author of a forum thread up to
  the first link after the author block, so a guest or a removed account was
  credited with the first link of the post ("Download", "Mirror 1"). It now
  reads the name itself, and `--brief` shortens a thread review's log.

### Cheats & Enhancements

See [ENHANCEMENTS.md](ENHANCEMENTS.md), "Publication" and "Origin download".
In short: one immutable folder per revision, the newest index copied where
each earlier revision asks for it, a record format number for what older apps
cannot read, and PS2 sources without a licence read by reference.

### Shaders

See [shaders-system.md](shaders-system.md), § 2. The pinned commit of
`libretro/slang-shaders` does not move; presets that appear upstream later are
"additions", each with its own pinned commit. The Metal gate of the macOS CI
(`test/neo_shader_kit_catalog_test.py`) validates each addition against its
own commit.

## What was added on 16 November 2026

Before: commit `d4a494a`. Reproduce with
`python3 tools/catalogues/report.py --compare d4a494a`.

| Catalogue | Before | After |
| --- | --- | --- |
| Enhancements: sources | 11 | 16 |
| Enhancements: entries | 47,184 | 50,462 |
| Enhancements: PS2 games / entries | 4,221 / 6,223 | 4,618 / 9,251 |
| Enhancements: Switch games / entries | 2,285 / 36,980 | 2,306 / 37,230 |
| Enhancements: entries by reference (not hosted) | 36,980 | 40,244 |
| HD textures: references (sources) | 1,124 (457) | 1,319 (619) |
| HD textures: page links | 615 | 810 |
| HD textures: one-tap profiles (distinct families) | 509 (424) | 509 (424) |
| Shaders (slang): presets | 982 | 987 |
| Unified cheats: programs | 2,394,631 | 2,394,631 |

- **Enhancements.** CookiePLMonster moved to `f63492f8` (+14 cheats, MIT,
  hosted). Four PS2 sources without a licence are read by reference:
  PCSX2/pcsx2_patches newer than the engine's `patches.zip` (1,007 entries),
  Gabominated/PCSX2 (850), Saramagrean/NetherSX2-cheats (767) and
  PeterDelta/PCSX2 (390). Switch exefs patches of
  KeatonTheBot/switch-pchtxt-mods are read the same way (250 mods of 60
  titles). dolphin-emu and Slippi moved to their heads without a new entry
  in the listed categories.
- **HD textures.** ps2ktxpak moved from `807733e5` to `1d6cfc3b` (+41 page
  links, 10 entries withdrawn at their creators' or the catalogue's request,
  listed in `tools/textures/ps2ktxpak-report.json`). The Dolphin forum's
  "Custom Texture Projects" threads read by the CI review of 16 November
  (run 43951999553, 151 threads) are listed as page links when their author,
  game and a download link are established: 81 entries in
  `tools/textures/sources/dolphin-forum.json`. 41 threads were already
  catalogued (the same thread, the same author and game, or the same file),
  and 29 are in `excluded-dolphin-forum.json` with their reason (no download
  link, system menus, restyles, a pending copyright claim). Ten more page
  links come from author pages read by run 43954594224: four Henriko
  Magnifico packs (the Twilight Princess page asks to link to it instead of
  distributing the pack, which is what a page link does) and six GameBanana
  pages that state CC BY-NC-ND 4.0 (`dolphin-references-2026-11.json`,
  `3ds-references-2026-11.json`; left out with reasons in
  `excluded-references-2026-11.json`). No file of these packs was downloaded
  or installed: they are references, not one-tap packs. A game the pages do
  not identify by ID is matched by its title and marked "to confirm".
  A second series read two more sets of threads the same day: pages 9 to 13
  of the Dolphin forum (run 43958561872, 102 threads: 47 entries in
  `dolphin-forum-2.json`, 10 already catalogued, 45 left out in
  `excluded-dolphin-forum-2.json`) and the PPSSPP forum's HD texture threads
  (run 43958566954, 140 threads: 26 entries in `psp-forum.json`, 38 already
  catalogued or reviewed earlier, 76 left out in `excluded-psp-forum.json`).
  Each PSP entry was read by hand: its Game ID comes from the thread's words
  or from the name of the author's archive, never from an ID quoted in
  passing. A thread title that names a sequel is matched to the sequel's
  disc only; a title that fits both a GameCube and a Wii release without
  saying which is left out. The thread lists are kept in
  `tools/textures/research/`.
- **Shaders.** Five presets added upstream after the pin (see
  shaders-system.md). Two community repositories were tried with the app's
  compiler and are not usable as published: anikom15/scanline-classic (its
  sources are produced by a build step: 14 of 15 presets have no source
  file) and ChthonVII/chthons_color_correction (its presets need files of
  another tree and lookup tables the user generates). The 1,494 "bezel" and
  150 "hdr" presets of the pinned repository stay out for the reasons in
  `slang-catalog-diagnostics.json`.

## Not done, and why

- **Unified cheat catalogue.** No program was added. `watch.py --only cheats`
  shows which pins moved (libretro-database, DuckStation chtdb, CWCheat,
  FBNeo, MiSTer among them). A refresh needs every pinned input of the build
  and of the origin publication (`tools/cheats/origin/`), several of which are
  not reachable from the work container (codeload archives, Google Drive,
  psxdatacenter.com), and it rewrites packs that the origin recipes then have
  to be located in again. It is a build to run where those hosts answer.
- **RPCS3 patches.** `rpcs3.net` is not reachable from the work container;
  the published RPCS3 records are reused as they are.
- **GBAtemp, Henriko Magnifico and other author sites.** Not reachable from
  the work container; GBAtemp also refuses the CI review (403). Their packs
  are added only from pages the CI review could read.
- **One-tap promotion of the new HD page links.** It needs
  `tools/textures/verify_packs.py` on a CI runner for each file (real
  download, the app's installer), then a review of each result.
- **iPhone.** Nothing in this change was run on a device.
