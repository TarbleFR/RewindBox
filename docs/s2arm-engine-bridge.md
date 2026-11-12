# S2Arm engine host bridge (Switch 2 playlist)

Host side of the embedded Switch 2 engine: the Flutter plugin `packages/s2arm_engine_bridge` and the Dart service
`lib/services/s2arm_internal_service.dart`. It prepares a game on the phone, loads `S2ArmEngine.framework`, drives the
engine's guest sequence and the S2Arm JIT helper, and reports every step to a journal. Nothing of S2Arm or of any game is
stored here; the engine framework, `NS2Pro.framework`, `S2ArmPrepare.xcframework` and the system data are supplied by the
delivery from their pinned producer runs (`docs/s2arm-study-2026-11-11.md` §§ 6–9, `s2arm-engine.yml`, `s2arm-core.yml`,
`s2arm-prepare.yml`; [Delivery](#delivery-pinned-engine-component-s2arm) below). Nothing here has run on a device.

## Plugin `packages/s2arm_engine_bridge`

Method channel `neostation/s2arm_internal`. Files:

| File | Role |
| --- | --- |
| `S2ArmEngineLoaded.{h,c}` | exports `rb_s2arm_engine_loaded()` / `rb_s2arm_engine_mark_loading()` (atomic flag, set-only) |
| `S2ArmLaunchJournal.{h,c}` | one JSON object per line, `write(2)` + `fsync(2)` before the call returns; sizes/addresses/codes only |
| `S2ArmPackPlan.{h,c}` | reads the image pack's `S2AEMB01` index to know the boot vs later code blocks |
| `S2ArmJitSession.{h,m}` | the JIT helper transaction on the RPCS3 model (loopback, token, nonce, `NSExtension`) |
| `S2ArmCodePages.{h,c}` | the engine's `prepare_code` hook: command 1 while attached, a spare pool after the detach |
| `S2ArmGamePreparation.{h,m}` | the preparation chain through `S2ArmPrepare.xcframework`; `S2ArmGameInfo` (NACP) |
| `S2ArmGuestABI.h`, `S2ArmPrepareABI.h` | copies of the engine's `rb_guest.h` struct and the `rb_s2arm_*` entry points |
| `S2ArmEngineBridgePlugin.{h,m}` | the method channel: `status`, `detectExport`, `gameInfo`, `storageInfo`, `prepareGame`, `cancelPrepare`, `launchGame`, `configureLaunchJournal` |

### One engine per process

`S2ArmEngine` carries one NativeAOT runtime; MeloNX's Core carries another. They cannot share a process, so:

- The plugin exports `rb_s2arm_engine_loaded()` (an atomic flag). It is set to 1 **before** the `dlopen` of the engine
  (even if the load then fails), so MeloNX's bridge, which reads it through `dlsym(RTLD_DEFAULT, "rb_s2arm_engine_loaded")`,
  refuses to load MeloNXCore afterwards (session 01, `a18490cb`).
- Before opening the engine the plugin reads MeloNX's `rb_melonx_core_loaded()` the same way; if it answers non-zero it
  refuses the launch with `engineRestartRequired` ("restart RewindBox").
- After one launch in a process the plugin refuses a second (`engineRestartRequired`): v1 is one Switch 2 game per process.

### Launch sequence (`launchGame`)

1. Refuse if MeloNX loaded, or if a launch already ran. Read the image pack's boot plan (`S2ArmPackPlan`).
2. iOS 26+: start the JIT helper (`S2ArmJitSession`), wait for connect and attach. `s2arm_code_begin(universal)`.
3. Prove the debugger round-trip (command 3 with the session nonce) before the `dlopen`, as the RPCS3 loader does.
4. Prepare the spare pool: R|X pages for the code the game loads after the detach (later NROs), filled with command 1 in
   chunks of at most 16 MiB while the helper is attached.
5. `setenv("DOTNET_GCSegmentSize","2000000",0)` and `setenv("MTL_SHADER_CACHE_SIZE","67108864",0)` (the engine's `main`,
   study § 9.1), `rb_s2arm_engine_mark_loading()`, then `dlopen(S2ArmEngine, RTLD_NOW | RTLD_GLOBAL)` (the engine looks up
   85 of its own functions with `dlsym(RTLD_DEFAULT)`, so it must be global). Its exports are restricted to the guest entry points and the names it looks up by string (`build-utils/s2arm/engine/export_list.py`), so its third-party symbols (glslang, whose weak definitions DolphinCore also carries) are not coalesced with another engine's.
6. `s2a_rb_guest_configure(&config, …)` with the prepared paths and `prepare_code = s2arm_code_prepare`.
7. Main thread: present `s2a_rb_guest_make_view_controller()` full screen; the start runs in the presentation completion.
8. `s2a_rb_guest_start(…)`. The engine maps the boot modules through `prepare_code`: each block is `mmap`-ed R|X at the
   engine's address, prepared with command 1, and returned as a read-write `vm_remap` alias the engine writes through.
9. **When the helper detaches.** Once the boot code blocks have been served (`S2ArmPackPlan`'s count and bytes) and the
   hook has been quiet for 2 s, the host issues command 0 and completes the JIT transaction. Code mapped after that comes
   from the spare pool: its pages are `vm_remap`-ed onto the engine's address and a writable alias is returned. New aliases
   after the detach are proved on device for the probe (802, `docs/s2arm-prototype-2026-11-10.md`) but not yet for the engine.
10. `session_ended(code, reason)` is delivered to Dart through the channel (`sessionEvents`).

Every step is one line in `Documents/Diagnostics/Switch2/S2Arm-launch.log`.

## Preparation (`prepareGame`)

`S2ArmGamePreparation` runs the chain of study § 8 on a background queue, with progress and cancel, into the app's private
`Library/S2Arm/<gid>/` (excluded from backup, never shared or exported): `ns2-dump --reference` (RomFS and DLC read in
place), code stage, caps, direct skeleton, module directory with the image pack, resource pack with the system data copied
(about 20 MB per game: a link into the app bundle would dangle after an app update, whose bundle path changes) and `--applied`. It reports sizes and durations by step and maps failures to codes; it never logs game content. The direct
chain version comes from `S2ArmEngine.framework/S2ArmDirectChain.txt` and the system data from `<app>/S2ArmSystemData/systemdata`
(the delivery ships the whole tree as `S2ArmSystemData`, its licences and provenance beside the data; the engine reads a
resource pack's `systemdata/` folder).

## Dart service `S2ArmInternalService`

Shaped like `XeniaInternalService` (PR #172) so the shared library layer calls both the same way:

- `systemFolder = 'switch2'`, `sessionExecutable = 'ios_s2arm_internal'`.
- Layout under `Documents/S2Arm`: `Games/` (one export folder per game), `.importing/` (staging). `ensureLayout()` creates
  them. The library layer owns `ConfigService.linkedS2ArmGameFolderPath`; this service does not touch shared files.
- `availability()` → `S2ArmRuntimeAvailability { state, detail }` with `ready`, `engineMissing`, `jitHelperMissing`,
  `systemDataMissing`, `requiresIOS26`, `unsupportedPlatform`; `availabilityForTesting` overrides it.
- Import: `importFolder({onProgress, control})` (picker) and `importFolderAt(path, …)` stage-copy into `Games/<safe title>`
  with a free-space check and cancel; a folder `detectExport` does not recognise is refused.
- `gameInfo(exportFolder)` → titleId, title (NACP, best language), publisher, display version, local `icon.jpg` path.
- `launch(exportFolder, pairingFilePath)` → `S2ArmLaunchOutcome`, preparing first when needed; `sessionEvents` is the
  native session-end stream.
- `messageKey` / `localizedError` map the native codes to `lib/l10n/s2arm_engine_locale.dart` (12 locales).

## Settings and in-game menu

No engine change: everything below uses what the pinned engine already reads in guest mode (S2Arm `ios/settings.m`,
`ios/hud.m`, services `Host.cs`, read at the pinned commit).

- **Settings** (`S2ArmSettings.m`; channel methods `getSettings` / `setSettings`): resolution scale 0.5× / 0.75× / 1×,
  anti-aliasing (none, SMAA medium, SMAA high), scaling filter (bilinear, nearest), frame-rate limit (30, 60, 120, none),
  console mode (handheld, docked), image format (widescreen, or 16:9 with black bars), performance overlay, game
  language. They are stored under the engine's own `NSUserDefaults` keys (`S2AResolutionScale`, `S2AAntiAliasing`,
  `S2AScalingFilter`, `S2AFrameRateLimit`, `S2ADockedMode`, `S2AWidescreen`), so the RewindBox screens and the engine's
  own settings page agree. The engine reads them once per process when a game starts, and a process runs one Switch 2
  game: a change applies to the next game, after RewindBox is restarted. Scales above 1 are not offered: the engine's
  direct mode (the only one it ships) clamps them to 1. The game language is `S2A_SYSTEM_LANGUAGE` (a `SystemLanguage`
  name), set before the dlopen; "automatic" leaves it unset and the engine follows the iPhone's languages.
- **Performance overlay**: the engine's own brief overlay ("FPS · memory", top right). The bridge turns it on before the
  start (`S2APerfHUD`) and the in-game menu hides or shows it live; the RewindBox preference is
  `RewindBoxS2ArmPerformanceOverlay`.
- **In-game menu** (`S2ArmSessionMenu.m`, native UIKit like MeloNX and RPCS3): a ☰ button at the top right of the game,
  or − and + held together on a controller (state read by polling; the engine's input handlers are not touched). Rows:
  show / hide the performance overlay, settings (each value written at once, with the next-launch note), quit (confirmed,
  then `s2a_rb_guest_stop`: saves written, then `session_ended`), resume. The game keeps running behind the menu: the
  engine exports no pause. Strings come from Dart at launch (`menuStrings`, `lib/l10n/switch2_settings_locale.dart`,
  12 languages), English when a key is missing. The engine's own gear menu (top left, English or Chinese) stays for
  controls, cheats and saves.
- **Saves** (`S2ArmPrepareSaveFolder`, `S2ArmInternalService.saveFolderFor` / `importSave` / `openSaveFolder`): each game
  has one folder, `Documents/S2Arm/Saves/<title> [<TITLE ID>]`, visible in the Files app (On My iPhone → RewindBox → S2Arm
  → Saves) and found again by its title id. The bridge gives it to the engine as `S2A_SAVE_FOLDER` before the dlopen (the
  engine's default, `<docs>/SaveData`, is in the private Library). The engine (S2Arm services `SaveFolder.cs`) reads it
  when the game starts if its content changed since the last write-back: JKSV, Checkpoint, Ryujinx, yuzu, NX2Apple or
  plain files; a save of another game is refused and the current save kept; an empty folder keeps the current save. A
  clean quit writes the progress back there. A save already in the old private folder is copied once into an empty new
  one. The playlist menu imports a save for the selected game (a folder picked in Files, copied in as one sub-folder,
  inside `StorageImportActivity.run`; refused while a game runs; the previous content kept as `<name> (backup)`) and
  opens the folder in Files (`shareddocuments:`). A save that names its game (Ryujinx `ExtraData0`, a yuzu path, a Checkpoint
  `0x<id> …` folder; `saveProgramId`, read as the engine's `Detect` reads them) goes to that game's folder when it is not
  the selected one: the library game's title names the folder, or `Switch 2 [<id>]` when the game is not imported yet.
  JKSV and plain files name no game and stay with the selected game; a save naming several games too (the engine decides).
  Both save items are always in the menu, second as in MeloNX's (IPA 727 showed them only with a game selected, and the
  maintainer looked for them without one). With no game selected, a save goes to the game it names. A save that names
  none goes to the game picked in a list of the Documents/S2Arm/Games games (`libraryGames`), or is refused with
  `saveNoGame` ("select the game in the list") when that list is empty. "Open the saves folder" then opens
  `Documents/S2Arm/Saves` itself. Checked by `test/s2arm_session_menu_test.py` (Saves),
  `test/s2arm_internal_service_test.dart` (saves) and `test/s2arm_playlist_menu_contract_test.dart`. Not observed on a device.
- **End of session**: on `session_ended` (either menu's quit, or an engine stop) the bridge removes the menu and dismisses
  the game view controller before it tells Dart.
- Checked by `test/s2arm_session_menu_test.py` and compiled for iOS arm64 by `.github/workflows/s2arm-bridge-ios.yml`.
  Not observed on a device.

## Delivery (pinned-engine component `s2arm`)

The common delivery carries the bridge: `packages/s2arm_engine_bridge` is a workspace member and a path dependency of the
root `pubspec.yaml` (no `pubspec.lock` change), accepted by the legal gate through
`docs/evidence/s2arm-engine-declarations-2026-11-11.json`, chained after the XeniOS playlist review. Nothing of S2Arm is
committed: each piece comes from a successful run of its producer on this branch, pinned in
`build-utils/s2arm/engine-pin.json` (run, attempt, artifact id, size, digest, members), authenticated through the API by the
generic `pinned-engine` kind of `.github/diagnostics/standard_delivery.py` (`download-engine s2arm`, `verify-engine s2arm`,
`embed-engine s2arm`, with `build-utils/s2arm/engine_pin.py` as verifier and `build-utils/s2arm/check_app.py` as check) and
checked again in the application and the signed IPA. The pin job of `s2arm-engine.yml` (`[s2arm-pin engine=… prepare=…
sysdata=…]` in a commit message) writes and prints the pin; the producer artifacts expire after 30 days.

| Piece | Producer (pin entry) | Steps | Checked |
| --- | --- | --- | --- |
| `S2ArmEngine.framework` (with `S2ArmDirectChain.txt`), `NS2Pro.framework` | `s2arm-engine.yml` (`producers.engine`) | download, embed | archives against the manifest, identity against the pin and the patch series; byte for byte in the application, payload and signature in the IPA; the chain present, well formed, recorded |
| The engine's licence and notice texts (`licenses/` of the same artifact: `license-sources.json` and the texts it lists) | `s2arm-engine.yml` (`build-utils/s2arm/engine/collect_licenses.py`, from the pinned commit, the source archives the build fetched and the .NET packs it restored) | download, embed into `Runner.app/Legal/S2Arm` after the legal bundle | the legal gate's rule (every listed text with its digest and size, nothing else, the required texts, the statement that no Nintendo data ships), the record of the producer identity, the pin, the producer commit's RewindBox notice; again in the application, the signed IPA and offline, and by the legal gate itself (`embed_legal_bundle.py --validate-only --app`, right after `engine-check-app`) |
| `S2ArmPrepare.xcframework` (static `libS2ArmPrepare.a`, only `rb_s2arm_*` visible) | `s2arm-core.yml` (`S2ArmPrepare-<sha>`, `producers.prepare`) | download, `engine_pin.py install-prepare` into `ios/Frameworks/` of the package, before the first `pod install` | the zip against the manifest and `sha256.txt`; `S2ArmPrepare-identity.json` against the producer commit's pin (S2Arm commit, Capstone and LZ4 digests) and `sha256.txt`; one iOS arm64 device library, the bytes `sha256.txt` measured, and its headers; `undefined.txt` leaves no `rb_s2arm_*` undefined; the podspec vendors that path alone (`ios/Frameworks/` is ignored by the package `.gitignore`) |
| System data tree: `systemdata/` (open fonts, tz data, synthesised empty data), `licenses/`, `SOURCES.tsv`, `SHA256SUMS` | `s2arm-prepare.yml` (`s2arm-sysdata-macOS-<sha>`, `producers.sysdata`) | download, embed as `Runner.app/S2ArmSystemData` with the engine | every file against `SHA256SUMS` (missing, extra or changed refused), its digest against the manifest; the OFL and tz licence texts, the fonts; `SOURCES.tsv`'s S2Arm commit against the pin; no Mach-O, bundle, hidden or case-colliding path |
| The plugin itself | this build (CocoaPods, Xcode) | the compilation | the generated registrant registers `S2ArmEngineBridgePlugin` once; the Runner executable defines the plugin class, `rb_s2arm_engine_loaded`, `rb_s2arm_engine_mark_loading` and the seven `rb_s2arm_*` entry points it calls (nm -gU), leaves no `rb_s2arm_*` undefined (nm -u), and exports `rb_s2arm_engine_loaded` in its dyld export trie; no separate bridge or preparation image |

The embed step records the pieces in `S2Arm-native-identity.json`; `check_app.py`, the IPA checks and the offline verifier
check them. The texts of `Legal/S2Arm`, their origins and what could not be located are in
[the notices](s2arm-legal-notices.md#the-texts-in-the-test-ipa-legals2arm).

The common steps run unchanged: every closed extension set or count the application meets (the single-IPA validator,
the Dolphin packager's and seal's `verify_ipa.validate`, the structure step's `validate_rpcs3_ipa`, the version check of
the workflow, the offline verifier) and the legal gate carry their own conditional on `S2Arm-native-identity.json`
(handed to main), inert in an application without the S2Arm identity; nothing is patched in memory (`docs/s2arm-jit-helper.md`, Validators).
Only CI can verify that CocoaPods links the vendored static library into Runner and the real symbol table, and that the
producer finds the source archives and .NET packs where the collector reads them; only a device the rest.

## Tests

- `test/s2arm_engine_bridge_test.py`: static checks (the flag contract, the channel name, the MeloNX refusal before the
  load, the environment and flag before the `dlopen`, the renamed JIT identifiers, the guest and preparation ABIs against
  the engine patch and `native/s2arm/prepare/*.h`, no game content in the journal) and an executed check of the plain-C
  pieces (the flag, the journal, the `S2AEMB01` reader).
- `test/s2arm_internal_service_test.dart`: the error mapping across locales, the availability override, and the import
  through a fake channel.
- `test/s2arm_pinned_engine_test.py` (the S2Arm instance of the pinned-engine kind on synthetic producers, its refusals,
  the committed pin) and `test/s2arm_legal_review_test.py` (the chained declaration review; on the
  effective tree of a build, skipped elsewhere).
- `test/s2arm_engine_licenses_test.py` (the producer's collection of the texts; with `S2ARM_PINNED_TREE`, on the pinned
  commit), `test/s2arm_legal_bundle_test.py` (the legal gate's conditional), and the tests of the closed-set conditionals:
  `test/s2arm_validator_test.py`, `test/s2arm_dolphin_verify_ipa_test.py`, `test/s2arm_rpcs3_helpers_test.py`,
  `test/s2arm_version_check_test.py`, `test/s2arm_downloaded_delivery_test.py`.

Only CI and a device can verify: Swift/Objective-C compilation and linking against the real frameworks, the `dlopen` and
`dlsym` of the guest entry points, `prepare_code` on device, the detach timing, the spare pool after the detach, the
presentation, and the session end.
