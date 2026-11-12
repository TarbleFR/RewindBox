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

**Booleans sent to Dart are BOOLs.** The bridge is Objective-C, not Objective-C++. A comparison, `!`, `&&` or `||` is a C
`int` there, and `@(x != nil)` is an ordinary `NSNumber` that Flutter's codec sends as `1`, not `true`. IPA 727 sent
`systemDataPresent`, `helperPresent`, `available`, `engineFloorMet` and `engineLoaded` that way. `_readAvailability`
compared them with `== true` and returned `systemDataMissing`, so the Consoles switch stayed off with every part present.
The maintainer forwarded that analysis. Each flag is now a `BOOL` local before it is boxed. Dart reads flags with
`S2ArmInternalService.flag` (true or a non-zero number), and `S2ArmSettings.fromMap` accepts a number too.
`test/s2arm_engine_bridge_test.py` fails on any boxed comparison in `Classes/*.m`; the 727 code fails it on six. The
libretro bridge hit the same trap in Build 454 (`test/libretro_channel_codec_test.py`). The XeniOS, RPCS3, Dolphin and
ARMSX2 bridges are `.mm`, where a comparison is a C++ `bool`. Not observed on a device.

### One engine per process

`S2ArmEngine` carries one NativeAOT runtime; MeloNX's Core carries another. They cannot share a process, so:

- The plugin exports `rb_s2arm_engine_loaded()` (an atomic flag). It is set to 1 **before** the `dlopen` of the engine
  (even if the load then fails), so MeloNX's bridge, which reads it through `dlsym(RTLD_DEFAULT, "rb_s2arm_engine_loaded")`,
  refuses to load MeloNXCore afterwards (session 01, `a18490cb`).
- Before opening the engine the plugin reads MeloNX's `rb_melonx_core_loaded()` the same way; if it answers non-zero it
  refuses the launch with its own code, `switch1EngineLoaded` (same-named message: the Switch 1 engine was loaded in
  this session, close and reopen RewindBox). It answered `engineRestartRequired` before 12 Nov 2026. The status map
  keeps the flag as `melonxCoreLoaded` (diagnostics only).
- After one launch in a process the plugin refuses a second (`engineRestartRequired`, message `restartRequired`, about
  Switch 2 only): v1 is one Switch 2 game per process.

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

### IPA 728 on device: import space, preparation feedback and reuse, MeloNX

The maintainer's test of IPA 728, with app.log. The Consoles switch now turns on (`available: true`). Three problems
remained.
- **Import refused for space** with about 68 GB available in Settings. The check used statvfs (`freeBytes`), which counts
  no purgeable space.
  - `storageInfo` now also gives `importantFreeBytes` (`NSURLVolumeAvailableCapacityForImportantUsageKey`), and the
    import checks it (`availableBytes`).
  - The import first tries `cloneTree`, an APFS `clonefile(2)` of the whole export into staging. It accepts only a
    destination inside Documents, onto a free path, without following links. On the same volume it is instant and takes
    no space. Otherwise, after removing any partial clone, the byte copy runs as before.
- **"code · 0%" for minutes.** The code stage was given no progress callback, and every launch prepared the game again
  from scratch.
  - The code stage now reports each step: addr_need, nro, each module, tables. The resource pack reports bytes. Events
    are throttled to 1 % or 250 ms, and each carries `detail` (the module), shown as "code · main".
  - `<game>/prepared.json` keeps the result and a fingerprint of the inputs. The fingerprint covers the app build, the
    direct chain, the system data list, the export folder, its parts, every ExeFS file by size and date, and the
    RomFS roots. A later launch with the same inputs and its outputs still present (image pack, `.applied`) reuses the
    result (`reused: true`). The stamp is removed before a new preparation and written after its last step.
  - Dart opens the native journal in `Documents/Diagnostics/S2Arm/s2arm-journal.jsonl`; it was never opened before. It
    logs one app.log line per step and module, the result with step durations and sizes, and the launch outcome.
- **MeloNX loaded by the Consoles tab.** Its `runtimeAvailable()` → `diagnostics` loads MeloNXCore and its NativeAOT
  runtime. After that, `melonxCoreLoaded` is true and an S2Arm launch is refused until RewindBox restarts. `launch()` now
  reads the status first and fails with `melonxCoreLoaded` (message `melonxLoaded`, 12 languages: close and reopen, then
  start the Switch 2 game) before any preparation. The MeloNX probe itself belongs to main and the MeloNX owner; reported.
