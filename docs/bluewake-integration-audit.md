# Wind Waker / BlueWake integration audit

Date: 2026-10-13. Status: **audit complete; native integration blocked before the iOS build**.

## Decision

Use maintained [BlueWake](https://github.com/chrissotraidis/bluewake), not the retired Wind-Waker-Recomp release path. Pin the candidate to `6248171f3ef6094d179d45385b522d6bc8f49248`. This is an audited source candidate, not an iPhone-tested NeoStation engine.

A personal integration is technically plausible. The requested public-IPA workflow “install NeoStation, import an ISO, play this native port” is **not supplied by this architecture**. BlueWake needs both its host/runtime and an ARM64 module translated from the player's disc before the application is signed. Importing a disc on iOS prepares data; it does not translate or compile that module.

No Wind Waker entry, import option, native framework, build workflow, or gameplay support is enabled by this change.

## Branch and preserved work

GitHub had no `Cloud` branch when checked. Following the maintainer's explicit instruction for this task, `Cloud` was created from the current `Claude` head, `5866bc658e26861c9f0d44ea8b32da33b885bbc4` (tree `56233b164a0218705e60dcc0ce2bd1cbaa83d6ba`). This preserves Build 455 and subsequent documentation changes. The existing `Claude`, `main`, `backup` and local workspaces were not modified.

The older Claude-only instruction in AGENTS.md is superseded **for this task** by the maintainer's explicit Cloud request. This audit does not establish a new policy for unrelated work.

## Source and dependency identities

[Machine-readable audit pins](bluewake-source-lock.json) record the full identities.

| Input | Audited identity |
| --- | --- |
| BlueWake | `6248171f3ef6094d179d45385b522d6bc8f49248` |
| Wind-Waker-Recomp, inspected only | `adac1e616376ab0d7d57eda51d82acf4dc607079` |
| RecompCore / GXRuntime / vendored Aurora | `ee99bbc13c948351f6974c745cad2593a25eacbf` |
| DolRecomp | `b8b534591cba8ca7cd43943a655ee6e2591cf5de` |
| SDL 3.4.10 tag resolved to commit | `8e37db5e797b6167f3a00d697d816a684bd259c7` |
| Dawn iOS ARM64 archive | `v20260618.032059`, SHA-256 `ada0bafc173152d80eba7c3b2f9609a71185d5809cbd5dd3251b91a0803a7ae2` |

The builder's runtime and translator pins match `config/dependencies.lock.json`. SDL is pinned by a tag in the upstream CMake file; the commit above records the tag resolution for a future reproducible build. The Dawn digest is recorded from upstream configuration; the archive was not downloaded or independently hashed in this audit.

The migration is established by the original fork's README and BlueWake's [migration status](https://github.com/chrissotraidis/bluewake/blob/6248171f3ef6094d179d45385b522d6bc8f49248/docs/MIGRATION_STATUS.md). Imported work includes Elliott's Windows/runtime changes; some newer work remains pending upstream. Do not mix the fork's older Apple host with BlueWake's current runtime.

## Build, signing and distribution

The [builder](https://github.com/chrissotraidis/bluewake/blob/6248171f3ef6094d179d45385b522d6bc8f49248/scripts/builder/build.sh) and its [profile](https://github.com/chrissotraidis/bluewake/blob/6248171f3ef6094d179d45385b522d6bc8f49248/scripts/builder/profiles/bluewake.sh) implement these separate steps:

1. On an Apple Silicon Mac with Xcode/iPhoneOS SDK, CMake and Ninja, validate the personal GZLE01 disc, extract `main.dol` and exactly 415 REL files, translate them with DolRecomp, verify the generated-source digest, prepare supported options and train a local optimization profile.
2. Compile the generated C into `gGZLE01_recomp.dylib` for iOS ARM64. Separately compile the host, RecompCore/GXRuntime, Aurora/Dawn/Metal, SDL3 and the Dolphin-derived DSP components.
3. Embed the personal module in `Frameworks`, sign the nested code and app consistently, then install the personal package. No JIT is required for this AOT route.
4. On iPhone, import the same supported disc and extract the runtime DOL/REL inputs. Textures/audio/world data remain on the disc. This operation cannot fill in a missing native module.

The upstream `--app-only` path can build a shell without any disc or translated game code. The shell deliberately cannot play until a personal module is added. Its existence does not prove a callable NeoStation framework exists.

[Apple documents](https://support.apple.com/guide/security/app-code-signing-process-sec7c917bf14/web) code-signature checks for dynamic libraries and matching Team IDs. The integration route should embed and sign the module before installation. The upstream Documents-directory fallback is merely a file lookup; it does not sign code. Sideloading or enabling Developer Mode does not turn an imported ISO into signed native code.

The proposed solution is a **local personal packaging step**, similar to PadMint: take the public NeoStation shell plus compatible BlueWake runtime, compile the player's module from their disc, assemble and sign the personal NeoStation IPA, then import the disc on the phone. This requires a NeoStation-specific packaging adapter; the current BlueWake `--app` route is not evidence that an arbitrary NeoStation IPA is compatible.

The upstream [rights notice](https://github.com/chrissotraidis/bluewake/blob/6248171f3ef6094d179d45385b522d6bc8f49248/RIGHTS_AND_LICENSES.md) distinguishes GPL-covered software from game-derived code and asks that Apple personal builds not be shared. Public source/host releases must exclude discs, extracted DOL/REL files, translated C, personal modules, game profiles, cards, saves and keys. Windows/Linux release exceptions are not an Apple distribution permission. These are the project's stated boundaries, not a legal determination about the player's jurisdiction.

## Native embedding changes required

The [iOS CMake target](https://github.com/chrissotraidis/bluewake/blob/6248171f3ef6094d179d45385b522d6bc8f49248/apple/ios/CMakeLists.txt) builds a standalone executable. It is not a reusable engine API.

| Area | Source finding and required adaptation |
| --- | --- |
| UIKit / SDL ownership | `ios_entry.m` uses SDL's application entry point. NeoStation already owns UIKit. Build a private callable framework, omit that entry point and attach only a game-owned view/window. Existing Dusklight embedding demonstrates `SDL_MAIN_HANDLED`, `SDL_SetMainReady` and `SDL_SetiOSEventPump(false)`. |
| Symbols and Objective-C classes | BlueWake includes SDL3, Aurora and Dolphin-derived DSP/Common code. Dusklight already privately renames SDL Objective-C classes in `native/dusklight/core/SDLClassNames.cmake`. Use a separate BlueWake prefix, an explicit export list and private symbols; `RTLD_LOCAL` alone does not isolate Objective-C's process-wide class registry. Actual binary collisions remain untested. |
| Rendering | Use the pinned GXRuntime/Aurora/Dawn Metal path. NeoStation's Dolphin core is not a substitute. Stop and join rendering workers before destroying the owned Metal surface; verify alternation with Dolphin and the existing ports. |
| Audio and input | Coordinate SDL/DSP output with NeoStation's process-wide AVAudioSession and menu music. Remove observers, release held inputs/controller callbacks and stop output on every exit. The upstream overlay uses SDL window lookup and audio-interruption observers; neither can be copied unchanged into a multi-engine host. |
| Stop and relaunch | `ios_entry.m` calls `_exit(status)` after the host returns. That path would terminate NeoStation. The host has shutdown routines, but also persistent globals and `atexit` registrations; their reset and failure paths must be audited before claiming restartability. Removing `_exit` alone is insufficient. |
| Session contract | Follow the versioned C ABI and transaction/event approach of `KartPadCoreABI.h`, the native bridge and `GameLaunchManager`. Distinguish starting/running/stopping/ended, ignore stale callbacks, acknowledge stop only after cleanup and return to the existing Ports selection. |
| Saves | Allocate a dedicated persistent BlueWake save/config root outside the bundle and caches. The upstream card is `GZLE01.card`; preserve it and SRAM across updates. A failed import, cancellation or runtime rebuild must not replace saves. Savestates are separately version-sensitive. |

## Importer findings — audit only

The actual iOS [importer](https://github.com/chrissotraidis/bluewake/blob/6248171f3ef6094d179d45385b522d6bc8f49248/apple/ios/src/disc_import.c) accepts **uncompressed ISO/GCM content**, not RVZ, GCZ, WIA, CISO, ZIP or 7z. The broad extensions in NeoStation's Ports system describe all existing ports and must not become BlueWake's acceptance list.

Confirmed validation details:

- `bluewake_disc_check` checks GameCube magic and GZLE01, but does not independently enforce the revision header byte.
- `bluewake_disc_prepare` verifies the extracted DOL SHA-1: `8d28bab68bb5078c38e43f29206f0bd01f7e7a67`. This verifies the supported executable, not every byte of the disc.
- Runtime preparation accepts at least 400 module writes, whereas the builder requires exactly 415 REL files. A stricter integration must verify the expected unique module set and its compatibility with the built module.
- The C progress callback returns void and provides no cancellation contract.
- iOS first-run code replaces the old disc before full preparation; preparation removes old outputs before the final rename sequence. This is not rollback-safe replacement. Do not inherit it unchanged.
- Fixed 1024-byte output path buffers produce GCC truncation warnings.

Once the native build gate passes, reuse `PortsInternalPlaylistActions` and the existing Files picker. Add a BlueWake target with a streamed, cancellable validation/extraction job and structured error keys; wrap it in `StorageImportActivity`. Use per-job staging, bounded reads, content fingerprints, compatibility checks and atomic publication with rollback. Preserve the source and previous installation on rejection/cancellation. Clean only verified picker-owned temporary copies via the existing storage rules. A matching fingerprint should reuse the installation, not create another disc copy. Hashing for duplicate detection alone is not proof of a known-good full disc.

## Library and metadata integration points

- `PortsInternalPlaylistActions` already has the Import button for Dusklight and KartPad, calls `onLibraryChanged` and launches `onGamesImported` enrichment asynchronously.
- `refreshPortsInternalLibrary` and `scanRomsForSystem` in `lib/providers/sqlite_config_provider/scanning.dart` enumerate only the existing ports' roots. A new root/identity needs an explicit route.
- Extend `PortGameIdentity` with GZLE01 and a distinct display title. Reuse the GameCube ScreenScraper identity (system 13, already used by the existing source-platform mapper), existing media resolver/downloader and game metadata records. Resolve cover, fanart, video and description only when available; install a usable offline title first. Scraping currently requires saved provider credentials.
- `user_roms` enforces `UNIQUE(rom_path)`: two engines cannot simply insert the same absolute ISO path as two records. To share one physical disc with a Dolphin entry, use a distinct lightweight port launch record/manifest that refers to it, with explicit scanner/launcher/scraper/deletion support. Do not silently rewrite the GameCube record or introduce a broad database migration.
- Ports currently dispatches KartPad-owned paths explicitly and then falls through to Dusklight. Add an explicit BlueWake owner/engine route before that fallback; never dispatch merely because the title says Wind Waker.
- Reuse `PortsLocale` and the native text bridge for every new string: `en, es, ru, zh, zh_Hant, pt, fr, de, it, id, ja, ko`. Validate keys, placeholders and Traditional Chinese selection. No new UI strings are introduced by this audit.

## Checks actually performed

| Check | Result |
| --- | --- |
| Source inspection | Pinned GitHub files read; 51 retrieved source files verified byte-for-byte against their Git blob hashes before native probes. Further library schema/scanner files were also inspected. |
| Dependency consistency | RecompCore and DolRecomp builder pins match the dependency lock; SDL release tag resolved to the recorded commit. |
| Builder shell syntax | `bash -n` passed for `build.sh` and `profiles/bluewake.sh`. |
| Portable importer compile | Actual upstream `disc_extract.c` + `disc_import.c` compiled with GCC 13.3.0 on Linux x86_64, AddressSanitizer and UndefinedBehaviorSanitizer. Two path-truncation warnings; compile succeeded. |
| Invalid-input behavior | **9/9 passed**: missing file, truncated header, synthetic RVZ, another game, European ID, revision-1 header with invalid DOL, out-of-file DOL offset, oversized DOL and spoofed revision-0 header with invalid DOL. Each was refused; input and pre-existing sentinel outputs were preserved. No sanitizer finding in these cases. This does not exercise a valid-disc success or late publication failure. |
| Apple builder attempt | Unmodified `build.sh --app-only --ipa …` exited 1 immediately at `sysctl -n hw.ncpu` on Linux. Xcode/xcrun/Apple Clang/CMake/Ninja are absent in that environment. The connected workstation was confirmed as Windows with no xcodebuild/xcrun. No iOS compile or link was performed. |
| Upstream CI, observed only | Four completed successful checks at the BlueWake pin: host, Ubuntu host/AppImage, audit and attribution. Not executed by this audit and not NeoStation/iPhone acceptance. |
| Personal game inputs | No disc or personal ARM64 module was provided or located for this task. No game data was uploaded, generated or published. |

Portable reproduction from the pinned upstream checkout:

```sh
gcc -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
  scripts/ios/disc_extract.c apple/ios/src/disc_import.c \
  -Iapple/ios/src -o /tmp/bluewake-disc-extract
bash -n scripts/builder/build.sh scripts/builder/profiles/bluewake.sh
```

## Remaining gate and acceptance

The next required inputs are an accessible Apple Silicon Mac with Xcode, the player's supported disc kept on that machine, and adoption of the personal packaging workflow above. A public ISO-only experience would require a materially different upstream execution/distribution architecture; silently switching to Dolphin would not satisfy the native-port request.

First compile the pinned standalone host and personal module locally, then make and validate a callable NeoStation framework and its signatures. Only after that gate should the import/library UI be enabled.

**Not performed:** valid-disc import; on-device detection/card display; native launch; controller/touch/audio checks; save/reload; close/relaunch; iCloud/cancellation/low-storage recovery; alternating engines; application update with retained saves; twelve-language UI testing. The eventual acceptance matrix must cover all of these, including repeated relaunches and the absence of lingering audio or a false running state.

Credits to retain when vendoring: Chris Sotraidis, Elliott Tate and BlueWake contributors; RecompCore/DolRecomp and Dolphin contributors; SunPad touch controls; Aurora, Dawn and SDL; applicable mod/research and per-file notices. No claim that BlueWake ships in NeoStation is made.
