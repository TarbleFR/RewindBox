# NeoStation iOS — Next release draft

**Unpublished draft · Prepared 21 October 2026 · Changes since 0.0.8**

The release version, final build and download are intentionally unassigned. This
file prepares the announcement; it does not create a GitHub release or announce
an available IPA.

## Release text

This update brings a much larger HD texture catalogue, customizable touch
controls and interactive 3D game boxes, alongside continued work on PS2, PSP
and PS3 emulation.

### 🎨 HD textures, directly in NeoStation

- **424 distinct downloadable texture-pack families** across PS2, GameCube,
  Wii, PSP, Nintendo 3DS, Nintendo 64, PlayStation and NES. Browse the catalogue
  from a console's **Import** menu or a game's **Textures HD** page, check the
  supported edition, then download and install a compatible pack.
- **More supported downloads:** native RAR extraction and public-file support
  for Google Drive, MEGA and Yandex expand the files the app can install.
  Downloads retain their original author links, with integrity checks and
  pause, resume and cancellation controls.
- **PlayStation HD textures:** Beetle PSX HW now uses Vulkan through MoltenVK
  for compatible texture replacement. The PS1 catalogue has **38 references:
  8 installer-verified downloads and 30 author pages**. These pages remain
  separate from packs available for installation.
- **NES HD packs:** Mesen is available as an alternative NES engine for
  compatible packs. Nestopia remains the default; the app explains the engine
  change when enabling a Mesen pack.

The catalogue includes full packs, partial projects and interface upgrades.
Coverage depends on the game, region, revision and engine. Download and
installation verification does not establish visual compatibility in every
game. Files stay hosted by their original creators; host restrictions and
unsupported archive types still apply.

### 🎮 Make the controls your own

Move and resize the original touch controls for **Dolphin iOS, ARMSX2 and
RPCS3**, adjust their opacity, and hide individual buttons. Save a general
layout or a layout for one game, with separate orientations where supported.
GameCube, Wii Remote and Wii Classic Controller layouts have their own
settings.

Touch controls can automatically hide when a compatible controller connects.
The editor is accessible from emulator settings and the in-game menu, with
preview, cancel and reset options.

### 📀 Explore your game collection in 3D

Game boxes now appear in **Carousel, Grid and List** views. Rotate a box to see
its back, zoom into the artwork, or open it to view the disc or cartridge and
read an already-downloaded PDF manual. A dedicated Back control lets you
return through the viewer without launching the game.

Back-cover text benefits from sharper display and on-device text recognition,
with translation into NeoStation's supported languages when the required
Apple language models are available. Manuals retain their original language.
The selection glow is kept on the selected game title in List view.

### 🔧 Emulator improvements

- **PS2:** Blending Accuracy is available in the in-game graphics settings,
  with a global default and per-game overrides. PS2 HD texture replacement
  also has dedicated import and activation controls.
- **PSP:** session memory management has been reworked to address the
  allocation errors reported when closing one PSP game and opening another.
- **PS3:** persistent SPU compilation caching, updated LLVM pipelines,
  additional SPU correctness fixes and lighter compilation diagnostics.
  RPCS3 and NeoSwap remain under active development; performance varies by
  game and device.

### Emulation and project credits

**Dusklight, Mario Kart Pad and the Ports playlist have been removed.**
Existing user files are preserved. NeoStation's development now focuses on
its emulator integrations.

The former external MeloNX launcher has also been retired. **The embedded
Switch integration is still in development and is not available for play in
this release draft.**

Credits and third-party notices have been expanded for the latest components
and texture sources. Thank you to the emulator developers, texture artists,
skin creators and everyone contributing fixes and feedback.

[Licenses and notices](../NOTICE.md) ·
[HD texture sources and credits](HD_TEXTURE_CATALOG_SOURCES.md) ·
[Skin and overlay credits](OVERLAY_SOURCES_AND_CREDITS.md) ·
[Cheat catalogue sources](CHEAT_CATALOG_SOURCES.md)

---

## Maintainer notes — not part of the announcement

### Scope and evidence

