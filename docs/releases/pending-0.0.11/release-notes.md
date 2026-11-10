# RewindBox 0.0.11 — Build 718

Everything since RewindBox 0.0.10 (Build 559), brought together in one update.

## 🎮 PlayStation 3 — RPCS3

- **Assassin’s Creed:** audio mixing corrections prevent audio periods from being discarded during waits.
- Reduced redundant rendering interruptions and repeated graphics work, including changes to **Vulkan/MoltenVK**.
- Improved texture caching to reuse more previously calculated results.
- **Black Ops II:** corrections to SPU synchronization, memory reservations and waits involved in stalls.
- Improved SPU program preparation and cache reuse to reduce recompilation during gameplay.
- **God of War III:** removed the unintended 30 FPS limit and reduced unnecessary texture validation.
- **Assassin’s Creed IV and Dynasty Warriors 6:** corrected game profiles to use the LLVM PPU recompiler.
- Corrected texture coherence, partial graphics commands and CPU/GPU synchronization paths.
- More reliable retention of mounted ISO images.
- Corrected JIT memory reservation when the usual address range is unavailable, including on certain iOS beta versions.
- Repositioned the **Menu** and **Performance** buttons to better respect touch controls and safe areas.
- Expanded per-game settings and diagnostic tools to identify the causes of stalls more precisely.

## 🕹️ Nintendo Switch — MeloNX

- Support for the **keyboard requested by games**, plus touch access to **L3/R3**.
- Corrected controller handling during sessions and when returning to the interface.
- First-frame and GPU-transfer corrections targeting **black screens at launch**.
- Graphics ordering corrections targeting stale frames, flickering and rendering artifacts.
- Corrected shader resource declarations and compilation paths that could prevent parts of a scene from rendering.
- JIT corrections covering branches, translation-block boundaries and register-state preservation.
- Fewer repeated allocations, improved texture reuse and release of resources no longer needed.
- Improved memory-pressure handling and cleanup of resources retained after closing a session.
- **More durable shader and pipeline caches:** saves during gameplay and on pause, background loading and improved reuse between sessions.
- Preparation of previously encountered graphics variants to reduce their reconstruction during gameplay.
- Reduced redundant graphics-resource updates and improved sharing of Metal libraries between compilation workers.
- **Hogwarts Legacy** corrections covering texture copies and handling of certain invalid graphics values.
- Failure to start the iOS audio engine no longer directly aborts the application.
- Compilation cancellation during teardown addresses sessions stuck on “closing,” including the SSBU path.

## 🎨 Skins and touch controls

- Added **GameCube Pocket, Wii Pocket and PS2 Pocket** skins.
- Added **Pocket — Original** variants for GameCube, Wii and PS2 while keeping the existing designs.
- Added **Switch Pocket**, available through **Skins in the Switch playlist menu**.
- Portrait and landscape layouts, with orientation locking where supported by the selected skin and engine.
- Corrected offsets between the drawn buttons and their touch areas.
- Corrected **rectangular press highlights**, pressed states and analog-stick geometry.
- GameCube/Wii analog sticks now move as a complete circle, including the C-stick.
- Bundled skin updates now refresh older installed copies while preserving your selections.
- Restored access to **Skins from the PS2 playlist**.
- Dolphin and PS2 floating session buttons no longer cover skin controls when the skin provides its own Menu button.

## 🏆 RetroAchievements

- Centralized sign-in and **Hardcore** settings.
- Corrected repeated sign-outs, credential persistence and migration of older accounts.
- Improved session ownership of notifications and progress, including external-display presentation.
- Achievement text follows the app language when the required Apple translation features are available.
- Improved game recognition, including **CHD and CSO**, with consistent identification in the library and during play.
- Clearer messages distinguish an unrecognized game from an unreadable file.

## 🧩 Cheats & Enhancements

- A unified **Cheats & Enhancements** page for each game.
- Access to compatible frame-rate, aspect-ratio, graphics and other available game patches.
- Improved activation, deactivation and restoration of original settings.
- **Corrected unintended Switch cheat activation** when the enable list was missing.
- Cheat state remains usable after the app container moves.
- RewindBox-generated cheat files now contain only the selected programs.

## 📚 Library, artwork and manuals

- Reworked 3D cases with more faithful proportions, relief, spines and backs.
- Editable back covers and nondestructive image correction.
- Artwork matching using the ROM’s actual game identifier.
- More reliable batch scraping with better preservation of existing media.
- Improved **French cover and manual** lookup with additional sources.
- Improved scan viewing and zoom.
- Lighter Switch discovery avoids reading entire game files on the main thread.

## ✨ Interface and navigation

- New **RewindBox Glacier** style with a reversible preset.
- Bundled offline system artwork.
- Corrections to margins, obscured titles, icon sizes and carousels.
- Corrections to system bubbles and the “⋯” menu.
- An **icons-only main navigation bar**, while retaining accessible names for VoiceOver.

## 🧪 Experimental renderer

- Added an **optional native Metal 4 renderer for RPCS3**. Vulkan/MoltenVK remains available and the selected renderer is preserved.

## Testing and known limits

The downloaded Build 718 IPA passed the recorded offline package, source/component identity and delivery checks. RPCS3 Core 914 and MeloNX Core 717 are included. Native checks were run for this delivery; equivalent Flutter evidence was reused from the preceding attempt.

Automated tests and desktop benchmarks do not establish iPhone FPS, audio or gameplay improvements. The latest combined build has not been gameplay-tested on a physical iPhone. First-use shader compilation and game-specific issues may remain. Cheats and achievement support depend on the game, version and engine.

Some faithful Pocket layouts have small touch targets or Dynamic Island overlap. Switch Pocket’s HOME and Capture controls are unavailable in this engine; MeloNX does not lock session orientation through the skin. The MeloNX Metal binary-archive prototype, Switch 2 experiment and RPCS3 comparison-only Cores are not included.

## Download and installation

**IPA:** [RewindBox-0.0.11.ipa](https://github.com/TarbleFR/RewindBox/releases/download/0.0.11/RewindBox-0.0.11.ipa)

**SideStore / AltStore Classic source:** [source.json](https://raw.githubusercontent.com/TarbleFR/RewindBox/Claude/source.json)

- Requires **iOS 18.0 or later**.
- Re-sign with SideStore, AltStore Classic or your usual compatible sideloading tool. This is not a notarized AltStore PAL package or a directly installable Apple distribution build.
- Public release: **0.0.11**. IPA metadata remains **0.0.8, Build 718**; the source preserves those exact values and uses `marketingVersion` to display 0.0.11.
- Size: **263,465,367 bytes**.
- SHA-256: `001957b9dec316bad97ad19a1e1fcecaeed5c3d5168415443b7c65478623c29a`.

No firmware, keys, BIOS or game files are bundled.
