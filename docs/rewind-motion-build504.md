# Rewind Motion — test delivery 504

Maintainer-requested startup presentation on Claude, without tag, release or main merge.
Preserves Build503's console glass bubbles, playlist morph transitions, all emulator
binaries, storage/import/scan implementations, HD catalogues and twelve locale maps.

One persistent root now spans pre-database initialization, permission checks and the
initial library scan. MyApp mounts and paints normally below the startup barrier.
Actual library/setup/error content reports its first painted frame before opening.
The former 2500ms minimum scan splash is removed. Early readiness settles the current
fragments while opening in 240ms (100ms with Reduce Motion); initialization never waits
for an animation or a network animation asset. Slow starts retain a 0.6% breathing mark
and a small neutral activity line, without brand text or console names. Storage recovery
retains its localized retry/default controls and controller key bindings.

The supplied official JPEG is kept byte for byte as the source reference. Its two white
contours are traced with a 0.3-source-pixel simplification bound and shared by the Flutter
Path and native transparent vector PDF. A raster comparison requires >99.9% contour-mask
intersection-over-union. Native and Flutter center a square at min(232, 0.58*shortestSide)
on uniform black, including rotation; the generated host view is black too. The native
Launch Screen is static. Flutter rewinds six clipped pieces of the actual mark with faint
trails, elastic reconstruction, a single reflection and an opening fade/scale. No font,
video, third-party animation package, image decode or emulation-time effect is added.

The intro is one-shot. It pauses when inactive; dismissal stops its controllers and timers.
The actual platform Reduce Motion/disableAnimations flags suppress fragment movement,
reflection and pulse. App pointer/focus/semantics input stays covered until opening ends.
Recovery is separately interactive. No warm-resume replay is scheduled.

Targeted Flutter tests cover cold slow and fast startup, painted setup readiness,
recoverable storage retry, warm resume, Reduce Motion, interruption, rotation and disposal.
All twelve startup locale maps are tested. Full Flutter analysis must pass. Native tests
verify source geometry, static constraints, idempotent generated-host configuration and
preserved identifiers; Xcode compiles the actual iPhone/iPad launch storyboard.
Main.dart and SystemContent have exact inverse presentation/formatting deltas back to
Build503 before the existing Build419 library hash guards. Provider/scan bytes are unchanged.

Native launch proof: run39843086776, source409ee862, named native job succeeded. That
run's Flutter analysis failed on an old import; its overall result is explicitly failure.
The import is corrected and formatting reviewed in the final Flutter candidate. Reuse
only that run's successful native component after exact source and recipe comparisons.
Other engine/native evidence comes from the successful immutable Build503 delivery.
The delivery guard closes every tested source byte; the only following changes are
this note, the build identity, delivery evidence reader and fresh public recipient key.

Build504 recompiles the current Flutter application and native launch resources, packages
a new IPA, stamps all application bundles504, checks device layout, licenses, engine pins,
Mach-O and signatures, and uploads only the existing encrypted Actions artifact. The
recipient key is session-owned. Apple signing through SideStore/AltStore is still required.
No physical iPhone launch/install or 60/120FPS measurement is claimed by unit/CI tests.
