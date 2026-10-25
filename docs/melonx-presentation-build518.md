# MeloNX launch presentation — Build 518 delivered

The latest supplied `app(7).log` and screen recording concern Build 517. In the
21:58 UTC session, personal keys reload successfully, the base program content
preflight passes, firmware 22.5.0 is recognized, and the real ARM64 JIT arena and
helper detach pass. The first launch then fails with `presentationUnavailable`.
The next attempt repeats the one-time JIT transaction and remains pending. The
post-import playlist also logs a null-context exception. No key material, game,
firmware or user recording is committed or sent to CI.

Three production changes address these observed failures:

- Resolve the Flutter registrar's current controller at launch, with an attached
  foreground application-window fallback. Registration no longer freezes a nil
  controller. Wait briefly for UIKit presentation/dismissal transitions and honor
  cancellation while waiting; external-display scenes are excluded.
- Retain successful process-local arena initialization and helper detach before
  UIKit presentation. A failed presentation can retry without repeating the
  completed one-time transaction. Launch success still requires the original
  first-frame confirmation, and Dart still checks live JIT authorization.
- Capture translated import feedback before asynchronous playlist refresh and
  stop using the widget after disposal. Existing translations are unchanged.

Targeted validation compiles the full production Swift host for iPhone and runs
the registered plugin in real UIKit/Flutter on ARM64 simulator, comparing the
delivered old plugin with the correction. Registrar, guest and JIT boundaries
are explicit doubles: this proves presentation, retry and cancellation behavior,
not commercial gameplay or physical-device JIT. The Flutter regression likewise
reproduces the old post-import null-context warning before checking the corrected
widget with a completed production key import. Only synthetic key values are used.

The already validated Build 517 NativeAOT Core and keys behavior are reused,
along with all other engines including RPCS3 515. Private Build 518 was delivered after these targeted checks, IPA packaging and
independent downloaded payload verification passed. Physical iPhone launch remains the user's acceptance
test; no FPS or commercial gameplay claim is made from simulator doubles.

## Verified private delivery

IPA **0.0.8 (518)**, source `9d064ad1e757e27dc2fc133a17b3e791178a9871`, successful delivery
[run 40033179437](https://github.com/TarbleFR/RewindBox/actions/runs/40033179437).
`RewindBox-Build518.ipa`: **186,175,893 bytes**, SHA-256 `1676b422e7bea341d8f81ab36e64488e995e52ee8dd50a99216db077e19a7934`.

- UIKit/Flutter simulator run `40031804127` passed four old-code controls and
  twelve corrected-code assertions, including three consecutive presentations,
  late controller attachment, foreground window fallback, existing modal traversal,
  prepared-arena reuse and cancellation. The iPhone SDK compilation and 24 native
  host ABI-double cases also passed. Production guest/frame code remains unchanged;
  simulator frame/JIT/engine doubles do not establish physical gameplay.
- Flutter run `40033099656` reproduces the disposed-context warning with the
  delivered old widget, then completes the real import and callback/disposal path
  without that warning using the corrected widget. Its picker/native boundaries
  use synthetic values and doubles. Analysis passed with only existing style infos.
- The downloaded encrypted parts, their complete reconstructed encrypted payload,
  source identities and final IPA were verified independently. All
  7 app/extension bundle versions align; all
  86 ARM64 images, 116 CodeDirectories and
  132,675 code-page hashes passed validation. The new UIKit
  code markers and exact three product source hashes are bound inside the IPA.
- MeloNX Core source `e0a1196d70469a28f04cc8a3628f43d484015581` and RPCS3 source `a69860297d7b26dbb688df0daf16a31b42046462` are
  unchanged; their compiled payloads and all other prebuilt engines/dependencies
  match the verified inputs and delivered 517 app. Personal content is not bundled.

Install 518 over the existing application using the same SideStore/AltStore
identity, close the old process and retry the existing Switch game. Existing
accepted keys and firmware can be retained. Physical iPhone launch/gameplay is
still the maintainer's acceptance test. No public release, tag or main change.
**518 is frozen after delivery; any later IPA requires a new build number.**

Receipt: `docs/evidence/melonx-presentation518-delivery.json`.
