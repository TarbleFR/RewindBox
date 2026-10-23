# MeloNX launch presentation — Build 518 candidate

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
along with all other engines including RPCS3 515. A private Build 518 may only be
delivered after these targeted checks, IPA packaging and independent downloaded
payload verification pass. Physical iPhone launch remains the user's acceptance
test; no FPS or commercial gameplay claim is made from simulator doubles.
