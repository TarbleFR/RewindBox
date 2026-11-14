# Xbox 360 playlist — XeniOS integration

Owner: session 03 Playlists/XeniOS (`012mUASiVyxdnhNTUKesGGm7`), branch
`work/playlists-xenios-20261110`. Integration, Core pins, CI and the IPA stay
with the main session. This file is the contract of the component; the shared
board keeps only its current state.

## Inputs

| Input | Identity |
| --- | --- |
| Owner IPA (reference only, never committed or installed) | 2.3.2 (14 Nov 2026): `xenios_ios_iphone_ipad.ipa` (uploaded in 5 parts), 49641629 B, SHA-256 `3f80bb1506cb1876d85cf714bd24080325821a3b8c279a9e87d47e98c9fa415a`, every ZIP CRC valid; before it 2.3.1: 49156698 B, SHA-256 `8ba4c18b17d7b6f8a8d1ff70eaaf22e18c391891a9e546ced572baad8def600b` |
| IPA identity | `Payload/XeniOS.app`, `com.xenios.jp`, 2.3.2 (11934) (previously 2.3.1 (11662)), Mach-O arm64 `MH_EXECUTE`, `LC_BUILD_VERSION` minos 26.0 / SDK 27.2, `MinimumOSVersion` 26.0, iPhone + iPad |
| IPA dependencies | `@rpath/libmetalirconverter.dylib` (30171152 B, Apple Metal Shader Converter runtime, the same bytes in 2.3.1 and 2.3.2: SHA-256 `923caf5d…90ff`), system frameworks incl. MetalFX, PHASE, Network (new in 2.3.2), weak StateReporting/CoreHaptics; no separate XeniOS framework |
| Upstream source | `xenios-jp/XeniOS` `5533fbfd19d45f32b40283de2382e7f54248bea9` (= `commitShort=5533fbfd1` of the 2.3.2 IPA's `XeniOSBuildAttestationPayload`, and the HEAD of the upstream `xenios` branch on 14 Nov 2026); before it `cf7c7ee452314913124d205e41e325b33891aacb` (2.3.1), no longer on that branch since upstream rewrote its history on 12 Nov 2026 (§ XeniOS 2.3.2) |
| License | Xenia BSD 3-clause (`LICENSE`, copied as `LICENSE.txt` in the IPA); Metal Shader Converter headers Apache 2.0 in `third_party/metal-shader-converter`; the dylib itself is not in the source tree |

## User flow

RewindBox → Xbox 360 playlist (existing `xbox360` system: folders, ScreenScraper
33, logo, box profile) → import button (same place as ARMSX2/RPCS3/libretro:
top right, or inside the game card in list view) → Files picker → copy into
`Documents/XeniOS/Games` → targeted rescan of the `xbox360` system only →
the existing game card, artwork, search/sort, favorites, history and
controller navigation → launch through `GameLaunchService`'s isolated
`explicit_xbox360_route`. No XeniOS launcher, library or onboarding is shown.

## Library

- System id `xbox360` (unchanged). `assets/systems/xbox360.json` gains `zar`
  and the embedded emulator `xbox360.ios.xenios`; the JSON is the source of
  truth at every sync, so fresh and upgraded databases converge without a
  migration.
- Scan roots of the `xbox360` system on iOS: `Documents/XeniOS/Games` (direct,
  like ARMSX2's root) **plus** the user's registered library folders, so an
  existing `roms/xbox360` keeps its rows, paths and media.
- Nothing is scanned at startup: `XeniaInternalService.ensureLayout()` only
  creates folders. An import refreshes the `xbox360` system alone.

## Formats (what the engine consumes, `xenia/vfs`)

| Picked file | Result |
| --- | --- |
| `.iso` (XGD/XISO) | Imported after GDFX validation at the engine's partition offsets (`gdfx_util.h` `kGdfxLikelyOffsets`); title/media ID read from `default.xex` (XEX2 execution info `0x00040006`) |
| `.zar` (ZArchive) | Imported (non-empty); the engine's reader validates it at boot |
| `.xex`, `.god` | Refused as single files ("use Import a game folder"): a loose executable needs its whole title folder, a package header its `.data` |
| Title folder with `default.xex` | Folder import (below) |
| GOD (SVOD header + `<header>.data`), single-file STFS (arcade) | Folder import (below) |
| `.xeniosprofile`, `.toml` | Refused as "profile, not a game" / "touch layout, not a game" |

Import rules: multiple selection; duplicate = same name and size, or another
file of the same size with the same title, media and disc IDs (skipped, not
recopied); same name with other content → `Name (2).iso`; free space checked
(`statvfs`, 512 MiB margin) before copying; ENOSPC mapped to "not enough
space"; 4 MiB chunked copy on the IO thread into `<name>.importing`, length
verified twice, then renamed; cancel between chunks deletes the temporary file
and keeps every earlier verified game; the source is never written. Picker
copies are discarded only after a verified copy (storage contract § 4).

## Folder import (XEX/GOD)

Import menu → "Import a game folder (XEX/GOD)" → Files folder picker
(`ExternalFolderAccess.pickAndActivateFolder`, bookmark `xenia-import`, read
in place, no picker copy) → `XeniaFolderContent.scan` → staged copy →
targeted `xbox360` rescan. The pick opens iOS's security-scoped access for the
session: file_picker 12.0.0-beta.3's `getDirectoryPath` returns a bare path
without it (`IOSFilePickerHandler.swift`), so a folder outside RewindBox's
container read as empty (found on Switch 2 with IPA 727, same call here). A
folder iOS does not open is refused as `folderAccessFailed` (12 locales).

What the engine consumes (XeniOS cf7c7ee45, `emulator.cc` LaunchPath picks
the device from the file's magic, never its extension; a directory path is
the XNA/indie path and is never used):

- **Title folder**: launched by `default.xex`; `HostPathDevice` mounts its
  parent as `game:` (emulator.cc:803, 865-896), so the whole folder
  (other `.xex`, media) is copied with its tree. A folder holding
  `default.xex` is one game: its subfolders are not searched further.
- **Content package**: a file starting with `CON `/`LIVE`/`PIRS`
  (`xcontent_container_device.h`), mounted by XContentContainerDevice. SVOD
  (Games on Demand, `volume_type` 1 at 0x3A9) needs `<header path>.data`
  holding exactly `data_file_count` (0x39D) regular files, each at most
  0xA290000 bytes; `SvodContainerDevice::LoadHostFiles` counts every entry,
  so a `.DS_Store` would break it. STFS (`volume_type` 0, arcade) is one file.
  Header fields are big-endian: content type 0x344, media ID 0x354, title ID
  0x360, display name 0x411 (UTF-16BE, first language). Launchable content
  types, as XeniOS's library: 0x4000, 0x7000, 0xD0000, 0x80000, 0x2000000;
  saves, add-ons, updates and original-Xbox titles (0x5000) are refused.
- Search: the picked folder and up to 5 levels below it (the console layout
  `<TitleID>/00007000/<hash>` fits), not following links, skipping hidden
  folders and `.data` folders; other files are ignored, as in XeniOS.

Copy: `Documents/XeniOS/.importing/<n>` (beside `Games`, never scanned) then
one rename into `Games/<title>` (`<title> (2)` when taken). A title folder
keeps its tree minus Finder metadata (`.DS_Store`, `._*`); a package becomes
`<title>.god` plus `<title>.god.data/` with only its counted data files (the
engine finds the data by the header's name + `.data` and reads the magic, so
the rename is safe; the hash name was only XeniOS's library heuristic).
Every file's length is checked; cancel (between 4 MiB chunks, and before
the final rename) and every failure delete the stage; the staging folder is
also cleared before each import. Duplicate = same kind with the same title,
media and disc IDs (name and size without a title ID). Free space: total
size + 512 MiB. Refusals: `folderNoGame`, `executableInvalid`,
`packageDataMissing`, `packageIncomplete`, `packageNotGame`, `unreadable`,
`notEnoughSpace`, `copyFailed` (12 locales).

Library on iOS: the `xbox360` scan adds `god` to the system's extensions and
keeps only `default.xex` among executables and nothing under a `.data`
folder; the row's title is the title folder's name (`default.xex`) or the
package name (`.god`), set when the row is first written. The `filename`
column is a game's identity (scraped metadata `UNIQUE(app_system_id,
filename)`, media named after it, favorites and history through
`getSingleGame`), so each `default.xex` row is stored as `<folder>.xex`, or
`<folder> [<8 hex of its path>].xex` when that name is already used by
another entry of the scan or another stored row
(`XeniaFolderContent.libraryFileNames`). A stored name never changes; rows
stored before as `default.xex` are renamed once by the next scan (ISO and
`.god` rows untouched). The metadata row once shared under `default.xex` is
left as is: those games are scraped again under their own name. Test:
`test/xenia_library_names_test.dart`. A `.god` launches
with content kind 4 (`NEO_XENIA_CONTENT_PACKAGE`, accepted by
`XeniaCore.mm` Boot; ABI unchanged at 2, an older Core refuses it with
"unsupported content kind"). Existing extension-less GOD headers in the
user's own library folders are not listed; import them instead. Android
scanning is unchanged.

Tests: `test/xenia_folder_import_test.dart` (synthetic XEX2 and XContent
headers, no game content).

## Settings

Stored by RewindBox in `Documents/XeniOS/Frontend/settings.json` (global +
per game), never in the engine's own `config/<TITLEID>.config.toml`, which keeps
guest writes. Game identity: `title:<TITLEID>` read from the image (shared by
all discs/regions of a title, survives renames), else `file:<name>`.
Every managed cvar is sent with its effective value at every boot (after
`config::LoadGameConfigForFile`), so no value of one title leaks into the next.
All of them apply at the next launch (stated in the UI).

| cvar | Values | Core consumer at `cf7c7ee45` |
| --- | --- | --- |
| `user_language` | Automatic, 1–9, 11–17 (`xbox.h` XLanguage) | `kernel/xconfig.cc:142` (XCONFIG_USER_LANGUAGE) |
| `user_country` | Automatic, the `xconfig.cc:39-53` table | `kernel/xconfig.cc:160` |
| `widescreen` | on (16:9, default) / off (4:3) | `kernel/xboxkrnl/xboxkrnl_video.cc:59, 214, 219`, `kernel/xconfig.cc:145` |
| `internal_display_resolution` | 0–16 (default 8 = 1280×720; 17 = custom is not offered) | `gpu/graphics_system.cc:571-577`, `kernel/xconfig.cc:169, 176` |
| `use_50Hz_mode` | on/off | `kernel/xconfig.cc:120`, `xboxkrnl_video.cc:55` |
| `framerate_limit` | 0 (unlimited), 30, 45, 60, 90, 120 | `gpu/command_processor.cc:489` |
| `guest_display_refresh_cap` | on/off | `app/xenia_main_ios.mm:944, 2261-2263` |
| `present_letterbox` | on/off | `ui/presenter.cc:771, 813` |
| `async_shader_compilation` | on/off | `gpu/metal/metal_command_processor.cc:785, 1015, 1038` |
| `apu_max_queued_frames` | 8, 16, 32, 48, 64 | `apu/audio_system.cc:61` |
| `xma_decoder` | new, old, master | `apu/xma_decoder.cc:161-167` |
| `mount_cache` | on/off | `emulator.cc:1974` |

`widescreen` is the aspect ratio the console reports; games read it when they
set their video mode. `internal_display_resolution` is the resolution reported
to the game: only games offering several resolutions use it, higher ones load
the GPU more.

Frontend-only (not a cvar, not in `managedKeys`, not sent in `settings`): the
performance overlay level `off` (default) / `simple` / `detailed`, global to
every Xbox 360 game, stored in the same file as
`"frontend": {"performance_overlay": "<level>"}` (`"version": 1` unchanged; a
missing or invalid object means `off`). It is passed at launch as `overlay`
and drawn natively by the bridge from a Core frame counter (the engine has no
overlay of its own).

### In-game menu

The launch `texts` map carries `menu`, `resume`, `quit` and the `display`,
`overlay`, `aspect`, `resolution`, `letterbox`, `fps`, `thermal`... strings
(locale keys `session_*`). The bridge reports changes on the
`rewindbox/xenia_internal` channel: `settingChanged {key, value}` (a per-game
override of the running game, saved only for a managed key with an accepted
value) and `overlayChanged {level}` (global). Aspect ratio, resolution and
letterbox apply at the next start of that game; the overlay applies at once.

Native side (`ios/Classes/XeniaSessionMenu.mm`, opened by the session's Menu
button or the controller's Home button, as the other playlists' in-game menus):
Resume; Display › Performance overlay (Off / Simple / Detailed); This game ›
Aspect ratio (16:9 / 4:3), Resolution reported to the game (640×480 … 1920×1080,
1280×720 default), Letterbox; Edit touch controls; Quit. The game is paused
and the Core receives a neutral pad while it is open; a swipe down resumes.
The overlay (`RBXeniaPerformanceOverlay`, top centre, takes no touch) samples
the Core twice a second: Simple shows the guest FPS; Detailed adds the frame
time, the process memory footprint and the device thermal state. FPS is the
rate of guest swaps between two samples (ABI 3 `get_stats`; samples spanning a
pause, the menu or the background are dropped).

Core ABI 3 (`XeniaCoreABI.h`): `get_stats(NeoXeniaStats*)` returns the guest
frame counter and its sample time; the counter is fed by one weak hook the
patch adds as the first statement of `MetalCommandProcessor::IssueSwap`
(`NeoXeniaNotifyGuestSwap`, a no-op outside XeniaCore; the patch test allows
exactly those lines) and restarts at each boot. `kManagedKeys` (Core) and
`XeniaManagedKeys` (bridge) gain `widescreen` and `internal_display_resolution`.
Not live on device: no iPhone run of this menu or overlay yet.

Not exposed: internal resolution scaling (`draw_resolution_scale` does not
exist on the Metal backend) and vsync (the XeniOS iOS UI has none),
renderer choice (Metal only), QoS/JIT debug cvars, `xma_decoder=fake`, the
audio backend (kept at the engine default pending audio arbitration review).

## Languages

- RewindBox interface language: unchanged mechanism; all new texts in
  `lib/l10n/xenia_locale.dart` for the 12 project locales
  (generator `tools/xenia/generate_locale.py`).
- Console/guest language: `user_language`. Automatic maps the interface
  language (fr→4, ja→2, de→3, es→5, it→6, ko→7, pt→9, ru→12, zh-Hant→8,
  zh→17); Indonesian has no Xbox 360 language and uses English (1), as the
  help text says. A signed-in XeniOS profile keeps its own language
  (`profile_manager.cc:821` seeds it once from XConfig) — documented in the UI.
- Region: `user_country`, a separate setting; Automatic uses the device
  region, United States (103, the engine default) when not in the table.

## Consoles tab (maintainer decision, 10 Nov 2026)

- The tab lists only consoles an engine of this build runs, grouped by
  application in this order: RetroArch (its built-in cores), Dolphin, ARMSX2,
  RPCS3, MeloNX, XeniOS (`ConsoleCatalog.listed`).
- Removed from the tab: the 36 systems only the external RetroArch app runs
  and consoles whose engine is missing ("Not included in this version").
  Their catalog entries, stored switches, libraries and launch routes are
  unchanged; "Show all" and "Restore defaults" act on the listed consoles.
- Xbox 360 is listed, engine **off by default**
  (`EmbeddedEnginePolicy.defaultDisabledConsoles`, choice stored under
  `console_engines_enabled_v1`, the existing key untouched). Switching it on
  adds it to the main menu; Restore defaults turns it off again. While
  XeniOS cannot run, its row says why (iOS 26 required / engine not included)
  and the switch is disabled.

## Native boundary

- `packages/xenia_internal_bridge`: Flutter plugin, pod deployment target
  18.0, ABI `XeniaCoreABI.h` v1, channel `rewindbox/xenia_internal`.
- `XeniaCore.framework` (to be built from the pinned upstream sources) is
  `dlopen`ed `RTLD_LOCAL` only on iOS ≥ 26 and only at the first launch,
  never at registration; it must export only `NeoXenia_GetAPI`
  (`-exported_symbols_list`), so its statically linked FFmpeg, fmt, SDL3,
  imgui, capstone and mbedtls cannot collide with other engines. Never
  unloaded (Xenia's cvars, logging, JIT mapping singleton and signal
  handlers are process-lifetime).
- Session: one at a time; a per-launch transaction drops late callbacks;
  prepare → `validate_jit` → boot off main; full-screen host view, Menu
  (Resume/Quit), GameController relay (X_INPUT bits), pause on resign-active,
  stop → `shutdown` off main → release view → dismiss → `ended` event. A
  shutdown past its deadline quarantines the bridge (restart required), as
  MeloNX does.
- Availability states: `ready`, `requiresIOS26`, `engineMissing`,
  `abiMismatch`, `unsupportedPlatform`. The app's own iOS 18 target is not
  raised; on iOS 18–25 every other playlist is unaffected and Xbox 360
  launches are refused with that reason.
- Why iOS 26: upstream forces `CMAKE_OSX_DEPLOYMENT_TARGET 26.0`
  (`CMakeLists.txt:4-11`); the core's two iOS 26 APIs are runtime-guarded
  (`metal_command_processor.cc:7423`, `metal_zpd_visibility_pool.cc:28`) and
  the UI already carries iOS 18–25 fallbacks, so the minimum looks like a
  policy choice. The JIT path differs (`jit_memory_ios.cc:450-456`, TXM
  broker at iOS ≥ 26). Lowering the Core's target is a separate, evidenced
  step, not done here.

## Shader converter (`libmetalirconverter.dylib`)

The IPA has no separate `XeniOS.framework`, but it does embed one native
dependency: `Payload/XeniOS.app/Frameworks/libmetalirconverter.dylib`, Apple's
Metal Shader Converter runtime. It is a hard requirement of the Core.

| Fact | Evidence |
| --- | --- |
| Reference bytes | 30171152 B, SHA-256 `923caf5d7f69b72c0e5e657ac63e48f7d8d972107a5f7d665417101d76d090ff` (pinned in `build-utils/xenia/source.json`) |
| Mach-O | thin arm64 `MH_DYLIB`, install name `@rpath/libmetalirconverter.dylib`, current/compat 0.0.0, `LC_SOURCE_VERSION` 33.39, platform IOS, **minos 13.0**, SDK 26.4, `cryptid 0`, code signature present, built by Apple (`AppleInternal` rpaths) |
| Dependencies | system only: libbz2, CoreFoundation, libarchive, libc++, libSystem (all present on iOS 18) |
| Exports | 188 external symbols in the `IR*`, `DXIL*`, `DXILContainer*`, `D3D*` namespaces only — no LLVM or libc++ symbol is exported (two-level namespace), so it cannot interpose another engine's symbols |
| How the Core uses it | non-weak `LC_LOAD_DYLIB` of the executable; `MetalShaderConverter::Initialize` (`gpu/metal/metal_shader_converter.cc:201`) is called by `MetalCommandProcessor` and its failure is fatal ("nothing can render", `metal_command_processor.cc:2619-2624`) on **both** guest-shader paths: render-target-cache compute shaders always go through it, and guest shaders default to `metal_use_dxil=true` with `metal_shader_compiler=spirv2air` falling back to MSC |
| Interface | headers in `third_party/metal-shader-converter` (IR_VERSION 4.0.1); the sources call 45 `IR*` names, 33 must be exported by the library (all present in the reference), the other 12 are header-implemented runtime helpers or enum types |
| Build input | `cmake/ios/ShaderConverter.cmake`: `XENIA_IOS_SHADER_CONVERTER_LIBRARY` must be an iPhoneOS (not macOS, not simulator) library, checked with `xcrun vtool` |
| License | Apple software under Apple's own terms (stated by the IPA's own `Acknowledgements.json`); the Apache-2.0 `LICENSE.txt` covers the headers only |

Consequences, enforced in this repository:

- **Not committed, not rehosted, not extracted from the owner's IPA into any
  artifact.** CI fetches XeniOS's pinned mirror at build time (see the
  XeniaCore section) or a builder supplies an iPhoneOS copy out of band;
  RewindBox has no
  redistribution permission on record, so shipping it in a published IPA is a
  maintainer/legal decision for the main session, not implied by this work.
- `build-utils/xenia/validate_shader_converter.py` authenticates the supplied
  file before any Core build or packaging: arm64 thin dylib, platform IOS,
  install name, not encrypted, minos ≤ 18.0, system-only dependencies and the
  33 required exports; `--require-pinned-digest` additionally requires the
  reference bytes. Executed against the reference copy on 10 Nov 2026: OK.
  Unit-tested on synthetic Mach-O files (`test/xenia_shader_converter_validator_test.py`).
- Packaging path: the app's `Frameworks/libmetalirconverter.dylib`
  (`@executable_path/Frameworks` is on the app's rpath), not nested inside
  `XeniaCore.framework`. SideStore re-signs it with the rest of the app.
- Loading: it is loaded only as a dependency of `XeniaCore.framework`, so
  only on iOS ≥ 26; its own minos 13.0 means it is not what imposes iOS 26.
  The bridge checks its presence first and reports `shaderConverterMissing`
  (localized) instead of an opaque dyld "Library not loaded"; a failing
  `dlopen` reports `coreLoadFailed` with `dlerror()` in the details.
- No other RewindBox engine embeds this library today, so there is no
  install-name clash; a future engine that needs it must share one validated
  copy (dyld loads a single `@rpath/libmetalirconverter.dylib` per process).

## XeniaCore framework (facade, patch, build)

`EmulatorAppIOS` (`app/xenia_main_ios.mm`) stays the boot driver: re-writing
it would lose its pause protocol (GPU idle, then audio, then guest threads,
deliberately not `Emulator::Pause`, `:1839-1930`), stop watchdog and
`ResetTitle` teardown. RewindBox drives it only through
`IOSWindowedAppContext`'s public API.

| Piece | Path | What it does |
| --- | --- | --- |
| Upstream patch | `build-utils/xenia/rewindbox-core.patch` | 47 added lines, nothing removed, every change behind `XE_NEO_EMBEDDED_CORE` (the XeniOS app build is unchanged): no microphone/party voice/voice device (`xe_ios_microphone_start`, title voice listener, `SetVoiceDeviceFactory`), no diagnostics title note, no Live social install; RewindBox launch overrides right after `config::LoadGameConfigForFile`; a title-launched hook after `LaunchPath`; RewindBox's input driver instead of the touch driver; `NeoXeniaCreateEmulatorApp` instead of `XE_DEFINE_WINDOWED_APP` (no `main`); `App.cmake` includes the RewindBox target when `NEO_XENIA_ADAPTER_DIR` is set |
| Hooks | `packages/xenia_internal_bridge/core/neo_xenia_core_hooks.h` | the four functions the patch calls |
| Facade | `core/XeniaCore.mm` (ARC, this file only) | `NeoXeniaAPI` v1: one `IOSWindowedAppContext`, one `EmulatorAppIOS`, one `XeniaMetalView` and one never-presented host view controller per process (iOSWindow keeps raw pointers to both); the `XeniaAppDelegate` steps it needs (launch arguments, log file in the storage root, `InitializeLogging`, `OnInitialize`); `LaunchGame` / `SetEmulationPaused(kUser)` / `TerminateCurrentGame`; exit, launch-failure and stop-stuck callbacks turned into transaction-tagged events; `voice_chat` and `apu_phase_head_tracking` forced off; JIT through XeniOS's own `xe_check_jit_available` |
| Pure C++ | `core/XeniaCoreInput.h` | host pad of user 0 (atomics), its `hid::InputDriver` (connected gamepad, no keystrokes, rumble not forwarded yet) and cvar application through `cvar::ConfigVars` + `LoadConfigValue` |
| Target | `core/target.cmake`, `core/exports.txt` | `XeniaCore` SHARED framework from the same sources/libraries/embedded data as `xenia-app`, `-Werror` (`xe_target_defaults`), deployment 26.0, `-exported_symbols_list` = `_NeoXenia_GetAPI`, rpaths `@executable_path/Frameworks` and `@loader_path/..` for the converter, LICENSE and Acknowledgements copied into the framework |
| Build | `build-utils/xenia/{prepare_source.py,build_core.sh,verify_core.py,upstream-files.json}` | pin + clean tree + 15 upstream API files by SHA-256 + `git apply`; converter validated (structure, exports, pinned digest) and `codesign`-checked as Apple's; host `xenia-shader-cc`; iOS configure/build exactly as XeniOS's `apple-publish.yml`; verification: arm64 iPhoneOS minos 26.0, install name `@rpath/XeniaCore.framework/XeniaCore`, converter as dependency, `_NeoXenia_GetAPI` the only export, no `main`, no absolute build path |
| CI | `.github/workflows/xenia-core.yml` (dispatch only) | `checks` (macos-26): patch test on the pinned checkout, validator tests, facade C++ check, bridge plugin compiled against Flutter for iOS 18; `core` (opt-in, runner input): Xcode 27 required, Metal toolchain, submodules without DirectXShaderCompiler, `slang`/`msc`/`fetchdata`, converter from its pinned mirror, build, artifact `dist/xenia` **without** the converter |

Executed here (Linux, no Xcode): `test/xenia_core_patch_test.py --upstream`
on the pinned checkout (patch applies, guards balanced, hooks/facade/bridge
keys agree); `test/xenia_core_cpp_test.sh` (the pure C++ parts compile with
`-Werror` against the pinned cvar, toml++, `X_INPUT_*` and `InputDriver`
headers — it caught a missing `xe::` qualification); validator on both the
mirror and the IPA copy. **Not executed:** the Objective-C++ facade and
plugin compile, the framework build, any device run; the workflow has not
been dispatched (Core CI belongs to the main session).

Shader converter supply for CI: XeniOS's own pinned mirror
(`xenios-jp/metal-shader-converter` `ios-4.0.3`, SHA-256 `bd6b729d…37aa`),
downloaded and compared on 10 Nov 2026: same code as the IPA copy
(identical bytes from offset 4096 to the code signature), only the
signature differs. It is fetched at build time, digest- and
signature-checked, and kept out of every artifact.

## JIT helper

**What XeniOS needs** (`cpu/backend/jit_memory_ios.{h,cc}` at the pin):

- Non-TXM device, or iOS below 26: only `CS_DEBUGGED`; the Core never asks
  the debugger anything (`IOSUseTXMBrokerPath` false, plain mapping).
- TXM device on iOS 26+: a 512 MiB code region below 8 GB, prepared once per
  process at the first game boot (`IOSJitMemory::Initialize`), through
  `brk #0xf00d` with `x16=1`, `x0`=start, `x1`=length, prepared address
  returned in `x0` (all 64 bits), then `x16=0` to detach — issued by the
  Core itself. Later sessions reuse the region with no request. If no
  debugger answers, the Core stops with "JIT was turned off".

**RewindBox's side**: the dedicated helper is derived from the ARMSX2
reference by `tools/xenia/derive_jit_helper.py` (identity renames plus the
attach-mode rule; `--check` fails on drift). The universal script is
byte-equal to the ARMSX2/RPCS3 one and already implements those commands
(x16 0 detach, 1 prepare with BigInt registers, 3 host nonce probe).

| Identity | Value |
| --- | --- |
| Extension | `native/xenia_internal_helper` (`XeniaJITRequestHandler`, share-services point, marker `NeoStationXeniaJITHelper`) |
| Pod | `packages/xenia_jit_helper` (`XeniaJITRequestHandlerBase.swift`, `xenia-universal.js`) |
| Host bridge | `XeniaJitBridgePlugin` in `xenia_internal_bridge`, channel `neostation/xenia_jit`, request type `com.neogamelab.neostation.xenia-jit-request` |
| Bundle / target | `com.neogamelab.neostation.xeniajithelper` / `XeniaJITHelper` (`build-utils/configure_xenia_ios.py`) |

**Decision, before every launch** (`lib/services/xenia_jit_service.dart`):
the bridge loads the Core and reads `jit_state` (ABI 2:
`NeedsAttachedTool`, `ToolAttached`, `CS_DEBUGGED`, broker path; ABI 4: code
region held).

| Core state | Plan |
| --- | --- |
| tool needed, the app's StikJIT lacks the full-width marker (`transportFullWidth` false) | refused, `jitToolUnsupported` (§ Code region) |
| tool needed, no code region below 8 GB held | refused, `jitMemoryUnavailable` (§ Code region) |
| no tool needed, debugged | nothing (second and later sessions) |
| tool needed, still attached (an earlier boot failed before the prepare) | reuse it |
| tool needed, not attached | pairing file → LocalDevVPN route probe → helper with the core handshake → launch: nonce probe (x16=3) **before** `prepare`, `validate_jit` refuses a missing tool, `boot` runs the Core's prepare and detach, then the helper's detach is confirmed (`XeniaJitWaitForDetach`) |
| no tool needed, not debugged | classic attach, then `completeJit` |

Helper connected, expected PID attached and `CS_DEBUGGED` are checked as
separate facts; each failure has its own message in the 12 locales
(`pairingRequired`, `jitAttachFailed`, `jitHelperIncomplete`,
`jitUnavailable`, `jitMemoryUnavailable`, `jitToolUnsupported`). Manual LocalDevVPN only; no external JIT app.

## Code region

**First device run (12 Nov 2026, IPA 727)**: RewindBox closed to the Home
screen right after `XeniOS launch`. The engine log (`Engine/xenia.log`) ended
with `iOS JIT: no room for the code region below 8 GB` then the FatalError
"Xenia couldn't find room for its JIT memory…": the JIT tool's prepare only
keeps addresses below 8 GB (`kExecuteRegionLimit`), so XeniOS reserves the
512 MiB region with a static initializer while its process loads. RewindBox
dlopens the Core at the first Xbox 360 launch, when the rest of the app may
already hold that address space. XeniOS's FatalError then calls its iOS hooks
and `quick_exit`: with no hook installed nothing was shown and no crash report
was written.

**ABI 4** (`XeniaCoreABI.h`): once a launch has loaded the Core on the TXM
broker path, the bridge sets `RBXeniaReserveCodeRegion` in the app's user
defaults. From then on, and whenever `Documents/XeniOS/Games` already holds a
game (the first launch after an update), every RewindBox launch (iOS 26+, Core
present) reserves
`NEO_XENIA_CODE_REGION_SIZE` PROT_NONE below `NEO_XENIA_CODE_REGION_LIMIT` at
plugin registration, with XeniOS's own hint search. Right after the dlopen,
`adopt_code_region` either keeps the Core's own reservation (`OWN`, the host
unmaps its own) or hands the host's to `IOSJitMemory` (`ADOPTED`, through
`NeoXeniaAdoptExecuteRegion`, the only function the patch adds to
`jit_memory_ios.cc`). `jit_state` then reports `NEO_XENIA_JIT_CODE_REGION_HELD`.
The Dart `jitState` map carries `codeRegionHeld` and `codeRegion` (host, own or
none) into the `XeniOS JIT:` log line.

