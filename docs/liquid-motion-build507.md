# Liquid Motion — candidate 507

Integration branch: `Claude`. No main change, release or version tag.
Product baseline: `4fb8ffe6672c7802ea39d7144dfc762a7b9f1a18` (MeloNX 506 assembly).
Tested final UI source: `225783a330e099d0fcbd95dd45ed4454fbe1ee9a`.
Full initial Flutter/UIKit checks: source `3dfd2d668ae6855094d24789b0ebc4cb683047d8`,
run `39864139925`. Final carousel checks: run `39865309953`.

## Actual author motion and navigation

The official Mau Ali **Interactive iOS 26 Inspired Tab Menu** dotLottie was
retrieved from the public asset URL advertised by its original page. Its 60 fps
scene has five fixed icon states and two state machines. The original archive
is retained under `assets/data/mau-ali-tab-menu.lottie`, with the full Lottie
Simple License and end-user attribution in the credits.

RewindBox adapts the original Select_mover PnW easing and Selected 2 scale
keyframes through the existing Flutter animation/rendering stack. The source
profile and archive SHA-256 are in `assets/data/mau-ali-tab-motion.json`.
Duration is adapted to 330ms; deformation is attenuated to 55%. This is an
actual adaptation of the author's motion data, not a dotLottie runtime claim.
The original scene's fixed icons, texts and opaque backdrop are not drawn.
No new hosted package or animation runtime is introduced.

The visible tab registry, canonical indices, focus, swipes, keyboard, bumpers,
D-pad and stick remain the existing Build 505 navigation. The moving glass
lens retargets from its current position, including rapid reversals. AirPlay
remains between Search and Achievements. Hidden-tab preferences are retained.

## Console perspective

Only `MySystemsCarousel` opts into GPU perspective in `NativeCarousel`.
The selected console is forward; neighbours recede and turn toward it. The
same cached SystemCard artwork/NeoAssets selection is transformed, preserving
image aspect, media cache and text. Game cover carousels, grid and list retain
their old geometry. The existing console-to-playlist morph and input lifetime
lock are unchanged; returning retains the selected console.

The new rotation regression found that Flutter could retain a ScrollPosition
whose custom physics still used the previous viewport's page pitch. Console
PageView identity now follows that pitch and restores its own selected index,
preventing the old ballistic snap from moving the selection after rotation.
Rapid controller requests retain a target index while a transition is running.
A deterministic fast-fling regression also reproduced a stale target when
switching back to a controller. Manual ballistic movement now follows the
actual centred page, and generation IDs prevent an interrupted animation's
completion from unlocking a newer movement. Two orientation cases exercise
this mixed-input path; unchanged full Flutter checks are authenticated and
reused rather than replayed.
Reduced motion uses static geometry and immediate controller selection.

## Real liquid progress, in Flutter and UIKit

Flutter transfers use one reusable measured capsule for themes/System Art,
skin/overlay catalogue checks, library/manual downloads, update downloads,
ARMSX2 texture operations and notification progress. A shared, paint-only
clock caps the slow liquid surface updates at 30 Hz; there is no timer per row.
Progress changes ease toward the reported amount and never draw ahead of it.
Unknown durations use separate moving droplets with no fictional percentage.
Paused/error states stop movement; explicit success can show a brief pulse.
Existing service messages and retry/cancel actions remain authoritative.

The main HD texture and unified cheat pages are **native UIKit**, so they use
`RBLiquidProgressView` from the existing local GPL host pod. The texture pod
reuses this public view instead of adding another renderer dependency. Native
views share a single CADisplayLink, observe Reduce Motion and Low Power Mode,
and detach or stop when hidden/offscreen/backgrounded. Download/install phases
use the existing actual received/total values. Texture catalogue refresh with
no measurement remains indeterminate. Native installs, byte counters, network
requests, partial files, integrity checks and retry/resume logic are unchanged.
NeoAssets progress remains its existing measured completed-file ratio.

## Device and controller battery

The device battery has a compact glass outline and vertical liquid level,
with the real percentage beside it, a charging bolt and restrained amber/red
low-charge colours. Controller readings retain their existing identity and
unknown-level behaviour; a controller no longer hides the requested device
reading. The device label is provided in all twelve supported languages.

Existing battery_plus level/state reads are reused. The existing local
ui_refresh_rate plugin now also forwards native power-change notifications
through a separate event stream, so toggling Low Power Mode stops liquid
movement without waiting for a polling interval. Its display-rate hook and
emulator-facing APIs remain byte-identical. Charging motion is suppressed
with Reduced Motion, inactive TickerMode, background lifecycle and the frontend
emulation barrier. A stopped clock never increments a battery reading.

## Verification and delivery

The closed product allow-list is `test/fixtures/motion507-scope.json`.
`test/liquid_motion_scope_test.py` verifies the exact UI scope and unchanged
startup, routing, engines, storage and network services against the baseline.

Local changed-component analysis has no remarks. Full-app analysis succeeds
with the same ten pre-existing MeloNX style infos, which are outside this UI
scope. The GitHub Flutter job passed **74 tests**, plus 3 library-baseline,
13 display-hook scope checks (2 source-environment cases skipped), and 8 legal
packaging tests. The intermediate local fixture compile failure, rotation failure and mixed-input
negative control were corrected; neither is represented as a successful run.

The native job type-checked the real cheat/texture page sources and modified
power plugin against the iPhone SDK, then passed **11 XCTest cases** using the
actual UIKit material, real power notifications and the existing real-Flutter
hook harness in the iOS Simulator. Native receipt/attachments:
artifact `12463981247`, SHA-256
`605cd2187fe99e637f5389e53ee2967678e15eec7f5c4780e9a6253c20dbba0e`.
The final carousel run `39865309953` passed both strengthened cases after
authenticating the unchanged successful full Flutter job `120121960951`.
Build 506 delivery `39863280830` also succeeded in full. Final signed-IPA
identity is recorded after delivery. Host/simulator tests do not prove physical Bluetooth input,
commercial downloads, iPhone gameplay or measured 60/120 fps.

The final delivery reuses the successful 506 native assembly and the exact
successful motion checks, with all existing engine, payload and signature
gates retained. An additional post-sign IPA inspection requires the original
motion archive/profile, full author notices, linked UIKit class, native power
channel, compiled Dart components and aligned app/extension build versions.
The final IPA requires normal Apple re-signing through SideStore/AltStore.

The first 507 assembly attempt `39865696331` stopped before compilation:
the new source gate incorrectly expected a direct `sign_delivery.py` call in
the workflow. The actual preserved entry point is `delivery_benchmark.py seal`.
The corrected gate checks that entry point and the byte-identical benchmark
and signer implementations. It was preflighted against authenticated actual
GitHub run/job metadata; no product source or successful test phase changed.
