# Unified cheat catalogue: origin publication (v2)

The maintainer's rule, 28 October 2026: RewindBox does not host the codes of
sources that grant no licence for them. The app downloads those codes from
the sources themselves, and the player sees no difference: the same "download
the cheat catalogue" button, progress, list, and installed files.

## What changes

| | Hosted publication (v1) | Origin publication (v2) |
| --- | --- | --- |
| Index | `native/cheats/catalogue/manifest.json.gz` | `native/cheats/catalogue/v2/manifest.json.gz` (bundled in the app) |
| Games, chunk SHA-256 and sizes | — | identical to v1 |
| Packs | every program whole | programs of unhosted sources keep everything but their code |
| Codes of unhosted sources | in RewindBox's packs | downloaded by the app from each source at a pinned revision |

The unhosted sources are those whose register verdict is "no licence
evidence", "tooling licence only" or "conditional permission"
([register](evidence/cheat-source-decision-register-2026-10-28.json)). A
program shared with a hosted source stays whole.

## How a program is published

The code fields of such a program (`code`, `lines`, `source_code`, and for
FBNeo `choices` and `native_document`) are replaced by a recipe:

```json
"origin": {"f": 0, "r": [[812, 829], "\n", [830, 847]], "n": "plus"}
```

- `f`: a file of the pack's own `origin.files` table, which gives the source,
  path, size and SHA-256 at the pinned revision. The pack's
  `origin.sources` gives the source's URL template (`raw`), its pinned
  tarball (`archive`), or its single archive (`bundle`)
  ([tools/cheats/origin/sources.py](../tools/cheats/origin/sources.py)).
- `r`: byte ranges of that file (optionally `[s, e, "x"]`, the Nestopia XML
  hex transform), and separator literals limited to `\n : ? +`. A recipe
  never carries code.
- `z`: a member of a zip origin (MiSTer games, the PSX Datacenter, Mighty Mo
  and Delta archives).
- `k`: `mister` (binary tuples converted as the importer did) or `fbneo`
  (choices rebuilt from the block). `n`/`d` reproduce the importer's
  normalisation.

[recipe.py](../tools/cheats/origin/recipe.py) is the reference.
[origin_recipe.dart](../packages/neo_cheat_catalog/lib/src/origin_recipe.dart)
is its port, with Python's exact text semantics (`strip`, `splitlines`, `\s`,
cp1252, float `repr`).

## How the app installs a v2 pack

1. The native catalogue (`NeoUnifiedCheatCatalog.m`) downloads the pack, which
   is hosted and checked against the manifest as before.
2. A pack with an `origin` table goes to the Dart resolver
   (`NeoCheatCatalog.enableOriginDownloads`, `OriginResolver`) through the
   plugin's channel.
3. The resolver downloads each origin file it needs.
   - Each file is checked against its size and SHA-256, then cached by digest.
   - After 64 files of one source, or on HTTP 429, it downloads the source's
     pinned tarball once instead and stores each file under its SHA-256.
4. The resolver rebuilds every chunk with the canonical JSON encoder, the
   exact bytes of Python's `json.dumps(sort_keys=True, ensure_ascii=False)`.
5. The native catalogue checks each chunk against the manifest SHA-256, as it
   always did, then installs it.
6. If a source changed or vanished, its files are refused. The pack fails like
   any failed download, and the rest of the catalogue is unaffected.

## Nothing breaks for players

- **Installed chunks.** v2 lists the same chunk SHA-256 as v1. An installed
  game stays installed: `installPack` finds every chunk already on disk and
  downloads nothing.
- **Updated app.** The bundled index changes, so on first launch the app adopts
  v2 (`localManifest`) and refreshes from the v2 URL.
- **Older apps.** They keep reading v1 and its packs, which stay hosted. They
  can be removed later, once players have updated; installed chunks would
  still work.
- **Personal cheats and engine imports** are not touched.

## Coverage (28 October 2026)

- 718,409 programs are located and rebuilt byte for byte, over 14 sources:
  MiSTer, CWCheat, FBNeo, GeckoArchive, DuckStation, PSX Datacenter,
  Mighty Mo, the shadow, PAL and Yuki pnach collections, weed-sheet, LunaMoo,
  the dillonhafer gist and the Delta workbook.
- The rest stay whole for now (see `v2/VALIDATION.json`):
  - `dragon_pnach478` (785): RAR archives, which the app cannot open in Dart;
  - 15 Mighty Mo multipart programs;
  - about 45 programs from web pages and local snapshots, which have no
    pinned revision.

## Verification

- `tools/cheats/origin/locate.py` finds every program in the pinned files and
  checks that the recipe gives back its exact fields.
- `tools/cheats/origin/skeleton.py` writes v2, and rebuilds every chunk to
  the published bytes before publishing it as a skeleton.
- `test/cheat_canonical_json_test.dart` re-encodes every published chunk in
  Dart byte for byte (51,014 chunks with `CANONICAL_ALL=1`).
- `test/cheat_origin_resolver_test.dart`: rebuild, integrity refusal, cache,
  and the archive fallback.
- `test/cheat_origin_publication_test.dart` (with `ORIGIN_DIR`): every v2
  pack rebuilt by the Dart resolver from the pinned files has the manifest
  SHA-256.
- `test/cheat_origin_v2_test.py`: v2 has the same games as v1, no code field
  for an origin program, and recipes made only of ranges and separators.
- `test/unified_catalog_published_index_test.py` (macOS CI) loads both the
  hosted v1 index and the bundled v2 index in the real Foundation reader.
- `test/unified_catalog_origin_native.m` (macOS CI, `unified-cheats`), on the
  native catalogue:
  - an origin pack is installed through the resolver;
  - a wrong rebuild is refused;
  - a missing or failing resolver is reported;
  - an installed chunk is kept with no download.

## Regeneration

After any v1 build (`tools/cheats/unified_catalogue.py` writes the bundled
index), regenerate v2 and copy it into the bundle:

```sh
python3 tools/cheats/origin/locate.py --origins <dir> --out recipes.json.gz
python3 tools/cheats/origin/skeleton.py --origins <dir> --bundles <dir> --recipes recipes.json.gz
cp native/cheats/catalogue/v2/manifest.json.gz packages/neo_cheat_catalog/ios/Resources/manifest.json.gz
```

`<dir>` holds each source at the revision in `sources.py`.
