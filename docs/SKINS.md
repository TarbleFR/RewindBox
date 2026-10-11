# Controller skins in NeoStation iOS

This guide describes the skin features included in **NeoStation iOS 0.0.4
(Build 435)**, source `90a4e513e3a97f642bc45963bfb689f7c4677d46`.

Skins customize the on-screen controls and screen placement for NeoStation's
**embedded Libretro consoles**. These are the emulation cores also used by
RetroArch. NeoStation's **skin catalogs** gather the Provenance Skin Catalog,
the Delta Skins site and RetroArch touch overlays (PocketArch, libretro
common-overlays), keeping only what can be played by touch on an iPhone (see
[iPhone compatibility](#iphone-compatibility)). Skin choices here do not
configure the separate RetroArch application.

## Choose a skin

1. Tap the **console icon with +** in the main menu bar, right after the first
   icon (LB/RB also reach it). Since Build 440 it replaces **Settings → Folders
   → Embedded consoles**.
2. Select the console, then **Skins**. You can do this before importing any game.
3. Choose **Browse the skin catalogs** to browse skins for that console.
   Filter by source, orientation or favorites, search by name, author or
   source, then select **Install**.
4. In the installed skin's card, choose **Use in portrait**, **Use in landscape**
   or **Use in both orientations**.

You can also open **Skins** from an embedded console's game-list actions.

Each of the 17 embedded console profiles has a **NeoStation default skin**,
inspired by the original console's controls. The defaults support iPhone and
iPad in portrait and landscape. Catalog availability varies by console; an
empty catalog does not remove the default skin.

## Import a file

Select **Import from Files** on the console's **Skins** page, then choose a
compatible `.deltaskin`, `.manicskin` or `.zip` archive.

An archive must contain one skin with an `info.json` description and its image
assets. A ZIP containing a single `.deltaskin` or `.manicskin` can also be
imported. If a ZIP contains several skins, extract it in Files and import the
skins individually.

The importer checks the archive and console compatibility. Read any remarks
shown after installation. If a skin with the same identifier already exists,
NeoStation asks before replacing it. A file extension alone does not guarantee
that every layout or feature in that skin is supported.

## iPhone compatibility

Every skin, whether it comes from a catalog or from Files, is checked by the
same filter on its real layout. The filter gives one of three verdicts for
each console:

- **iPhone compatible**: an iPhone layout with every essential control of the
  console.
- **Adapted for iPhone**: playable after an automatic adaptation. Examples:
  button names from other emulators converted, a stick used as the D-pad, or
  an iPad layout whose buttons stay large enough on an iPhone.
- **Not usable on iPhone**: for example no iPhone layout, an essential control
  missing, no touch controls, no artwork, or made for another console. Catalog
  entries also get this verdict when they are keyboard, decoration-only or
  Android-device overlays, or links that are not skin files.

Catalog entries that are not usable are hidden; **Show why they are hidden**
lists them with their reasons. An entry that could not be checked (network)
stays listed and is checked again when you install it. On an iPhone, an import
that no console can play by touch is refused with its reasons. Skins installed
before this check keep their files; their verdict is shown on the **Skins**
page.

During a game, if the selected skin has no touch-playable layout for the
current orientation, NeoStation shows its default controls for that
orientation and says so once (not when touch controls are off or a controller
is connected).

RetroArch overlays are converted on the device into the same skin format.
Conversion covers buttons, D-pads, ABXY areas, sticks, menu and
fast-forward commands, and the two DS screens. Overlays in pixel
coordinates, and commands without a NeoStation equivalent (rewind,
on-screen keyboard), are not converted; they are listed as reasons or
remarks.

**Touch diagnostics** (in-game menu, off by default) shows for each control:

- its touch area, and whether the control is live or sends nothing;
- what each finger sends;
- the state the game actually read at its last frame;
- how long iOS took to deliver the touch.

## Portrait, landscape and game-specific choices

Portrait and landscape selections are separate. If the selected skin has no
layout for an orientation, NeoStation uses its default skin for that orientation.
Choose **Use the default skin** to reset the console selection.

During a game, open **Display and controls → Skins**. The **Save for**
section lets you apply a choice to **Every {console} game** or **This game only**.
A game-specific choice takes priority over the console choice. Use
**Restore defaults** for the selected scope when you want to remove that override.

For Nintendo DS and Nintendo 3DS, supported skin layouts place both game screens
and the touch-screen area. Supported layouts depend on the skin and device.
Some skin functions may be ignored with an import remark, including unsupported
button actions and skin-specific picture filters. Buttons painted into the
background artwork cannot be moved independently.

## Catalog sources and creator credits

| Source | Role |
| --- | --- |
| [Provenance Skin Catalog](https://github.com/Provenance-Emu/skins) | Community-maintained skin index; its DeltaStyles and Delta Skins entries are shown under those names. |
| [Primary catalog JSON](https://provenance-emu.com/skins/catalog.json) | First catalog endpoint requested by the app. |
| [GitHub catalog JSON](https://raw.githubusercontent.com/Provenance-Emu/skins/main/catalog.json) | Fallback endpoint used if the primary request fails. |
| [Delta Skins site](https://github.com/delta-skins/delta-skins.github.io) | Pages read when the catalogs open (no licence declared; each skin belongs to its creator). |
| [PocketArch](https://github.com/stunrelay/PocketArch) (MIT) | RetroArch touch overlays at a pinned commit, converted on the device. |
| [libretro common-overlays](https://github.com/libretro/common-overlays) (CC BY 4.0) | RetroArch touch overlays at a pinned commit, converted on the device; keyboard, border and effect overlays are excluded. |
| [Delta / DeltaCore](https://github.com/rileytestut/DeltaCore) | Reference skin format credited to Riley Testut and contributors. |
| Individual skin creators | Authors of the downloaded artwork and layouts, credited by each entry when available. |

The Provenance catalog is cached for 24 hours. A manual refresh requests it
again; an existing cached catalog can also be used when the network is
unavailable. Duplicates (the same file listed by several sources, or the same
skin published twice) are shown once. Compatibility checks read only the end
of each archive and its `info.json` (HTTP range requests) and are cached for
30 days. A catalog entry must expose a supported direct archive download to be
installed inside NeoStation. Web pages and store pages are not treated as skin
archives. Favorites are kept in `Documents/Libretro/SkinFavorites.json`.

NeoStation supplies its own default skins. Community skin packs are downloaded
only when selected and are not included in the IPA. Installed skin details
retain the available author and download URL, or identify an import from Files.
Each creator's terms still apply. Catalog inclusion does not make artwork
NeoStation-owned or grant permission to redistribute it.

## Files and implementation references

Installed skins are stored in `Documents/Libretro/Skins/<id>/`.
Selections are stored in `Documents/Libretro/Config/Frontend/<console>.json`;
changing an emulation core for the same console does not change its skin choice.

- [Unified catalogs](../lib/services/libretro_skin_catalogs.dart)
- [Provenance catalog service](../lib/services/libretro_skin_catalog_service.dart)
- [RetroArch overlay converter](../lib/services/libretro_overlay_converter.dart)
- [Native iPhone filter](../packages/libretro_internal_bridge/ios/Classes/LibretroSkinCompatibility.h)
- [Touch and skin audit](libretro-touch-skins-audit.md)
- [Import and selection service](../lib/services/libretro_skin_service.dart)
- [Skin manager](../lib/screens/libretro/libretro_skin_manager_screen.dart)
- [Catalog screen](../lib/screens/libretro/libretro_skin_catalog_screen.dart)
- [Native skin parser](../packages/libretro_internal_bridge/ios/Classes/LibretroSkin.m)
- [Default skins](../packages/libretro_internal_bridge/ios/Classes/LibretroDefaultSkins.m)
- [Design and implementation notes](libretro-skins-shaders.md)
- [Credits and notices](LEGAL_AND_CREDITS.md)
