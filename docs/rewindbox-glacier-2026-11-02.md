# RewindBox Glacier: the validated main menu (2 November 2026)

**Status:** source on branch `Claude`; private IPA through the standard recipe (build 615 on the
verified 614). Device validation pending.

Kit: `Kit-Claude-RewindBox-Glacier.zip` (checksums verified, `KIT-SHA256SUMS.txt`), imported by
`docs/design/rewindbox-glacier/import_kit.py`. Approved layout: `reference/MENU-CIBLE.png` and
`reference/composition.json` (1837 x 856). The mock-up is never used as a background or a capture.

## What the app does now

| Part | Implementation |
| --- | --- |
| Look | `InterfaceStyle.glacier` (+ `TabIndicatorStyle.glacier`) and the `glacier` colour palette (`lib/themes/glacier_theme.dart`, kit colours). |
| Background | `GlassBackdrop` paints `assets/images/glacier/background.webp` (kit `FOND-SEUL.png`, WebP q90) with `BoxFit.cover` over `#090B10`; decoded before the first frame (`warmGlacierBackground`); the backdrop is never rebuilt on tab changes (no flash). A personal background keeps priority on Systems. A light palette keeps its own background. |
| Header | Left: white emblem (from `assets/images/rewindbox-logo.png`) + "RewindBox". Centre: LB, the 8-tab capsule, RB. Right: real notifications, time and batteries (existing preferences), scaled to the reference height. The active tab only is named. |
| Tabs | One glyph per `NavTab` (`assets/images/glacier/nav/<tab>.png`, kit SVG/PNG originals in `docs/design/.../navigation`), tinted at runtime; canonical index, labels, hidden tabs, LB/RB cycle, swipe and hit regions unchanged (cells are wider, still equal). |
| Title row | "Systèmes" aligned with the first card; "X · Mode de vue" is the existing `HeaderSortDropdown` (same menu, same X shortcut), its menu opens under the button. |
| Grid | `SystemCardGridView(glacier: true)`: `Responsive.getSystemsCrossAxisCountFromSize` columns (6 by default), one card template (the recent game takes one cell), two whole rows at the reference, more whole rows on taller screens when the library has them, card height 0.78-1.12 of the width; scrolls for the rest; selection centring, touch "select then enter", D-pad and keyboard unchanged. |
| Cards | Full-bleed art (personal background, then System Art, then the logo), name at the bottom, silver rim; the recent game shows its database artwork, a clock and "Récent". Screen readers get the full name. |
| Focus | Glacier frame: glacier-blue outline, halo and four light-blue corner accents; jumps without animation when motion is reduced; shape alone shows the selection. |
| Action bar | Dark glass band as wide as the grid. Recent game: controller, thumbnail, "Dernier joué", title, "A · Jouer". System: art, name, game count, "Paramètres" and "A · Entrer". Grows with large text. |
| System Art | "RewindBox Glacier" (`rewindbox-glacier`) embedded: 121 canonical WebP + `aliases.json` (455 spellings), credits and licences. Installed offline into `<user data>/themes/rewindbox-glacier/` by `BundledSystemArt` (versioned by content digest, staging + SHA-256, swap keeping the previous copy, resume after a kill, one shared installation). Names resolve exact file first, then the alias table (exact canonical id first: `pspminis` is PSP Minis; case/accents; the three slash aliases are keys only); every path stays inside the pack. Listed first in the System Art picker with its local preview, online or not. |
| Preset | Settings › Themes › "RewindBox Glacier": applies the interface style, palette, background, glyphs and pack together, keeps icon size, density, status pill, bubbles and motion; tapping it again restores the previous look. New installations start on Glacier (`GlacierPreset.applyDefaultForNewInstall`); updates keep every explicit choice. Each part stays changeable alone. |
| Texts | `lib/l10n/glacier_locale.dart` and three Interface Style keys, 12 locales. |
| Notices | `assets/legal/RewindBox-Glacier-ATTRIBUTION.md` (required by `embed_legal_bundle.py`), section in `THIRD_PARTY_NOTICES.md`, pack `CREDITS.md`, `CC-BY-4.0.txt`, `BAXY-README.md`; source declaration overlay `docs/evidence/rewindbox-glacier-declarations-2026-11-02.json` (pubspec asset entries). |

`lib/screens/libretro/libretro_consoles_screen.dart` reads the console catalogue and core bindings
only: System Art never declares a console.

## Verification

Real Flutter rendering of the production widgets (`test/glacier_menu_capture_test.dart`), 1837 x 856
(918.5 x 428 at 2x), the mock-up's demo data, the pack installed from the app assets, the app font
(Anta, the pinned Google Fonts file) when `GLACIER_FONT` points to it. Captures:
`docs/design/rewindbox-glacier/verification/captures/`.

Measured against `composition.json` (reference pixels):

| Band | Reference | Flutter |
| --- | --- | --- |
| Content x | 80-1755 | 80-1757 |
| Header (tab capsule) | 20-110 | 20-103 |
| Section title | 136-190 | 136-192 |
| Row 1 | 199-445 | 201-445 |
| Row 2 | 460-707 | 461-704 |
| Action bar | 729-820 | 727-820 |

Checked by the test: order (recent game, FinalBurn Neo, NES, Master System, Mega Drive, Game Boy /
Super Nintendo ... Game Boy Color), equal cards, two full rows between title and bar, title and bar
aligned with the grid, focus on the first card, "A · Jouer" at the right, brand / LB-tabs-RB / status
order, the 8 glyphs. Variants: iPhone landscape with notch and home indicator, compact width (SE),
iPad (24 systems: 4 whole rows), large text 1.35 + reduced motion (frame without animation), no
recent game (first system selected, "Entrer"/"Paramètres"), German with long names, a hidden system
and a personal background (wins over the pack), a pack not installed (logos).

Remaining differences with the mock-up: the app font (Anta) instead of the mock-up's sans; the
existing French string "Mode de Vue"; the active tab outline is the cell width (the mock-up's is a
little wider); the recent game's picture in the capture is a synthetic stand-in for scraped artwork
(the app uses the game's database artwork); the clock is the real time.

Tests: `test/rewindbox_glacier_test.dart` (alias table, offline install, version check, double
request, interrupted swap, failed update keeps the previous pack, path confinement, picker, preset,
geometry, Themes card apply/restore, 12 locales) 21/21; capture suite 8/8; existing suites
(tab strip and styles, header, grid geometry, carousel, Liquid Glass theme, interface style, nav
tabs, palettes, bubbles, startup, RA) pass, after declaring Glacier's wider cells, its product name
and its palette in the tests that enumerate them. Pre-existing failure unrelated to Glacier (also on
`HEAD`): `neo_glass_bubble_test.dart` "rapid focus changes retarget the moving lens".
