# Native RetroArch cheat readability — 16 October 2026

Branch: `Claude`. Base: delivered Build 467, branch head `0f385d67`.
Initial implementation/test source: `80cc347c19ad462195d8abd0b82e4cc1e0229825`.
This is a presentation correction. No cheat parser, adapter, catalogue content,
identity resolver, application callback, core binary or library source is changed.

## Confirmed source defect

`LibretroCheatMenu.rootPage` assembled an unverified-version warning, a format
warning, up to 512 code characters and every catalogue attribution into the
row's `detail`. `LibretroMenuPage` placed it beside the title in legacy
`UITableViewCellStyleValue1` labels, both with unlimited lines. That layout
provides no explicit vertical layout chain for this content. Setting automatic
row height alone did not make these text-heavy value cells safe.

## Correction

Cheats opt into UIKit's vertical `UIListContentConfiguration` subtitle content
view. Its multiline text, margins and accessory-aware layout participate in
self sizing. Body/subheadline fonts follow Dynamic Type. The same opt-in is
used for multiline catalogue results and source-install rows; other menu rows,
image previews and sliders retain their existing layouts.

The primary list contains the name, game title (including source region when
present) and short status labels. Codes, hashes, paths, revision identifiers
and attributions remain in the records and can be read on a separate details
page by selecting the cheat name. The right-hand switch remains independent.
A disabled activation switch does not block opening its explanation.

The details page shows full warnings and the complete code plus technical
metadata. Text is split at composed-character boundaries into bounded 512-character
cells rather than truncating the stored or displayed program. Missing
verification is labelled as unverified, not as proven incompatibility. Known
unsupported memory-engine operations retain their existing activation gate.
No consent, deduplication, persistence, selection restoration or native-code
application logic is rewritten.

## Files

| File | Change |
| --- | --- |
| `packages/libretro_internal_bridge/ios/Classes/LibretroCheatMenu.m` | Compact cheat rows, read-only details, full technical data, adaptive catalogue rows. |
| `packages/libretro_internal_bridge/ios/Classes/LibretroSessionMenu.h` | Opt-in vertical content and independent details action. |
| `packages/libretro_internal_bridge/ios/Classes/LibretroSessionMenu.m` | Self-sizing content configuration, accessible switch names, independent selection routing. |
| `lib/l10n/libretro_locale.dart` | Five new labels/hints in all twelve languages. |
| `test/libretro_simulator/cheat_menu_probe.h` | Real UIKit bounds/label/switch measurements across five dimensions and four text sizes; long-list switch tests. |
| `test/libretro_simulator/cheat_automatic_probe.h` | Actual FFVII/Digimon data, full-code preservation, unavailable-code details and long-program stress case. |
| `test/libretro_cheat_probe.py` | Stage both reviewed PS1 data fixtures in the Simulator app. |
| `test/cheat_bootstrap_test.py` | Require all new labels in twelve locales. |
| `test/fixtures/libretro_cheats/digimon-world-original.cht` | Unmodified, reviewed CC BY-SA 4.0 test data; no game image. |
| `test/fixtures/libretro_cheats/README.md` | Fixture provenance, immutable upstream revision and Git blob. |

## Validation

Local checks actually completed for the initial implementation:

- `python test/cheat_bootstrap_test.py`: 4 tests passed; 22,746 source entries,
  40,398 identities and every bundled resource digest verified.
- `python test/cheat_bootstrap_ipa_test.py`: 1 test passed (validator fixture).
- `python test/libretro_frontend_ui_contract_test.py`: passed.
- Python syntax compilation for the two modified Python scripts: passed.
- `git diff --check`: application/test sources passed. The unchanged Digimon
  upstream fixture intentionally retains its original trailing whitespace.

CI results and final build identity will be recorded only after completion.
Tests are not device validation. The layout matrix uses UIKit table dimensions
320×568, 390×844, 844×390, 768×1024 and 1024×768 and four categories from XS to
Accessibility XXXL. It checks actual label bounds, full text height, accessory
collisions and scrolling, rather than a height formula. Existing tests retain
real Nestopia, Snes9x and DeSmuME RAM activation/disable checks, explicit consent,
wrong-region exclusion and second-process persistence.

No physical iPhone/iPad, commercial FFVII/Digimon gameplay or PS1 core RAM effect
is claimed. PS1 verification uses catalogue data and native menu dispatch,
without a BIOS or commercial disc image. The 34-core package and all other
emulators remain unchanged.
