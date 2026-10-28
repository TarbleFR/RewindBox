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

The [register](evidence/cheat-source-decision-register-2026-10-28.json) gives
each source its pin, its licence metadata, the evidence preserved in
[`docs/licenses/cheats/`](licenses/cheats/README.md) and a verdict:

| Verdict | Sources | Programs | Meaning |
| --- | ---: | ---: | --- |
| licence verified | 1 | 280 | Licence checked against the published content (illusion → RPCS3 Wiki) |
| licence declared | 5 | 1,012,285 | The data licence grants redistribution: libretro-database (CC BY-SA 4.0), Dolphin GameSettings (GPL-2.0+), OpenEmu (Unlicense), Luckysugar and chidreams (MIT) |
| compiler licence | 10 | 620,372 | A licence of the compiling repository, for example DeadSkullzJr/szTheory (AGPL-3.0), Mupen64Plus (GPL-2.0+, "relicensed GPL with permission from Gent"), Project64 (GPL-2.0), Admentus (GPL-3.0), TAbdiukov (Apache-2.0) and ArtemisPS3 (MIT). The authority of third-party code authors is not established |
| tooling licence only | 2 | 66,644 | DuckStation chtdb (scripts MIT; codes stay their authors') and Mesen2 |
| no licence evidence | 28 | 704,694 | No licence or written permission recorded here. Includes MiSTer (455,353), CWCheat Database Plus, FBNeo cheats, GeckoArchive, PSX Datacenter, Snes9x, pcsx2_cheats_collection and the reviewed web excerpts |

The 39 "Unspecified" metadata values are reconciled here; they are not left
as 39 automatic removals. For example, Mupen64Plus, TAbdiukov and Admentus
have preserved licence files. Programs in the existing chunks still carry
their original licence strings, which a future build can update.

**Pending maintainer decision.** Applying the rule strictly would withdraw
every source outside "licence verified" and "licence declared". That is about
1.39 million programs, including the large DS, MiSTer, PSP and arcade
databases. Those sources remain published until the maintainer decides. The
register is the input for that decision, and `withdraw_fps478.py` is the
pattern for carrying it out.

## Not done here

- No device test, IPA, CI run or release.
- `test/source_rights_native.py` needs macOS; it was updated but not run.
- History is not rewritten. See the purge simulation in
  [evidence/history-purge-simulation-2026-10-28.md](evidence/history-purge-simulation-2026-10-28.md).
  Rewriting history needs a separate, explicit authorisation.