Reviewed source:
[`dc46d73c6a42c5662ad3a863071edac0aa4081ad`](https://github.com/TarbleFR/neostation-ios/commit/dc46d73c6a42c5662ad3a863071edac0aa4081ad)
on `Claude`, compared with the public 0.0.8 source
[`bcca4e4a4dc89a96b1dde05d66436af54efd327e`](https://github.com/TarbleFR/neostation-ios/commit/bcca4e4a4dc89a96b1dde05d66436af54efd327e).
This is a source-tree draft, not a description of an assembled future IPA.

| Announcement item | Supporting implementation and existing evidence |
| --- | --- |
| Unified HD catalogue and public-host/RAR support | [Catalogue architecture](build486-hd-textures-catalogue.md), [native RAR and public downloads](hd-direct400-rar-native.md), [current generated source register](HD_TEXTURE_CATALOG_SOURCES.md) |
| PS1 Vulkan and expanded catalogue | [Beetle implementation and limits](build489-hd-catalogue-ps1-vulkan.md), [latest PS1 publication](ps1-hd-continued-research-2026-10-20.md) |
| Mesen as an alternative NES engine | [Integration, format restrictions and delivery](hd-textures-nes-mesen.md), [current engine catalogue](../lib/services/libretro_core_catalog.dart) |
| PS2 blending and texture replacement | [Blending implementation](build482-ps2-blending-ps3-ram.md), [PS2 texture replacement](build485-hd-textures.md) |
| Touch-layout editor | [Implemented controls, settings and validation](build484-touch-controls.md) |
| 3D boxes, manuals and text | [Box design and reading behavior](game-box-3d.md), [three-view/manual delivery](build493-plan.md), [sharp-text changes](build494-plan.md) |
| PSP relaunch correction | [Observed arena/view collision, correction and native/Simulator evidence](build497-psp-managed-memory.md) |
| RPCS3 work | [Persistent SPU cache](build481-plan.md), [LLVM pipelines](build483-llvm-pipelines.md), [diagnostics](build487-plan.md), [selective upstream/ARMSX3-related changes](build499-armsx3-rpcs3-audit.md) |
| Native ports removed | [KartPad removal](build491-plan.md), [Dusklight/Ports removal and data preservation](ports-removal-2026-10-20.md) |
| MeloNX remains unavailable | [Embedded integration](melonx-embedded-integration-2026-10-20.md), [native-session milestone and remaining work](melonx-native-session-2026-10-20.md) |

### Items to settle for the eventual release

- **Freeze the actual candidate before assigning a version or IPA.** The
  current catalogue is `2026-10-20.cb9ec63ce729`, SHA-256
  `80b1284294d7ac29d4a64f5512af1b3ffd61f26753df898ee28e2eab7f633453`:
  1,124 references, 424 installable families and 509 installation profiles.
  Variants and author-only pages are not additional installable families.
  The already-delivered Build 500 is immutable and has 37 PS1 references,
  not this latest 38-reference snapshot. Its source and delivery are recorded
  [separately](build500-rpcs3-ps1-catalogue.md).
- **Keep physical-device results distinct from existing CI evidence.** The
  PSP fix has native and Simulator regression coverage, but no confirmed
  physical-iPhone commercial-game relaunch result. PS1 replacement rendering,
  the new touch editor with a physical controller, and actual on-device
  translation also need their relevant device checks. No measured FPS gain or
  completed God of War III performance target is claimed here.
- **Keep unsupported archive cases explicit.** RAR4 solid archives, encrypted
  archives and multi-volume RAR remain unsupported. Download/installation
  checks do not guarantee pack completeness or permission to redistribute
  the creator's artwork.
- **Do not announce unfinished engines.** MeloNX's compiled engine/session
  foundation is not yet a packaged playable NeoStation integration. JIT,
  runtime dependencies, imports, original touch controls and NeoSwap work
  remain incomplete. The latest controller-ownership change must be matched
  to its own completed evidence; earlier successful engine artifacts do not
  validate it automatically. No Dreamcast/iFly or PS Vita capability is added
  to this announcement without separate implemented and verified support.
- **Attach the applicable notices to the eventual binary.** Review the final
  IPA's notices and matching source identities, including the new components;
  documentation added today does not change any previously delivered IPA.
  Outstanding source-provenance and license-compatibility findings must not
  be described as resolved merely because credits were added. Texture,
  overlay and cheat authors retain their own terms.

No GitHub release, tag, asset upload or new IPA is requested by this preparation.
