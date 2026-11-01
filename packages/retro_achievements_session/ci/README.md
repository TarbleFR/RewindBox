# Central RetroAchievements native tests

The harness compiles every production file in `ios/Classes`, including the
private migration helper, with the real Flutter iOS framework. A small UIKit
application hosts XCTest. The test bundle calls the production plugin and C
functions; it does not substitute a fake Hub or a fake Flutter method codec.

On macOS with Xcode 16.4 selected, XcodeGen installed and Flutter's iOS artifacts
available:

```sh
flutter precache --ios
python3 -B test/retro_achievements_session_native_test.py --output build/ra-session-validation
```

Set `FLUTTER_ROOT`, or pass `--flutter-root /absolute/path/to/flutter`. The runner
selects an available iPhone simulator matching the selected SDK. It writes
`RetroAchievementsSession.xcresult`, `xcodebuild.log`, `test-summary.json` and
`validation.json` under the output directory. Existing evidence is not overwritten.
Success requires a successful `xcodebuild test`, the expected test count, and zero
failed or skipped tests in the actual result bundle.

Linux can check the files and harness contract only:

```sh
python3 -B test/retro_achievements_session_native_test.py --check-only
```

That command explicitly reports that compilation and XCTest were **not run**.

## Behavioral coverage

- One-use handles, engine binding, expiry and simultaneous consumption.
- Immutable account/policy snapshots; activation determines notifications.
- Unsupported or unauthenticated launches remain disabled.
- Publication and termination require the exact owned snapshot. Public IDs and
  reconstructed dictionaries cannot replace that authority.
- Stale session callbacks and queued events, idempotent end, concurrent updates
  and delivery through the actual Flutter codec on the main thread.
- Logout invalidates pending launches while preserving the running snapshot.
- Authentication request encoding, success/failure, redirect refusal, cancellation
  and superseded requests. Passwords, tokens and raw response errors stay out of
  Flutter replies and session events.
- Actual Keychain storage under the test application's distinct bundle ID.
- Migration through the real INI parser: UTF-8/BOM, comments, quoted values, `=`,
  unknown/malformed sections, missing files, unreadable files, invalid encoding
  and the size bound.
- Case-insensitive account grouping with policy conflicts kept as choices,
  Dolphin Keychain/INI precedence and account conflicts, ARMSX2 secrets/base-token
  precedence, and missing libretro defaults remaining disabled.
- Inspection/import/interrupted SQLite completion/re-inspection and completion
  exercise the native Hub; the original fixture files and legacy Keychain item
  are checked for preservation. This does not execute the Dart SQLite layer.
- All 12 explicit application languages and Traditional Chinese aliases for the
  shared restriction labels.

## Test isolation and limits

Fixtures use dummy credentials only. The Keychain helper refuses to run outside
`org.rewindbox.tests.ra-session.host`. Legacy files/defaults are confined to that
simulator application's sandbox; no installed RewindBox data is accessed.

Authentication requests pass through the real NSURLSession code, with a test-only
NSURLProtocol attached by a factory swizzle in the XCTest bundle. Every request is
intercepted; no fixture contacts RetroAchievements. Cancellation tests hold a
request until cancellation instead of relying on a short timing window. The
factory is restored at class teardown. Expiry and reset use declarations of the
existing private Hub inside the test bundle. Production exposes no reset,
alternate endpoint, test credential or clock-injection API.

These tests do not prove a real server login, emulator game identification,
achievement evaluation/submission, translated game notifications, Apple model
downloads, or physical-device operation. Those require their respective native
and device checks. A source-contract check or YAML parse is not an XCTest result.
