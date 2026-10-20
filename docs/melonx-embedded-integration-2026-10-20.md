# MeloNX embedded integration — work in progress

The maintainer requests an in-process Nintendo Switch engine, its independent
playlist and imports, firmware/keys, original touch controls with editable
layouts, controllers, compatible HD content and a test IPA. The subsequent
instruction explicitly retires the external MeloNX entry. Work stays on Claude;
there is no authorization for a public release.

## Continuation: source-built dependency and embedded bootstrap

The original NuGet feed is still missing alpha.129. The matching source change
has now been found in the Starforge mirror of `projects/LibHac`:
`23e402ebb6dedc517e34a98a033078dc0f6fd478` (25 February, 19:48:57 UTC).
Ten minutes later the consumer commit
`cc6d2dc162ca00a3db9af09f176798a8297926ab` adopts alpha.129 instead of alpha.126
with the same NACP language-buffer correction. This identifies corresponding
source by the upstream change history; it does **not** recover the original
package bytes or prove equality with the original published NuGet binary.

Run `39504259828`, host source `56aeec6722a93f07bbdc05a4576e71cebc93702b`,
successfully runs the upstream generators, compiles LibHac, passes all **five**
`LibHac.Tests.Ns.TypeLayoutTests`, builds its local NuGet package and restores
every MeloNX dependency. The reconstructed package SHA-256 is
`b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9`.
Artifact `12302912762` retains that package, generated sources, upstream source
archive and source receipt. The **whole run fails**, subsequently, at
NETSDK1112: the NativeAOT iOS runtime pack was not downloaded during restore.
There is still no engine dylib from this run.

The next build reuses that exact package and its successful layout tests after
checking the source pin, package/archive hashes, job source and test log. It
aligns restore with publish (`Release`, `SelfContained=true`, `ios-arm64`).
No unchanged Flutter or emulator checks are rerun.

The first actual embedded engine adaptation is now in `native/melonx`:

- A caller-owned UTF-8 root and explicit bootstrap ABI; no foreign allocation
  ownership is transferred across this boundary.
- Only the current `Documents/MeloNX` root is accepted. Documents itself,
  other engine directories, relative paths and a symbolic-link root are refused.
- The engine's iOS data manager now respects its supplied root. The existing
  standalone initializer still supplies Documents and retains its old behavior.
- Initialization is serialized and idempotent. A failure after entering engine
  initialization prevents another attempt over partially created native handles.
- The bootstrap ABI is **not** an availability/session-ready report. No native
  game session is registered or enabled in the app by this step.

The executable bootstrap checks and the adapted NativeAOT build are pending.
The existing retirement validations below remain historical, unchanged results.

Source references:
<https://starforgejo.dev/archive/LibHac_Ryubing/commit/23e402ebb6dedc517e34a98a033078dc0f6fd478>
and
<https://starforgejo.dev/projects/MeloNX/commit/cc6d2dc162ca00a3db9af09f176798a8297926ab>.

## Source audit

The inspected engine is `projects/MeloNX` at
`13700519f3abc4e6d7ed8a065b118b2cc59bcd67` on
<https://starforgejo.dev/projects/MeloNX>. Its iOS frontend is Swift/SwiftUI;
`src/Ryujinx.Library` compiles a .NET 10 NativeAOT ARM64 dynamic library.
It exposes native window, game start/stop, input, firmware and game-info APIs.
The renderer uses Vulkan through MoltenVK with a CAMetalLayer. The .NET runtime
being AOT-compiled does not remove the guest CPU's JIT requirement.

Relevant source boundaries:

| Concern | Inspected source | Integration consequence |
| --- | --- | --- |
| Core ABI | `src/Ryujinx.Library/Library.cs`, `UnmanagedPassthrough.cs` | Preserve exact struct layout, allocator ownership and callback lifetime. |
| Storage | `Library.Initialize`, Swift `RyujinxController` URL helpers | Upstream starts at Documents. Confine embedded state to Documents/MeloNX before initialization. |
| Session lifetime | `Library.Load`, `StopEmulation`, `WindowBase.Exit` | Input manager disposal and synchronous stop need a dedicated relaunch proof before enabling the engine. |
| Original touch controls | Melo-Controller revision `c049ce88a5635bddcd88e1965c42aa8fc92fe961` | Retain original controls; do not substitute generic buttons and call them original. Evaluate the common NeoStation editor adapter. |
| GPU dependencies | committed SDL3, MoltenVK and codec libraries | Confirm binary/source/license provenance and coexistence with the delivered engines before packaging. |
| JIT | dual mapping and the upstream universal protocol | Verify the NeoStation PID and mapping handshake; do not repurpose a helper that also initializes another core. |
| NeoSwap | donated-memory exports and upstream RamDonor | Use one ownership/budget contract; do not run two independent donor managers or claim virtual space as RAM. |
| Mods | README and per-title mod-loading code | DLC/updates are supported upstream. RomFS/ExeFS/runtime mods are not guaranteed. No Switch HD download is enabled by this work. |

## Licenses observed

The engine root `LICENSE.txt` contains the Ryujinx MIT notice, while the README
also describes MeloNX as GPLv3. Preserve both facts in the audit; do not silently
relabel the complete engine. The separately pinned Melo-Controller package has
a GPLv3 license. Upstream also names BSD libvpx and LGPLv3 FFmpeg. A root license
alone is insufficient evidence for all committed native dependency binaries.
No engine/dependency binary, firmware, key, commercial game, or texture pack has
been added to NeoStation by this phase.

