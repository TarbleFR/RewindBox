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
