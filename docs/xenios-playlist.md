# Xbox 360 playlist — XeniOS integration

Owner: session 03 Playlists/XeniOS (`012mUASiVyxdnhNTUKesGGm7`), branch
`work/playlists-xenios-20261110`. Integration, Core pins, CI and the IPA stay
with the main session. This file is the contract of the component; the shared
board keeps only its current state.

## Inputs

| Input | Identity |
| --- | --- |
| Owner IPA (reference only, never committed or installed) | `xenios_ios_iphone_ipad.ipa`, 49156698 B, SHA-256 `8ba4c18b17d7b6f8a8d1ff70eaaf22e18c391891a9e546ced572baad8def600b`, every ZIP CRC valid |
| IPA identity | `Payload/XeniOS.app`, `com.xenios.jp`, 2.3.1 (11662), Mach-O arm64 `MH_EXECUTE`, `LC_BUILD_VERSION` minos 26.0 / SDK 27.2, `MinimumOSVersion` 26.0, iPhone + iPad |
| IPA dependencies | `@rpath/libmetalirconverter.dylib` (30171152 B, Apple Metal Shader Converter runtime), system frameworks incl. MetalFX, PHASE, weak StateReporting/CoreHaptics; no separate XeniOS framework |
| Upstream source | `xenios-jp/XeniOS` `cf7c7ee452314913124d205e41e325b33891aacb` (= `commitShort=cf7c7ee45` of the IPA's `XeniOSBuildAttestationPayload`, and the upstream HEAD on 10 Nov 2026) |
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
| `.xex` | Refused: a loose executable needs its whole title folder (folder import not implemented yet) — scanned and launchable when it already sits in a library folder |
| GOD/STFS (header + `.data`) | Not importable as one file; not offered |
| `.xeniosprofile`, `.toml` | Refused as "profile, not a game" / "touch layout, not a game" |

Import rules: multiple selection; duplicate = same name and size, or another
file of the same size with the same title, media and disc IDs (skipped, not
recopied); same name with other content → `Name (2).iso`; free space checked
(`statvfs`, 512 MiB margin) before copying; ENOSPC mapped to "not enough
space"; 4 MiB chunked copy on the IO thread into `<name>.importing`, length
verified twice, then renamed; cancel between chunks deletes the temporary file
and keeps every earlier verified game; the source is never written. Picker
copies are discarded only after a verified copy (storage contract § 4).

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
| `use_50Hz_mode` | on/off | `kernel/xconfig.cc:120`, `xboxkrnl_video.cc:55` |
| `framerate_limit` | 0 (unlimited), 30, 45, 60, 90, 120 | `gpu/command_processor.cc:489` |
| `guest_display_refresh_cap` | on/off | `app/xenia_main_ios.mm:944, 2261-2263` |
| `present_letterbox` | on/off | `ui/presenter.cc:771, 813` |
| `async_shader_compilation` | on/off | `gpu/metal/metal_command_processor.cc:785, 1015, 1038` |
| `apu_max_queued_frames` | 8, 16, 32, 48, 64 | `apu/audio_system.cc:61` |
| `xma_decoder` | new, old, master | `apu/xma_decoder.cc:161-167` |
| `mount_cache` | on/off | `emulator.cc:1974` |

Not exposed: resolution scale and vsync (the XeniOS iOS UI has none),
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
  artifact.** The builder supplies an iPhoneOS copy out of band (Apple
  Developer download of Metal Shader Converter); RewindBox has no
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

## Core adaptation plan (next increment)

`EmulatorAppIOS` (`app/xenia_main_ios.mm`) is the only boot driver and is
tied to the XeniOS UI; re-implementing it would lose its pause protocol (GPU
idle, then audio, then guest threads, deliberately not `Emulator::Pause`,
`:1839-1930`), stop watchdog and `ResetTitle` teardown. The adaptation keeps
it and adds a small compiled-in facade behind `NeoXenia_GetAPI`:

- context: an `IOSWindowedAppContext` whose `metal_view` is a `XeniaMetalView`
  created by `create_render_view` and whose `view_controller` is the
  bridge's session controller (`ui/ios/game/window_ios.mm:159-183` reads both);
- boot: the `EmulatorThread` steps (`:2240-2530`): `LoadGameConfigForFile`,
  then RewindBox's settings through `cvar::ConfigVars` + `LoadConfigValue`,
  `Setup`, `MountStandardDrives`, `SetupSubsystems`, `SetPresenter`,
  `LaunchPath`; stop through `RequestGameStop` and the existing teardown;
- input: a RewindBox `hid::InputDriver` fed by `set_buttons`/`set_axes`
  instead of XeniOS's touch driver, so RewindBox keeps controller ownership;
- neutralized in RewindBox (each would otherwise misbehave in the host):
  `xe_ios_microphone_start` and `voice_chat` (RewindBox has no
  `NSMicrophoneUsageDescription`; a record-permission request without it
  terminates the app), `xe_ios_party_voice_start`, `xe_ios_live_social_install`
  and every online/account feature (camera, Face ID), the diagnostics outbox
  and `xe_ios_diagnostics_note_title` (inert today without the
  `XeniOSDiagnosticsURL` Info.plist key, kept off explicitly), launch-status
  and dashboard UI, background refresh, the crash-reporter extension,
  `IOSAudioSessionStart` (replaced by RewindBox's audio policy),
  `apu_phase_head_tracking` (no head-pose entitlement);
- CMake: a `XeniaCore` SHARED framework target from the static libraries
  listed in `cmake/ios/App.cmake:49-94`, deployment target 26.0, linked to
  the validated shader converter, `-exported_symbols_list` = `NeoXenia_GetAPI`.

## State and limits (10 Nov 2026)

- Implemented and host-tested: catalog, policy, Consoles tab, playlist import
  button, import service, settings service and screens, per-game entry in
  the game card, launch route and session monitoring, bridge Dart API.
- Written, **not compiled**: the Objective-C++ plugin (no macOS/Xcode here).
- Not implemented: `XeniaCore.framework` adapter and its CI build (needs
  macOS, Xcode with the iOS 27.2 SDK, Ninja/CMake, and the iPhoneOS
  `libmetalirconverter.dylib` supplied out of band and validated as above —
  not downloadable here, not extracted from the owner's IPA); the JIT
  handshake (XeniOS needs an attached debugger: a dedicated helper identity,
  like the other engines); touch controls/skin; folder (XEX/GOD) import.
- Until the Core ships, every launch returns `engineMissing` (or
  `requiresIOS26`): no fake success. No iPhone observation exists.

## Next action

Build `XeniaCore.framework` from `cf7c7ee45`: an adapter (`core/XeniaCore.mm`)
implementing `NeoXeniaAPI` over `xe::Emulator` without the XeniOS UI shell
(`app/xenia_main_ios.mm` `EmulatorThread` steps: `Emulator::Setup`,
`SetupSubsystems`, `SetPresenter`, `LaunchPath`, `ResetTitle`), a CMake
target exporting only `NeoXenia_GetAPI`, and a component workflow modelled on
`armsx2-core.yml`; then the JIT helper identity. Coordinate the Core pin, CI
dispatch and IPA inclusion with the main session.
