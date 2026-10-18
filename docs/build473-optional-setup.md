# Build 473 — optional first-run iOS library

The maintainer requests a visible way to skip the initial folder/linking step
when RetroArch is not installed. The current iOS setup already has three
library choices; the screenshot depicts the older single-Link screen. The
shared footer offered Skip on Android and later optional steps, but hid it on
the iOS folder step, although gamepad B already invoked the skip handler.

The sole product edit is `lib/widgets/setup_wizard.dart`. It exposes the
existing `skipForNow` button on the iOS library step in both orientations.
Skip uses the existing scan/next/art-pack/finish path without calling a folder
picker, creating an external bookmark or registering a made-up ROM folder.
An empty library is permitted. Games/folders can still be added later.
All twelve existing translations are reused, including Traditional Chinese.
Touch and gamepad Skip are blocked while a picker/import/download/save is in
progress; a deferred scan is cancelled if the wizard has been disposed.

`test/setup_skip_test.py` compiles the actual footer, skip, main action,
gamepad setup and finish methods with Flutter 3.47.2. Only I/O/providers and
unrelated setup page content are doubled. It includes the old invisible
iOS-button negative control, touch and gamepad navigation, a single scan,
no selected ROM folder, final save/completion, pending operation protection,
disposed callback cancellation, twelve translated labels at narrow portrait
and landscape widths, and retained Android/desktop footer visibility.
It does not claim an actual Files picker, emulator or physical iPhone run.

Only this changed UI proof is newly executed. Build 472's return-label proof,
471's corrected Nestopia and all unchanged native/skin/cheat evidence are
reused by source identity. The broad Libretro workflow started automatically
on the wizard path and was cancelled to avoid rerunning unrelated successful
suites. No core rebuild, data reset or public GitHub release is requested.

The next available IPA build is 473. Targeted CI, delivery identity, package
verification and the private handoff are recorded once actually completed.


## Actual targeted validation

Proof source `97fdd006ae30f9ab5b33d7e140fabf8bd98a9b52`, run
`39088013240`, job `117558563397` passed all seven scenario groups on
Flutter 3.47.2. The actual Flutter assertions ran from 01:52:31 to 01:52:40 UTC.
Artifact `12121487670` contains the verdict; ZIP SHA-256 is
`464e5cd0e500901b78ca13f2868a67474b225faa0b68cdfceadc47db4ec20ce3`.
Two new delivery-composition guard tests passed locally once. No successful
test is repeated by the delivery recipe. The automatically started broad run
`39088013058` was cancelled, not accepted as new validation.


## Verified private delivery

- Source `881c8df6bcffbdd0e4c3f5a32fd66492830f6dd1`, branch `Claude`.
- Run `39088132898` succeeded: checks `117558927955`, native reuse
  `117558927866`, cold Release `117559037325`; optional warm job skipped.
  Exactly one Build 473 IPA was compiled. The AOT/Xcode compilation phase
  passed from 01:58:07 to 02:02:44 UTC (277 seconds).
- Actual IPA **0.0.7 (473)**: `NeoStation-Build473-881c8df6.ipa`,
  **218,615,292 bytes**. SHA-256:
  `ab4ca98e5aa7221a824591c39fb7e277cda3c1e7df6ca14c44c4922205376054`.
- Encrypted artifact `12121897150`, 219,540,381 bytes, ZIP SHA-256:
  `0408158c50b0d444327f0c2fd80bfeab07ce5bc1d99d14307651847719638320`.
  The existing authorized recipient is unchanged. Private keys and transient
  delivery passwords are excluded from reports and deliverables.
- The first local decryption was attempted before the download process had
  finished; the archive hash guard stopped it before decryption/extraction.
  After awaiting download exit 0 and its exact hash, decryption succeeded.
  This preparation error caused no CI rerun or additional IPA compilation.
- Independent inspection passed ZIP structure, source stamp, all six bundle
  versions, exact final IPA identity and all 76 thin Mach-O fingerprints
  against the CI seal. CI verified 79 ad hoc signatures; codesign was not
  rerun on this Linux inspection host. SideStore Apple re-signing is required.
- The actual Flutter App AOT differs from delivered 472. Its SHA-256 is
  `238ca2566ddae7bfe028cf37619717408feb7f01cd978e911dab2638835c5b84`.
  All 34 Libretro cores, RPCS3, Dolphin, ARMSX2 and MoltenVK retain their
  delivered 472 code/data/ABI identities. Only Runner differs in the thin
  Mach-O ledger (the fat-wrapped Dart AOT is inspected separately).
- Desktop Commander completed a create-only copy and independently verified
  the same bytes/hash at
  `C:\Users\Coren\Downloads\NeoStation-Build473-881c8df6.ipa`.
  Existing IPAs were preserved. The temporary AES password was removed.
- No physical iPhone first-run, actual Files picker, RetroArch app launch or
  gameplay validation is claimed by the Flutter harness. No phone/Xcode test
  connection is available here. The unchanged prior proofs are reused.
  No public GitHub release was created.

## Changed files

Product: `lib/widgets/setup_wizard.dart` only. Focused proof:
`test/setup_skip_test.py`, `.github/workflows/setup-skip.yml`. Provenance:
`.github/diagnostics/setup_skip_delivery.py`, its two guard tests in
`setup_skip_delivery_test.py`, and `.github/workflows/retroarch-delivery.yml`.
`AGENTS.md` and this report record the scope and actual results.