**Without a held region** while a tool is still needed (the first Xbox 360
launch of a process that was already full, with no imported game and no
earlier Xbox 360 launch), nothing attaches:
`XeniaJitPlan.noCodeRegion` refuses with `jitMemoryUnavailable` ("close
RewindBox from the app switcher and reopen it", 12 locales). `validate_jit`
refuses the same state before `boot`. RewindBox is not closed, and the next
launch reserves the region. Cost: 512 MiB of address space (no memory) below
8 GB, held only by users who have imported or launched an Xbox 360 game; other engines'
allocations go elsewhere.

**Fatal record**: the Core installs XeniOS's `note_fatal_error` hook (at the
first prepare, before any Xenia thread): any other FatalError writes its reason
to `Engine/last-fatal.txt` before XeniOS ends the process. The next Xbox 360
launch logs it to app.log (`XeniOS: an engine fatal error closed RewindBox in
an earlier session: …`) and removes it. The early refusals of
`XeniaInternalService.launch` (availability, kind, missing file, JIT plan) are
logged with their reason (`XeniOS launch refused: …`).

**Second device run (IPA 728)**: the first launch of a process was refused
cleanly (`codeRegion: none`); after a restart `codeRegion: host` (the flag was
set), then RewindBox closed again and `Engine/xenia.log` ended at `Loaded
config`, with no FatalError line: a real crash, close to that line (Xenia's log
is written by a background thread, so its tail can be lost). Diagnostics added
in the bridge for the next run: the `XeniOS JIT:` line carries `registration`
(reserved, noRoom or notRequested, why: flag or imported games, and the
largest free gap below 8 GB at registration) and `freeBelow8GBMiB` (now); every
launch appends and syncs its stages to `Engine/launch-journal.txt` (launch,
present, presented, nonce probe, prepare, validate_jit, boot, the detach wait,
then launched or failed), which the next Xbox 360 launch copies into app.log
(`XeniOS: previous launch stages: …`, an error when the last stage is neither
launched nor failed).