## External integration retired

- Removed the external library exporter/cache loader and URL callback, launch
  Shortcut installer, external StikJIT target discovery and foreground handoff.
- Removed the settings synchronization card. Switch has an embedded-only seed
  and route; it never falls through to RetroArch, a URL or a share sheet.
- Existing `melonx://` metadata rows are retained. Launch asks the user to import
  the actual game file; it never guesses a local game from a title. Existing
  personal files, saves, artwork, playtime and cached exports are not deleted.
- The shared StikJIT pod retains the read-only LocalDevVPN route probe and the
  same source-built framework ABI. The three other engines' dedicated helper
  sources and scripts are unchanged. The previous dynamic FFI export list is
  retained in frozen source snapshots excluded from CocoaPods compilation. This
  preserves the existing framework/source fingerprint and avoids rebuilding JIT;
  the snapshots provide no registered or compiled external launcher.
- Packaging removes and rejects the retired `melonx`/`atariemulator` query
  schemes. Switch engine availability requires a native runtime report; a Dart
  route declaration is not treated as an installed engine.
- Failure and reimport messages are translated in all twelve languages. Switch
  session monitoring retains frontend audio ownership until native teardown
  explicitly reports false.

## Engine build attempts

`build-utils/melonx/source.json` pins the engine, controller and SDK. The focused
`melonx-core.yml` lane builds no other emulator and creates no release.

1. Run `39498866032`: source fetched and SDK installed; NativeAOT publish stopped
   at NETSDK1147 (mobile-librarybuilder missing). No binary produced.
2. Run `39499119399`: pin SDK resolution to 10.0.100 and install the workload;
   restore stopped at NU1101 for exact `Ryujinx.LibHac` 0.21.0-alpha.129 in the
   upstream-declared Ryulynx feed. No binary produced. Nuget.org only lists older
   versions; no API downgrade was substituted.
3. Run `39499844255`: try the original Ryujinx projects feed retained by the
   inspected MeloNX mirror `f925129209afd55927a0201d82285b8fa4b7ba30`, preserving
   the exact package version and source mapping. Failed before compilation:
   NU1301, `Network is unreachable (git.ryujinx.app:443)`.
4. Run `39502094518`: check that original `projects` namespace on the current
   official Starforge host. Workload installation succeeds; bounded restore
   again reports NU1101, no `Ryujinx.LibHac` in that feed. No binary produced.

The builder retains the upstream-declared Ryulynx feed and exact alpha.129
dependency; it does not retain the guessed projects namespace as its default.
Restore now has a 240-second bound. The source linked by MeloNX for LibHac,
<https://github.com/Thealexbarney/LibHac>, also returns 404 when checked.
Continuing the engine build requires the exact package or its matching source.
Using an older API or extracting an unverified binary is not a completed port:
the storage, session lifetime, dependency isolation and JIT adaptations still
require implementation and testing.

## Validation and remaining work

Local checks passed: protected library/native baseline (3 tests), bounded
LocalDevVPN route contract (5), embedded routing contract, unchanged dedicated
JIT source/patch fingerprints, and packaging parser tests (25, including refusal
of each retired query scheme). These are source/parser checks, not gameplay.
Focused CI evidence:

- Run `39500644479`, source `127b527f`: app analysis passed, 68 Flutter tests
  passed and three failed. Retained failures are the old Switch-external
  expectation, a now-unused external failure locale key, and an already-stale
  RetroArch method-name assertion. The failures were corrected rather than
  removed: Switch is embedded-only but unavailable without its runtime; the
  retired key is removed from all twelve languages; the route test names
  `launchGameWithDiagnostics`, which was already the actual unchanged method.
- Run `39501621994`, source `faa28104`, job `118900258241`: final full app
  analysis and all **35** focused Flutter tests passed. Baseline (3), VPN (5),
  packaging (25), routing and unchanged JIT-source contracts also passed. The
  final SDK step failed because its framework search path omitted the
  `Flutter.xcframework/ios-arm64` slice. This is a harness-path failure, not an
  observed engine or iPhone failure. Do not describe this whole run as passed.
- Run `39502499716`, source `e214cf59`, native job `118903228338`: the actual
  registered Swift plugin and route probe **passed the iPhone SDK type-check**
  using the real pinned Flutter device framework. The selected pod source set
  is checked to contain exactly those two Swift files, excluding both frozen
  external-launch snapshots. Three successful phases from `faa28104` are reused
  only after comparing their complete app/test inputs; they are not re-run.
  Receipts are uploaded as `MeloNX-retirement-proof-e214cf5975a1b3c2031baac5ff06961a1f979859`.
  The native job completed successfully.
  The separate host job is intentionally skipped, not counted as a new pass.

The intermediate queued `39501307268` and automatically triggered broad
`39500644316`/`39500644101` runs were cancelled when their narrower source-bound
checks became available. They provide no validation claim. No unchanged
emulator/JIT framework is rebuilt by the retirement check.

The native embedded-session adapter, runtime packaging, game/firmware/key/DLC
imports, original-control/editor adapter, graphics settings and NeoSwap mapping
integration are not complete. No firmware installation, homebrew execution,
physical controller, on-device relaunch or HD mod loading is claimed. No build
number has been allocated and no test IPA has been produced for this task.
