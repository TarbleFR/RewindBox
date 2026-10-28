# Source-rights follow-up — 28 October 2026

The rule is the same for both catalogues. Code bodies are published only on
proof of a licence or permission that applies to the codes. A source the
engine already ships may be referenced by name without copying it. That does
not prove the rights of the engine's own copy.

This follow-up applies the rule to the unified cheat catalogue
(`native/cheats/catalogue/`). It acts on the coordinator's dossier of the same
day, read as input and checked against the repository. The Cheats &
Enhancements catalogue was already pruned the same day; see
[ENHANCEMENTS.md](ENHANCEMENTS.md), "Rights".

## RPCS3 Wiki licence

The RPCS3 Wiki General disclaimer and the Help:Game Patches footer were read
in a browser on 28 October 2026. Both state CC BY-SA 4.0 "unless otherwise
noted" ([evidence](licenses/rpcs3-wiki-2026-10-28.md)). This confirms the
wiki's default licence. It does not audit every patch author individually.

## 60 FPS supplement (Build 478) — withdrawn or relicensed

| Profile | Programs | Finding | Action |
| --- | ---: | --- | --- |
| `pcsx2_fps478` (PCSX2/pcsx2_patches) | 125 | No licence file at the pin; the README says the patches belong to their authors | Withheld |
| `gabominated_fps478` (Gabominated/PCSX2) | 291 | No licence file at the pin | Withheld |
| `nethersx2_fps478` (Saramagrean/NetherSX2-cheats) | 486 | No licence file at `52187122`; the README says it is based on pcsx2_patches | Withheld |
| `nds_fps478` (Reddit post by TheYearOfWaluigi) | 5 | A forum post grants no redistribution licence | Withheld |
| `illusion_fps478` (illusion0001 mirror of RPCS3 patches) | 283 | 280 native documents are identical to the official patch.yml, content SHA-256 `f1f3cab0…` (same PPU hash, name and patch lines, anchors expanded). 3 differ: `27f742c0…`, `8652b210…`, `dbe94750…` | 280 relabelled CC BY-SA 4.0; 3 withheld |

These programs held no provenance shared with another source.

**Implementation.** [`tools/cheats/withdraw_fps478.py`](../tools/cheats/withdraw_fps478.py)
runs once against the reviewed index `095cf728…`, following the Pokémon France
precedent:

- 910 programs and 636 transport records (games) are removed. The 4 profiles
  move to `excluded_sources` with status `withheld`, keeping their names, URLs
  and pins.
- Only the 14 packs that held these programs are rewritten. The other 860
  packs, and every chunk outside the 14, keep their bytes.
- In the 280 kept illusion programs, only the `license` label of the
  illusion provenance changes.
- The validator of `unified_catalogue.py` accepts the result.

New totals:

- 46 active profiles;
- 2,394,631 programs (previously 2,395,541);
- 49,670 identity groups;
- 51,014 transport records;
- 874 packs.

The [receipt](evidence/source-rights-withdrawal-fps478.json) lists every
removed record and every replaced pack.

**Re-import is blocked.** In `tools/cheats/sources478.json` and
`unified-sources.json`, the 5 profiles have `publication.enabled = false`, with
a reason. The illusion profile is included: a future import must go through
the official patch.yml.

**Old caches are blocked.** `NeoUnifiedCheatCatalog.m` rejects these
programs when they come from an older downloaded index or cache:

- programs tagged with the 4 withheld sources (as it already did for Pokémon
  France);
- the 3 differing illusion programs, by program ID.

Personal cheat files and programs the player already imported into an
engine are not edited.

## Decision register for the remaining sources

The [register](evidence/cheat-source-decision-register-2026-10-28.json) records,
for each source, its pin, its licence metadata, the evidence found and a
verdict. Every GitHub source was searched on 28 October 2026, at the pinned
revision and at the current HEAD:

- `LICENSE`, `COPYING`, `NOTICE` and README files at any depth;
- the data files, for grants or restrictions.

| Verdict | Sources | Programs |
| --- | ---: | ---: |
| Licence verified against the content (illusion → RPCS3 Wiki) | 1 | 280 |
| Data licence | 8 | 1,027,330 |
| Licence of the compiling repository | 12 | 655,340 |
| Conditional permission | 1 | 59,087 |
| Licence of the tooling only | 1 | 44,029 |
| No licence or permission found | 23 | 618,209 |

**Data licence.** libretro-database (CC BY-SA 4.0), Dolphin (GPL-2.0+),
OpenEmu (Unlicense), Luckysugar (MIT), and chidreams (MIT) for
`artemis_pkg478` and, newly found at `21fc0ee8`, for `artemisrpcs3` and
`gow3_0103_ppu`. Also Snes9x (non-commercial licence; the notice must
accompany copies).

**Compiling repository's licence.** DeadSkullzJr/szTheory (AGPL-3.0),
Mupen64Plus (GPL-2.0+, with Gent's permission), Project64 (GPL-2.0), Mesen2
(GPL-3.0), Admentus (GPL-3.0), TAbdiukov (Apache-2.0), ArtemisPS3 (MIT),
Tyler (GPL-3.0), and pcsx2_cheats_collection, whose source CheatDevicePS2 is
GPL-3.0.

**Conditional permission.** The Pugsy MAME cheat.dat in FBNeo-cheats says it
"can be freely distributed with any MAME compile or any frontend", provided
the file is not modified.

**Tooling only.** DuckStation chtdb says: "Copyright for cheats and patches
is held by their original authors".

**Nothing found.** MiSTer (entirely from GameHacking.org, whose site refuses
automated reads), CWCheat Database Plus, GeckoArchive (geckocodes.org archive),
the PS2 pnach collections, Mighty Mo, LunaMoo, weed-sheet, xoevoox,
PSX Datacenter and the web excerpts. Their data files contain no explicit
restriction.

**Maintainer decision (28 October 2026).** Every active source stays
published. The maintainer regards repositories without a licence as free to
use. Without a licence, copyright stays with the authors by default, so
publication relies on that decision, on the credits, and on removal on
request (https://github.com/TarbleFR/RewindBox/issues). Sources whose
authors explicitly restrict distribution stay excluded.

## Not done here

- No device test, IPA, CI run or release.
- `test/source_rights_native.py` needs macOS; it was updated but not run.
- History is not rewritten. See the purge simulation in
  [evidence/history-purge-simulation-2026-10-28.md](evidence/history-purge-simulation-2026-10-28.md).
  Rewriting history needs a separate, explicit authorisation.