**Cause of that crash** (the maintainer's `Runner-2026-11-12-082610.ips`, IPA
728): `EXC_CRASH (SIGABRT)`, main thread, `abort()` after an uncaught
`std::filesystem::filesystem_error` thrown by `create_directories` in
`EmulatorAppIOS::OnInitialize()+912`, called from the facade's
`InitializeOnMain`. `config::SetupConfig` reads the saved
`xenia-edge.config.toml` over the roots `prepare` had set, and that file, written
under IPA 727, held the absolute `content_root`, `cache_root`, `storage_root` and
`log_file` of the previous app container (the config dump shows them as
`/var/mobile/Containers/Data/Application/<uuid>/…` where the first run showed
`~/…`). iOS gives the app a new container on every update, so
`create_directories(content_root)` aimed at a directory the app may not create.
Fix: the patch calls `NeoXeniaApplyHostRoots()` right after
`config::SetupConfig` in the embedded build (the `#else` of the existing
microphone guard), and the facade sets the four cvars again from the roots of
the first `prepare` before OnInitialize reads `content_root` and `cache_root`.

**Third device run (first boot, Fable Anniversary)**: the launch journal shows
every stage through `launched` (boot 6 s, about 2170 guest frames), but neither
the touch controls nor the controller reached the title. XeniOS's
`InputSystem` reaches a driver only through guest-slot bindings it builds from
the devices drivers enumerate (`ReconcileBindings`, first at
`InputSystem::Setup`, input_system.cc:53-58 and 483-600); our
`NeoXeniaInputDriver` enumerated none, so slot 0 stayed empty. It now lists the
host pad as one auto-bound device for slot 0 (`rewindbox-host-pad`), as XeniOS's
touch overlay does (touch_input_driver_ios.cc:380-393); the facade C++ check
asserts it. The next launch was refused (`registration: noRoom (flag), largest
free below 8 GB 442 MiB`, where the booted launch had 687 MiB): at plugin
registration the Flutter engine, the Dart VM and UIKit already hold part of the
low address space. The reservation now runs in a constructor of the bridge
image (`XeniaReserveCodeRegionAtLoad`), before them; it reads the flag with
CoreFoundation preferences, and `registration` reports `… at image load`.