Checked by `test/s2arm_engine_bridge_test.py` (137 checks), `test/s2arm_internal_service_test.dart` (clone, space,
early refusal, progress detail) and the iOS compile. Not observed on a device.

### No ambiguity between the two engines (12 Nov 2026)

The maintainer asked that the Switch 2 surfaces never mix in the Switch 1 engine. Every player-facing string names a
console, never an engine:

- The two "close and reopen" refusals are two codes and two messages in the 12 languages. A Switch 2 game already ran
  in this process: `engineRestartRequired` → `restartRequired`, which speaks of Switch 2 only (it used to say "a Switch 2
  or Nintendo Switch game"). The Switch 1 engine is loaded in this process: `switch1EngineLoaded` → `switch1EngineLoaded`
  ("the Switch 1 engine ... keeps the Switch 2 engine from starting"), from the Dart status check and now from the
  native refusal too, which answered `engineRestartRequired` before.
- The failure dialog shows `S2Arm: <code>` and the native diagnostic under "Technical details", so the code (formerly
  `melonxCoreLoaded`, message key `melonxLoaded`) and the diagnostic name the console, not the engine. Logs, the native
  journal and the status map may still name MeloNX: they are diagnostics, not player surfaces.
- The Switch 2 playlist menu (`docs/s2arm-switch2-library.md`) no longer offers prod.keys: S2Arm needs none, and it stays
  in the Switch 1 playlist.

Checked by `test/s2arm_engine_bridge_test.py` (139 checks: the native refusal has its own code; no error code or
diagnostic literal names MeloNX), `test/s2arm_internal_service_test.dart` (each message names one console and the two
differ; the native code reaches its message and its technical details name no engine),
`test/s2arm_playlist_menu_contract_test.dart` and `test/switch2_empty_hint_contract_test.py`.
Not observed on a device.

### Real progress during the preparation (12 Nov 2026)

The maintainer asked for a real progress bar: on IPA 728 the dialog showed "code · 0%" for minutes on Mario Kart World.
`4454bf54` (next IPA) only reported each part of the code stage, so the main module stayed one block.

- **Rewriter.** `build-utils/s2arm/prepare/patches/0001-rewriter-progress-report.patch` adds a per-thread callback,
  `s2a_rewrite_set_progress`, to S2Arm's `runtime/rewriter`. It reports the attempt number and each pass: load,
  prepass, boundaries, scan, data, analyze, generate, late, spins and outputs. Inside the long loops it adds counts:
  every 256 KiB of text for boundaries, scan and spins, every function for analyze, every 256 units for generate.
  - It only adds lines (67, none removed), and the code it adds reads only loop counters.
    `test/s2arm_rewriter_progress_test.py` (68 checks) refuses any added line that is not a report. It also refuses
    any assignment outside `rb_*`. Four bad variants of the patch fail it.
  - `s2arm-prepare.yml` builds the reference `s2a-rewrite` from the unpatched checkout and our library from a
    patched copy. Every existing comparison (rewrite, whole code stage, per-game files) therefore checks that the
    patched rewriter writes the same bytes.
  - `s2arm-core.yml` applies the series before it builds `S2ArmPrepare.xcframework` and records it in the identity
    (`patches`). Listed in `docs/s2arm-legal-notices.md`.
- **Code stage.** `rb_s2arm_code_request.work` (new last member; the pod's copy in `S2ArmPrepareABI.h` is checked
  member by member, in order) reports `part`, `phase`, `attempt`, `done`/`total` and one `fraction` for the whole code
  stage. That fraction never goes back.
  - Weights: a module's rewrite counts for its size, and the address-need table for 5 % of main.
  - Each RomFS walk counts for 1 % of the modules and reports its entries (`rb_s2arm_nro_to_nso_ex`,
    `rb_s2arm_nro_exports_ex`).
  - The ZBIC decoding of the ExeFS takes the first 5 %.
  - Inside a module the passes take fixed shares: analyze 40 %, generate 25 %, the rest 35 %.
  - A new layout (attempt 2 and later) continues from where the bar is.
  - The test CLI checks every event: in [0, 1], never back, ending at 1. `run_code_stage_test.py` reports it per case.
- **Bridge.** `prep_code_work` sends the fraction with `phase`, `attempt`, `done` and `total`. The step callback
  only writes `codeStep` to the journal, so two fractions of different meaning never alternate. Each phase is
  journaled (`codePhase`, with its duration and counts), so the pass shares can follow measured costs after the
  next device run.
- **Dialog.** One bar for the whole preparation. Its weights are unpack 4 %, code 80 %, caps 2 %, direct 2 %,
  module 6 % and pack 6 % (`S2ArmInternalService.preparationOverall`). Above the bar, the step and its part, then
  the phase and its counts: "Compilation du code du jeu · module principal · passe 2", then "Analyse des
  fonctions · 1234 / 5678 fonctions". Below it, the percentage and the elapsed time, which moves every second even
  when a pass reports nothing. The 26 new strings come in 12 languages (`prep*` keys of
  `lib/l10n/switch2_library_locale.dart`). Tests: `test/s2arm_prepare_dialog_test.dart` and
  `test/s2arm_internal_service_test.dart`.
- Limits: the pass shares are estimates until the journal of a real run gives the durations. Nothing has been
  observed on a device. The new library needs a new `prepare` pin (`build-utils/s2arm/engine-pin.json`); the engine
  and the system data are unchanged.

## Preparation speed (Mario Kart World, IPA 731 timings)

The S2Arm journal and app.log of IPA 731 give 427 s for a full preparation:

| Step | Time | Where it went |
| --- | --- | --- |
| clearing | 14 s | deleting the previous root, whose RomFS view of a delta update holds one link per file |
| unpack | 119 s | a `mkdir` for every path component from `/` before each of about 205 000 links, plus walks with a `stat` per entry |
| code | 60 s | two RomFS walks of 29 s each (NRO conversion, NRO exports), with an `lstat` and a `stat` per entry; the modules took 3 s |
| caps | 29 s | a third RomFS walk, for an engine rule that cannot match (main names neither Unity nor Unreal) |
| pack | 204 s | SHA-256 of the whole RomFS (22 GB) in portable C on one thread, about 110 MB/s |

What changed (outputs are the same byte for byte; CI compares them with S2Arm's tools on Linux and macOS):

- SHA-256 comes from CommonCrypto on Apple systems (`s2arm_sha256.c`), which uses the CPU's SHA-256 instructions.
- The resource pack hashes the RomFS and DLC files with up to four threads. Each thread has one 4 MiB buffer. The
  calling thread reports progress every 100 ms, and cancel is polled between chunks (`hash_linked` in `s2arm_pack.c`).
  Errors come out as they did with one thread. A failure stops the files after it, the files before it finish, and the
  earliest file's failure is the one reported.
- `makedirs` (ns2_dump) tries the path itself first and goes up only when a parent is missing. The in-place view
  remembers the directory of the previous link and makes the link before any `unlink`.
- The walks take the entry type from `readdir` (`s2arm_dirent.h`). They `stat` only links and entries of unknown type.
  The NRO walk stats only links named `*.nro`, and the pack walk stats files with `fstatat` relative to their directory.
- The caps engine rule skips the RomFS walk when main names neither Unity nor Unreal: the walk could only turn the
  answer to False, and it is already False.
- One difference from the old C walks remains, and the review accepted it. A folder that can be listed but not
  searched (read without execute permission) is now walked from its listing, as Python's `os.walk` does through
  `scandir`. Before, a stat of each entry failed. An export imported by the app has no such folder.
- The bridge moves the previous root aside (one `rename`) and deletes it at background QoS once the preparation has
  ended. Only `.discarded-*` entries are deleted there. The root holds about 150 MB until then.
- The journal adds `cleared`, `unpackLayout` / `unpackUpdates` / `unpackDone`, `packWalk` and `packDone` lines. They
  carry counts, fixed words and durations only. With them, the next device run shows where the remaining time goes.

Local check (scratch harness, Linux, not the phone): the old and new libraries gave identical outputs and errors on 17
case and mode combinations, including delta overlays, links to files and to folders, a dangling link, a FIFO, Unity, and
Unreal with `.pak`. ThreadSanitizer reported nothing on a full pack or on early and late cancels. On a 60 000-file delta
tree with a warm cache: unpack 1.42 → 0.85 s, caps 0.25 → 0.00 s, NRO walk 0.25 → 0.04 s, pack 0.95 → 0.46 s.
The phone's times are not measured yet. Its `stat` costs about 140 µs per RomFS entry in a walk, far more than on
this machine. The progress bar's step weights (unpack 4 %, code 80 %, pack 6 %...) still follow the old guesses, to
be set from the next journal.
