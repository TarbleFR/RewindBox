# MeloNX launch investigation — 23 October 2026

## Evidence from the supplied cumulative app journal

The entire `app(5).log` (4,271,413 bytes, 44,842 lines) was read. Its 470
logger-initialization boundaries were separated. The final section starts at
line 44,705; the imported NSP appears as one Switch game at 44,766. Two rejected
launches end at 13:48:57 and 13:49:05 UTC on 23 October. The historical HeaderKey
and key_area_key_application_16 errors occur before this section, not in these
attempts. There is no evidence establishing their exact native failure cause.
The dialog-disposal warning follows the reported refusal and is not itself
evidence of the original failure. The SQLite uniqueness errors concern old
ROM-folder preferences; the Switch dispatch uses the game's own local path.

Import already commits a verified-length permanent copy and records that path
before deleting document-picker copies. The 6,172,971,680 removed bytes are
temporary copies. This investigation does not delete or reimport personal files,
change the playlist, alter saves or repair database rows automatically.

## Proven defects addressed

- Dart did not persist MeloNX's launch refusal details in the app journal.
- Swift discarded the native metadata result before continuing toward a game.
- Successful icon/metadata reads did not validate the executable NCA sections.
- An unsuccessful NSP content load could fall through into the ExeFS loader and
  replace the original CNMT/NCA error with an unrelated second error.
- The embedded host omitted the standalone host's explicit dual-mapping setup.
  It now initializes the actual engine code cache and signal mapping, executes
  an ARM64 probe through its real aliases and completes the selected helper's
  detach before creating guest threads. Its reserved probe cannot overwrite
  translated guest code on a second launch.
- Real NativeAOT execution reproduced a separate deterministic failure:
  `System.IO.FileNotFoundException` from `Silk.NET.Vulkan.Vk.CreateDefaultContext`
  during `MoltenVKWindow` construction (run 39970253306). The standalone Main
  installs `MVKInitialization.InitializeResolver`; embedded initialization did
  not call it. The private framework was loaded, but Silk's Vulkan aliases could
  not resolve it. Embedded bootstrap now installs that resolver before the first
  `Vk.GetApi`, and all supported Darwin Vulkan aliases resolve to the private
  source-built MeloNX framework. This is a proven startup blocker; the missing
  device-stage logs still prevent assigning it as the exact first refusal on the
  maintainer's two latest attempts.

An additive diagnostic ABI carries a bounded, redacted native stage journal.
Its Swift/Flutter bridge writes into the normal app journal, including GPU,
session return and real Metal-presentation events. Startup success still requires
both an observed CAMetalDrawable presentation and actual JIT confirmation.
The engine's existing quarantine and lifetime protections remain in place.
Rejected preflight attempts remain retryable; an unproven native shutdown does
not free its resources. Repeated stop requests do not repeat native teardown.

## Validation and remaining device work

Local production preflight/LibHac/journal fixtures: 13 assertions passed.
Production Dart service with controlled native responses: nine scenarios passed.
Affected audio finalization: five scenarios passed, including 100 original
return cycles and new rejected/quarantined initialization checks. These are host
and channel tests, not iPhone gameplay.

The engine workflow builds iOS ARM64 and ARM64 Simulator. Its real-runtime smoke
tests missing personal keys and attempts two sessions of an original unencrypted
ARM64 homebrew that executes SVC ExitProcess. This program produces no video;
even successful CPU/session proof does not establish a first game image.
Exact CI, bundle validation and delivery results are recorded in the delivery
receipt after the jobs finish, including failures where applicable.

No connected iPhone, personal game, personal keys or personal firmware is
available to this environment. Installed-signature entitlements, StikJIT or
LocalDevVPN authorization on that phone, compatibility of the user's selected
game/revision, its first image, audio and controller operation remain physical
device checks. No personal files are requested, generated or bundled.

Build 514 preserves the concurrently prepared RPCS3 513 Core, all other engine
pins, Switch import/storage, Motion, Liquid Glass, AirPlay, covers and catalogues.
The prepared IPA uses ad hoc signatures; SideStore/AltStore must apply the user's
Apple signing/provisioning. Declared entitlements and the capabilities actually
granted to the installed process are separate checks. No release, tag or main
update is authorized or performed.