**The 8 GB limit lifted (maintainer's request: no launch may depend on free
address space)**: XeniOS keeps the code region below 8 GB only because
StikDebug 3.1.x drops the high bits of the address it prepares. RewindBox's
JIT helpers use its patched StikJIT 1.9.0: `build-utils/patch_stikjit_rpcs3.py`
writes 16 hex digits per address (upstream 1.9.0 writes 9), and
`validate_stikjit_ipa.py` requires that patch's marker in the IPA's
`StikJIT.framework`; RPCS3's arena at `0x7000000000` relies on it. On iOS the
A64 code cache always uses the encoded indirection (rel32 plus a 64-bit table,
code_cache_base.h), so it puts no limit on the code address either. The patch
therefore adds a weak hook right after `kExecuteRegionLimit`
(`NeoXeniaExecuteRegionLimit`, declared outside the anonymous namespace so the
reference keeps external linkage; every later use of the constant reads it),
and the facade returns 2^47. The Core's own reservation, made when it loads,
then always finds room; the bridge's reservation at image load, its flag and
the free-space measurement are removed (they held 512 MiB of address space for
nothing, which other engines such as RPCS3 need). `adopt_code_region(nullptr,
0)` still reports `codeRegion` (own or none) in the `XeniOS JIT:` line, and
`noCodeRegion` stays as a safety net.

