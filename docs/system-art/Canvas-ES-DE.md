# Canvas (ES-DE) System Art

Requested by the maintainer on 19 October 2026: add
https://github.com/zenandiko/canvas-es-de as a source of main-menu system
icons in Settings › System Art.

NeoStation iOS exposes it as the curated external pack **Canvas (ES-DE)**
(`CanvasESDE`). The artwork is not bundled into the application binary:
NeoStation downloads the selected systems' capsules on demand from the original
repository, exactly like RiiSU.

## Sources

- Canvas-Capsule Theme — Custom Edition, by zenandiko:
  https://github.com/zenandiko/canvas-es-de
- Original Canvas theme for ES-DE, by Siddy212 (CC BY-NC-SA, artwork and
  layouts credited to fagnerpc): https://github.com/Siddy212/canvas-es-de

zenandiko's repository carries an MIT `LICENSE`; its README states personal,
non-commercial use only and that game artwork, logos and trademarks belong to
their owners. See `assets/legal/Canvas-ES-DE-ATTRIBUTION.md`.

## Integration

- **Pinned revision.** Images come from
  `12d03b1856b892497a3fa1c943888c1f542f9236`, `theme/flat/webp/<capsule>.webp`
  (247 square capsules, about 110 KB each, 1500 × 1500). The revision is also
  the pack version: moving the pin redownloads the pack.
- **Variant.** The `flat` variant is used: square, opaque images that fill the
  system card like the other packs. The `rounded with shadow` variant draws its
  own rounded corners and transparent shadow, which the card already provides.
- **No `theme.json` upstream.** NeoStation builds the pack metadata itself
  (`NeoAssetsService._canvasThemeMetadata`) and never requests one.
- **Names.** Capsules are named after ES-DE folders (`psx`, `megadrive`,
  `gamegear`...). `tools/system_art/canvas_es_de.py` maps every alias of every
  system in `assets/systems/*.json`, lowercased, to a capsule and writes
  `lib/services/system_art/canvas_es_de_capsules.dart`; `--check` fails when the
  map is stale. An alias that has its own capsule keeps it (`gx4000`,
  `megadrivejp`, `sufami`); hack systems without a capsule use their base
  console, `all` uses `allgames`, `favorites` uses `auto-favorites`.
- **Coverage.** 116 of the 122 systems have a capsule. `amazon`, `gog`,
  `music`, `pet`, `pico` and `vc4k` have none: nothing is requested for them and
  their cards keep the default appearance. Only WebP is requested.

## Checks

- `test/services/neo_assets_service_external_pack_test.dart`: routing, aliases,
  case, uncovered systems, every capsule present in the pinned file list.
- `.github/workflows/legal-compliance-check.yml`: the test above, the map
  `--check`, attribution file and credits entry (dispatch with `--ref Claude`).
- All 136 capsules referenced by the map answered HTTP 200 at the pinned
  revision on 19 October 2026.

No device validation: the pack has not been displayed on an iPhone.
