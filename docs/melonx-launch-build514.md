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

After correcting Vulkan resolution, the actual native homebrew load stalled
inside the fault handler (runs 39972715534 and 39974803384). The thread sample
shows the loader within `_sigtramp`; the native journal reaches content load.
Pinned upstream uses Linux's 128-byte signal mask and flag `4` for sigaction on
Darwin. Apple's SDK uses a 4-byte mask, flags at byte 12 and SA_SIGINFO `0x40`.
The embedded adapter now registers the exact Darwin ABI, preserves each prior
SIGSEGV/SIGBUS disposition and its one/three-argument convention, and uses the
matching generated handler offsets. Non-guest faults still chain to NativeAOT;
SIG_DFL/SIG_IGN are treated as dispositions rather than function addresses.
Registration is checked against the actual iOS SDK and live Darwin signals;
the real ARM64 app also checks both installed SA_SIGINFO flags before a guest.
Any original loader exception is recorded before resource teardown, and actual
Horizon-service readiness is distinguished from creating service objects.

The exact alpha.129 LibHac also reproduced a NullReferenceException in
`Nro.OpenNroAssetSection` for a legitimate executable without optional ASET.
The HLE loader called it unconditionally. The embedded loader now checks the
optional AssetHeader before opening RomFS/NACP, retaining present assets and
propagating malformed present content errors. Ten checks execute the production
NRO executable and new asset helper against the pinned real LibHac for absent,
empty and present assets. The original homebrew fixture remains unchanged;
this fixes the loader instead of adding assets just to avoid the failure.

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

Actual Core run [39978893582](https://github.com/TarbleFR/RewindBox/actions/runs/39978893582)
passed for source `e050961d6caabfabdef57dd140c774545976d0fd`. Both device ARM64
and Simulator ARM64 NativeAOT images compiled with 39 exported ABI functions.
The ARM64 Simulator app verified the real JIT arena and installed Darwin
SA_SIGINFO handlers, executed the original homebrew's SVC ExitProcess twice and
returned both sessions to idle. MoltenVK created the real simulator Vulkan/Metal
device and swapchain, then released them. First-run GPU initialization took
about 16 seconds; teardown waited for that worker instead of freeing it early.
No game image is claimed: this original program has no video output. The
firmware-free test logged an absent TimeZoneBinary archive; it did not block this
homebrew and is not evidence about the user's installed firmware. The report's
`jitTested: false` retains its physical-helper limitation; its separately named
`actualSimulatorCodeArenaVerified` and `originalHomebrewGuestSvcConfirmed` are true.

The IPA is frozen at `22df4502db21ee1bcd68e15c1791aeba1a826658`, retaining RPCS3
Core 513. A later independent RPCS3 push (`a6986029`) remains on Claude and is not
silently mixed into this already-tested candidate. The first delivery attempt
passed final signature, bundle, ABI and memory-entitlement checks, then a skipped
concurrent workflow cancelled it during compilation-cache preparation before
upload. The delivery concurrency rule is now isolated and future IPA uploads
precede cache work. Recovery reruns the original job on its original tested
source; it does not rebuild the validated MeloNX engine or replay Flutter tests.
Final download identity and independent verification follow in the delivery receipt.

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

## Delivered candidate

[GitHub Actions attempt 2](https://github.com/TarbleFR/RewindBox/actions/runs/39979130143/attempts/2)
completed successfully. Artifact `12515825796` was downloaded, its encrypted ZIP
SHA-256 checked, and its IPA decrypted and independently verified against source
`22df4502db21ee1bcd68e15c1791aeba1a826658`. The 186,162,249-byte IPA is
`92e3ed7938db64b6bc96146a06cdfdb85811062b71663e39d3f746c13a4a2564`.
All six private MeloNX frameworks and 39 NativeAOT exports are present. Signature
checks passed for all bundled executable images; compiled code/data and ABI
fingerprints stayed unchanged through signing. Both required memory entitlements
are declared. Apple re-signing and the installed phone's actual granted
entitlements are separate, unverified steps. No Nintendo content, keys or firmware
is bundled. The one-off investigation/cancellation/recovery workflows were retired
after delivery; the permanent launch checks and corrected delivery rules remain.

The [delivery receipt](evidence/melonx-launch514-delivery.json) contains the exact
component runs, hashes, tests, initial failure distinction, recovered delivery and
physical-device limitations. No release, tag or main modification was made.