**Only that StikJIT may prepare the region** (main session's condition): the
lifted limit is safe only while the debugger answering the Core's prepare
writes full 64-bit addresses. Every link is checked by
`test/xenia_jit_transport_test.py` (run by `xenia-core.yml`):
`patch_stikjit_rpcs3.py` (16 digits, marker `NEOSTATION_STIKJIT_RPCS3_V1`, the
`transport_marker` of `build-utils/stikjit/source.json`) →
`install_patched_stikjit.py` refuses a framework without the marker →
`configure_xenia_ios.py` links `XeniaJITHelper` against that framework, embeds
no copy in the appex and loads the app's (`@executable_path/../../Frameworks`)
→ `validate_stikjit_ipa.py` requires the marker in the IPA's
`Frameworks/StikJIT.framework/StikJIT`. At run time the bridge reads the
marker in the app's StikJIT and in any copy inside `XeniaJITHelper.appex`
(`transportFullWidth`, `transportDetail` in `jitState`, once per process).
While the Core still needs a tool: Dart refuses `transportFullWidth` false with
`jitToolUnsupported` (12 locales) before any pairing, route or helper; the
bridge refuses again before the nonce probe and `prepare` when the transport
is not full-width or the attached debugger is not RewindBox's helper with a
live handshake (an external StikDebug 3.1.x attached on its own has none):
`jitToolUnverified`, shown as `restartRequired`. No path runs the Core's
prepare through a tool that could truncate the region's address.

**Fourth device run (IPA 730, Fable Anniversary)**: the launch reached `launched` (`codeRegion=own`) and
the title screen ran at 30 FPS, but START never went past it. `Engine/xenia.log`: `ProfileManager: Found 0
Profiles`, then at START `iOS XAM: native dialog requested` answered at once with `000004C7` (cancelled): the
title asked for a sign-in (XamShowSigninUI), and in the embedding nothing answered it. Audit of everything
XeniOS's app layer (`ui/ios/app/ios_app_delegate.mm` and its view controllers, not compiled into XeniaCore)
does for a running game, now held by `test/xenia_embedding_test.py` (with `--upstream`, every app-layer
`IOSWindowedAppContext` callback is installed by the facade or listed with the reason it is not needed):

- Sign-in: the facade answers the title's sign-in itself, without a screen: a profile already in the asking
  player's slot, else the first one signed in nowhere, else a new one named `RewindBox` (then `RewindBox 2`…).
  Player 1 is also signed in as soon as the emulated kernel exists, before the title runs
  (`NeoXeniaNotifyKernelReady`, one guarded patch line after `iOS: Emulator setup complete`), and again at
  each later title start: XeniOS derives the console identity some titles encrypt saves with from the
  signed-in profile (`XConfig::ResolveOwner`; without one it was random each run: `XConfig: No machine id`).
  XeniOS's ProfileManager keeps the login for the next launches (`logged_profile_slot_0_xuid`).
- Guest message boxes and the guest keyboard (XamShowMessageBoxUI, XamShowKeyboardUI) were presented on the
  facade's host controller, which is in no window, so they were answered as cancelled too. They are now shown
  on the window of the render view (on top of the session), with XeniOS's rules (cancel style, preferred
  action, B cancels); Cancel/OK use UIKit's own translations. A stop cancels a prompt a title waits on.
