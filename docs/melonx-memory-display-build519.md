# MeloNX memory donor and display — private Build 519 delivered

The maintainer explicitly requested connecting MeloNX's original RAM donor,
showing measured RAM during gameplay, and adding per-game screen formats.
Build 518 launches on the maintainer's iPhone; this continuation preserves its
key import and UIKit/JIT retry fixes. Work remains on Claude, with a private
IPA only. No release, tag or main update is authorized.

The pinned MeloNX donor (13700519f3) supplies mapped chunks through its original
extension and XPC transport. A process-owned Swift lease offers the actual
mapped prefix to the actual Core allocator before a session. Normal allocation
remains the fallback when the extension is unavailable or refuses the loan.
The donor stays alive while memory is borrowed. A failed withdrawal or unmap
retains ownership and requires process restart instead of freeing live memory.
The original allocator refuses replacement/withdrawal while allocations remain;
Core exports also require an idle session. Late donor connections are isolated
by a fresh endpoint per acquisition. Partial mappings and scratch aliases retain
cleanup ownership. RPCS3-active sessions block MeloNX donor acquisition; the
frontend's existing single game route remains the session admission boundary.

A 120-sample, 2 Hz HUD reports TASK_VM_INFO.phys_footprint, available app memory,
peak footprint, mapped donor capacity and actual allocator usage separately.
Mapped capacity is not resident RAM, additional physical memory or evidence that
iOS memory limits have been removed. Invalid readings leave gaps. Sampling stops
when hidden, backgrounded or closed. Screen formats use the upstream renderer's
AspectRatio setting: 4:3, original 16:9, 16:10, 21:9, 32:9 and stretched. Changes
are generation-bound and saved per game, with rollback on save failure.

Validation targets: actual allocator ownership and zeroed reuse; production
Swift lease fault cases; complete iPhone SDK compilation; actual UIKit plugin
presentation/retry and RAM graph/timer checks; original extension compilation;
Flutter persistence/localization/import-disposal regression; rebuilt NativeAOT
ARM64 simulator with two homebrew sessions consuming supplied memory. The smoke
backing is a local mmap, not a donor process. Actual iPhone donor activation,
footprint benefit, commercial gameplay and FPS remain unverified until testing.

## Verified delivery

Private IPA **0.0.8 (519)** is frozen at `f93323768831428186c3aeb21b7e7a6130897836`.
[Delivery run 40043376467](https://github.com/TarbleFR/RewindBox/actions/runs/40043376467)
uses driver `df96b0d85f12d1442060e8d426175f3928fcb7bc`. Every checkout and shell build identity uses
the frozen source; the driver preserves concurrent RPCS3 integration on Claude.
The IPA intentionally retains the validated Build 518 RPCS3 Core and all other
prebuilt engines/dependencies. The new RPCS3 work is not overwritten or claimed
as part of this separate MeloNX test.

`RewindBox-Build519.ipa`: **186,248,745 bytes**, SHA-256 `2790348d9d9d33a2fee47856cf8669e23b251ac1f782d88e4a95b37ef46403aa`.
All 8 app/extension versions align. Independent validation
checked 87 ARM64 images, 117 CodeDirectories and
132,733 signed code-page hashes. The new original donor
extension is present with exact metadata and empty upstream entitlements.
SideStore must apply the user's Apple signing identity.

Core `c8424c32d2437b930870222fee1a07481d2b117d` / run `40038087907` passes 43 allocator/display cases
and two actual ARM64 simulator NativeAOT homebrew sessions using supplied mmap
memory, refusing live withdrawal, then releasing it. This test uses no donor
process and is not physical iPhone memory/FPS evidence. Host `5445f9bb3bd1b04ba88e4e4f03852e6dfbd4763e` /
run `40038955791` passes complete iPhone SDK checking, UIKit presentation/retry
and quarantine, original extension compilation, lease fault cases and bounded
RAM graph/timer tests. Flutter `5445f9bb3bd1b04ba88e4e4f03852e6dfbd4763e` / run `40038955747`
passes per-game preferences, method-channel persistence, imported flags,
retained-memory quarantine and all twelve translations; the unchanged import
widget proof is reused from run 40038088301.

The initial assemblies exposed CocoaPods header relocation and missing C++
module flags in the actual Pod target. Host build fix `a279185aec23fcbf9dfbd389a62f5c0e90d83bc6`
resolves both. The final delivery reproduces both old failures, verifies the
corrected framework using the actual CocoaPods settings and the iPhone SDK,
and reruns the complete Swift/Objective-C++ host SDK check. The unchanged UIKit,
allocator and Flutter proofs above are reused.

The final package-source inventory records the reviewed donor source selection
and module flags. UI validators require the exact declared extension set and
aligned versions, including the new donor. The package checks cover 27 malformed
and valid donor cases plus six extension-set/version cases.

Install over the existing application without uninstalling, fully close the old
process and launch the existing Switch game. The native menu controls RAM graph
visibility and screen format, including Stretch. Graphics settings can enable
or disable RamDonor for the next launch. Observe mapped/used donation separately
from app footprint; unavailable donation uses ordinary allocation. A retained
lease requires restarting RewindBox. Effective donor activation and commercial
playability remain the maintainer's physical acceptance test.

Receipt: `docs/evidence/melonx-memory519-delivery.json`.
**519 is frozen after delivery; later IPA changes require a new build number.**