- Rumble: `NeoXeniaInputDriver::SetState` ignored it. A change of player 1's motors is forwarded
  (`vibration` event, `left,right` 0..65535) and played by the bridge with CoreHaptics on the first pad with
  haptics (heavy left motor, light right one); stopped by the menu and the end of the session.
- Controllers: every connected pad is read and merged (was `GCController.current` only, which can be nil or
  another pad); losing the last pad mid-game opens the menu, which pauses the title.
- Edge swipes are deferred while a game runs (`preferredScreenEdgesDeferringSystemGestures`), so one swipe no
  longer leaves the game or opens Control Center.
- Background: on top of the bridge's pause, the app holds a background task until the pause has settled (no
  GPU or JIT work in flight when iOS suspends it) and notes/restores the audio session (a call that ended
  without "should resume" left the game silent), as XeniOS's lifecycle observer does.
- Not needed: achievements screen, gamer card, online panel (the title gets a cancel), XeniOS's own touch
  controls and profile UI refresh. The idle timer is already held by EmulatorAppIOS (screen stays awake).

**IPA wiring, for the main session** (delivery files, not edited here):
call `build-utils/configure_xenia_ios.py` after the XeniaCore pin (it
requires `dist/xenia/XeniaCore.framework`), add the `XeniaJITHelper` pod
path to `ios-ci.yml`'s lists, and add the extension row (suffix
`xeniajithelper`, principal class `XeniaJITRequestHandler`, marker
`NeoStationXeniaJITHelper`) wherever helper extensions are enumerated:
`build-utils/validate_single_ipa_distribution.py` (`EXPECTED_EXTENSIONS`),
`build-utils/validate_stikjit_ipa.py`, `build-utils/validate_rpcs3_ipa.py`,
`build-utils/validate_armsx2_ipa.py`,
`packages/dolphin_internal_bridge/ci/verify_ipa.py`,
`.github/diagnostics/standard_delivery.py` and the rewind608/609 checks;
plus `XeniaCore.framework` and the converter in `Frameworks/` once its
supply is decided.

## Touch controls

Built on RewindBox's shared touch-layout layer
([Build 484](build484-touch-controls.md)), not on a new mechanism:
`RBXeniaTouchControlsView` (`packages/xenia_internal_bridge/ios/Classes/
XeniaTouchControls.{h,mm}`) follows the ARMSX2 controls element by element.

- Layout key `xbox360` (`TouchControls/xbox360.json`, general and per-game
  scopes, landscape and portrait stock frames). Per-game key: the same stable
  identity as the settings (`title:<TITLEID>`).
- Elements: D-pad (one element), A/B/X/Y in the Xbox 360 diamond (Y top, A
  bottom, X left, B right), LB/LT and RT/RB, two sticks with L3/R3 buttons
  above them, BACK/START. Legends are product legends; the D-pad and stick
  names come from the shared catalogue.
- Pad of user 0: X_INPUT_GAMEPAD bits, sticks in [-1, 1] with Y up (the
  screen's Y is inverted), LT/RT full press while held.
- Session (`RBXeniaSessionController`): the shared hide rule
  (`NeoTouchControlsShouldHide`: hidden under the menu, or with a compatible
  controller while `NeoStation.TouchControls.xbox360.HideWithControllerConnected`
  is on, never while editing; hiding releases every control); controller and
  touch merged with RPCS3's policy when both are live (buttons OR, triggers
  maximum, larger stick deflection); rotation releases held controls.
- In-game menu (localized: resume, edit touch controls, quit): the shared
  editor over the real controls; the game is paused and the Core gets a
  neutral pad until it closes.
- Settings › Systems › Xbox 360 › Emulators: XeniOS identity and the shared
  `EmbeddedTouchControlsPanel` (hide with a controller, edit on a
  non-interactive preview registered by `XeniaTouchControlsRegisterPreview`).

Shared-layer additions (minimal, for review): `xbox360` in
`NeoTouchLayoutPlugin.m`'s console map, `NeoTouchLayout.consoles`, the panel's
layout names and `layoutXbox360` ("Xbox 360", 12 locales) in
`tools/touch_layout/strings.json` (catalogues regenerated, `--check` passes).

Skins: no Xbox 360 controller skin pack is added; a skin overlay, its
artwork, hit-testing and orientation rules belong to the Skins session,
which can layer one over these controls later.

## Review of #172 (11 Nov): launch transaction and runtime namespace

- **JIT transaction (D1).** Dart refuses an unsupported or missing game
  before `XeniaJitService.ensure()`; a Dart failure between `prepareJit` and
  the bridge calls `abortJit`. In the bridge every failure of `launch:` ends
  the transaction (`failLaunch`, and `if (stage) XeniaJitAbortTransaction()`
  after the async stages, the detach failure included, as ARMSX2's
  `failTransaction`), except while another launch is in flight (it keeps
  its own). The helper refuses `prepareJit` only while `activeSession` or
  `operationInProgress` is set, and the abort clears both: the next launch
  prepares again. Tests: `test/xenia_launch_test.dart`,
  `test/xenia_launch_transaction_test.py`.
- **Tool reuse (D2).** `reuseAttachedTool` needs `handshakeActive` (our
  helper session attached, not finished, not closed, debugger live); the
  launch's nonce probe then confirms it. A debugger attached without a live
  handshake is `staleTool`: refused with `restartRequired`, nothing attached
  or launched (a closed helper would not answer the Core's x16=1, and a new
  helper cannot attach over it). No evidence was found that the tool keeps
  answering after `[session close]`, so it is not relied on.
- **Objective-C classes (R1).** `RTLD_LOCAL` hides C symbols only; the
  bridge's classes are `RBXenia…` (`RBXeniaSessionController`,
  `RBXeniaTouchControlsView`, `RBXeniaVirtualStickView`, `RBXeniaJitSession`
  through `tools/xenia/derive_jit_helper.py`). The two plugin classes keep
  the names Flutter's registrant imports. `test/xenia_objc_namespace_test.py
  --upstream` compares them with the 194 classes/protocols of the pinned
  sources (no shared name); `verify_core.py` refuses a built Core defining
  one of them (`nm -m`, or a Core whose classes cannot be listed).
- **Session (R2, R3, R4).** Menu, quit and pause act only once the launch
  reported success (`sessionRunning`); a Core stop/error during the launch
  is held and becomes the launch's `bootFailed` result (one report, no
  `ended`); the detach wait is 30 s (the Core issues its prepare and detach
  inside `Emulator::Setup`, called from `EmulatorThread`, which boot waits
  for), and its failure ends the transaction.
- **Load.** An `abiMismatch` or `coreLoadFailed` Core is cached and reported
  by `availability` (new `coreLoadFailed` state and message, 12 locales);
  it is not opened again. `main.dart` logs a layout error instead of
  failing startup.
- **To confirm at the first compile:** the facade hands `g_host_controller`
  (never presented) to upstream; if upstream re-parents the Metal view or
  presents alerts on it, the render view leaves RewindBox's controller.
- **CI.** `xenia-core.yml` also runs on a push to this branch (host checks,
  the two new tests, the plugin compile, the helper type-check) and a
  `plugin_app` job builds a throwaway Flutter app holding only
  `xenia_internal_bridge` and `neo_touch_layout` for the simulator (compile
  and link, iOS 18 Podfile). `build_core` stays a dispatch. No existing
  workflow compiles the whole app for the simulator; `ios-ci.yml` builds the
  IPA and stays with the main session.

## Core built with an iOS 26 SDK (12 Nov 2026)

GitHub's macOS runners have Xcode 26.x only, so XeniaCore is built with the
newest iOS 26 SDK there (`rewindbox-core.patch` guards the two iOS 27 SDK uses).
Consequence, stated plainly: **StateReporting and the external-display scene
accessory (UISceneAccessory) are absent from this Core, including on iOS 27
devices such as the maintainer's iPhone** — compiled out, not merely unused.
XeniaCore logs it once at start (`RewindBox XeniaCore: iOS SDK …; StateReporting
and the external-display scene accessory are compiled out`). A Core built with
Xcode 27 would have both, unchanged from upstream.

The converter's signature is checked by signing requirements in
`build_core.sh`: `codesign --verify --strict -R '=anchor apple'`, then the
identity observed on the pinned mirror asset (identifier
`libmetalirconverter`, leaf « Software Signing », Apple Code Signing
Certification Authority, Apple Root CA, no Team ID; read from the asset's
signature on 12 Nov 2026 and recorded in `source.json`). The former
`grep -q "Authority=Apple"` check was too weak (a third-party chain ending at
Apple Root CA passes it) and, under `pipefail`, failed run 43119228652 by
itself (grep closing the pipe made `tee` fail). An Apple signature does not
name the Apple package or agreement behind the bytes (dossier open point 1).

## Legal gate (source/license declarations)

`build-utils/collect_build_source_evidence.py` binds `pubspec.yaml` to the
last review that declared it. `docs/evidence/xenios-playlist-declarations-2026-11-11.json`
is the next link: baseline = the Pocket originals review (whose `after` is
this review's `before`), `pubspec.yaml` moved on by the
`xenia_internal_bridge` entries, and three local manifests declared from
nothing (`packages/xenia_internal_bridge/pubspec.yaml`, its podspec, the
`xenia_jit_helper` podspec). No hosted package added or removed;
`pubspec.lock` unchanged; no engine binary bundled. Any later change to these
four files needs a review chained after this one (the Pocket originals block
accepts a moved `pubspec.yaml` only when this review exists). The Core's and
the converter's source and notice declarations are due when the Core ships.
Checked 11 Nov: the chain passes on this branch once the pre-existing
`libretro_internal_bridge.podspec` mismatch of `Claude` is masked; it refuses
the branch without this review and refuses a changed declared file.

## XeniaCore pin and its delivery review (12 Nov 2026)

Run 43126203790 (commit 79f3409f0, Xcode 26.x, iOS SDK 26.5) built
XeniaCore; `verify_core.py` passed (arm64 iPhoneOS, minos 26.0, only
`NeoXenia_GetAPI` exported, `@rpath/libmetalirconverter.dylib` dependency,
no Objective-C class shared with the bridge, no absolute build path). The
first full link (run 43121527685) had been refused for two runner paths:
CMake's build-tree `LC_RPATH` to the converter's directory and the `-g`
debug map; `target.cmake` now sets `SKIP_BUILD_RPATH` and links with `-Wl,-S`.

`build-utils/xenia/core-pin.json` (SHA-256 `8b850d7b…1e33`) was written by
`core_pin.py pin` in the ubuntu `pin` job (run 43131262723, triggered by
`[xenia-pin run=43126203790]`): it downloaded artifact 13904214253
(`XeniaCore-79f3409f0…`, 9,533,089 B, `73187aa0…dcd0`, expires 26 Nov) by id,
checked its digest against the API, then pinned and verified it. The binary
is 37,719,376 B, `e0a533dc…b011`, packaged fingerprint `97e08271…f9cd`. The
pin records codesign's own report of the converter in that run: identifier
`libmetalirconverter`, authorities Software Signing > Apple Code Signing
Certification Authority > Apple Root CA, TeamIdentifier not set, CDHash
`71a046f3…`, and both requirements (`=anchor apple`, the pinned identity)
satisfied. The committed file is byte-identical to the job's output (same
SHA-256). The run is on this branch: a delivery manifest names it
(`producers.engine.branch`) or main rebuilds on `Claude`.

`docs/evidence/xenios-core-delivery-declarations-2026-11-12.json`, chained
after the playlist review, binds that pin, the ten RewindBox files compiled
into the binary (equal to 79f3409f0) and the two statically linked LGPL
libraries: FFmpeg (has207/FFmpeg `xmaframes` @ `dfc5a399…`, XeniOS overlay
`third_party/ffmpeg-xenia`, LGPL 2.1 or later, no GPL/nonfree/version3
flag) and libmspack (in-tree `third_party/mspack`, LGPL 2.1). Their changes
from upstream are not enumerated. LGPL-2.1 §6(a) is recorded as the means
chosen, with `legal_clearance: false`; whether referencing the sources by
immutable revision is the « accompany » of §6(a) or calls for §6(c)/(d) is
left to the maintainer. `check_xenios_core_delivery` refuses a pin without
this review, a changed recipe file, another pin, or a clearance claim
(`test/xenios_core_delivery_review_test.py`, 9 tests).

## IPA closed sets: the Xenia identity file (12 Nov 2026)

The pinned-engine delivery step writes `Xenia-native-identity.json` at the
app root when it embeds XeniaCore (`standard_delivery.py engine_embed`). That
file is the only signal the IPA validators read, the same model as
`MeloNX-native-identity.json` and the one agreed with session 04 for S2Arm.
One table, `IDENTITY_ENGINES` in `build-utils/validate_single_ipa_distribution.py`,
maps it to the helper it adds (`XeniaJITHelper.appex`: suffix `.xeniajithelper`,
principal `XeniaJITRequestHandler`, marker `NeoStationXeniaJITHelper`,
share-services) and the images it requires (`XeniaCore.framework/XeniaCore`,
`libmetalirconverter.dylib`). Without the file the expected sets are today's,
and either image alone is refused. The places that hold closed sets import it:
`validate_single_ipa_distribution.validate`, the Dolphin `ci/verify_ipa.py`
(a retained Dolphin input: the build that crosses it declares
`components.dolphin.changedInputs`, base blob `60324580…3216` → `613eed25…136c`),
`validate_rpcs3_ipa.validate_helper_bundles` (run by the delivery's structure
step), the delivery's version step (8 bundles plus one helper per packaged
identity, each helper's Info.plist required) and
`verify_downloaded_delivery.packaged_engine_helpers` (the identities equal the
manifest's pinned engines; each names its pinned payload, which the packaged
image carries). `embed_legal_bundle.py` is unchanged: the XeniOS and Metal
Shader Converter notices ship in every build. `test/ipa_identity_engines_test.py`
(11 tests) runs each place on synthetic IPAs, the version step from the real
workflow heredoc.

## State and limits (10 Nov 2026)

- Implemented and host-tested: catalog, policy, Consoles tab, playlist import
  button, import service, settings service and screens, per-game entry in
  the game card, launch route and session monitoring, bridge Dart API, the
  JIT plan and its failures (`test/xenia_jit_service_test.dart`), the touch
  controls contract (`test/xenia_touch_controls_test.py`).
- Written, **not compiled**: the Objective-C++ plugin (no macOS/Xcode here).
- Written, not compiled: the XeniaCore facade, target and build, the JIT
  helper extension, pod and bridge, the touch controls and session (above); compiling needs a macOS runner
  (Xcode 27 for the Core) and a dispatch by the main session. Not
  implemented: the IPA wiring of the helper (main session); an Xbox 360
  skin (Skins session); rumble. Folder (XEX/GOD) import is implemented and
  host-tested (§ Folder import); no device observation.
- Until the Core ships, every launch returns `engineMissing` (or
  `requiresIOS26`): no fake success. No iPhone observation exists.

## Next action

Main session: dispatch `xenia-core.yml` (`checks`, then `build_core` on a
runner with Xcode 27), fix what the real compile reports, pin the Core.
Main session: wire `XeniaJITHelper` into the IPA (list above). Component:
fix what the first compile reports, then the first device session (launch
with the helper on a TXM iPhone, touch and controller play, editor, menu,
quit, second launch without a new attach).
