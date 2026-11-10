# Central RetroAchievements session

The main RetroAchievements tab owns the emulator account, activation and
Hardcore preference. The existing Web API dashboard remains a reader for the
same account. Its Web API key is not an emulator login token.

## Storage and launch ownership

`RetroAchievementsRepository` stores activation, Hardcore and migration version
in `ra_session_settings` in the existing application SQLite database. The native
plugin stores the emulator username/token in the iOS Keychain service
`<bundle identifier>.retroachievements`, account `emulator-player`, with
`WhenUnlockedThisDeviceOnly` accessibility. Passwords are used only for the
explicit login request and are never persisted or logged.

The Dart service serializes changes. `prepareSession` returns a one-use opaque
handle; the target native engine consumes it via `RBRATakeLaunchConfiguration`.
The credentials never travel through launch arguments or session events. The
immutable native snapshot includes the explicit application locale. Notifications
are derived from enabled RA. There is no separate notification preference.

Missing, consumed, expired, wrong-engine or unsupported handles fail closed.
The account or preferences can change while playing, but the running engine
retains its launch snapshot until its native shutdown completes. Publication is
read-only and distinguishes requested Hardcore from actual native activity.

## Migration

Migration runs once when the central SQLite migration version is zero. It reads
the legacy libretro and Dolphin Keychain records, libretro's explicitly stored
activation flag, Dolphin's `RetroAchievements.ini`, and ARMSX2's
`Documents/ARMSX2/inis/PCSX2.ini` plus `secrets.ini`. These inputs are read-only;
games, saves, existing INI files and old Keychain items are never deleted.

A single account with one consistent policy is imported automatically. Matching
usernames are compared case-insensitively and equal settings can be combined.
Different accounts or different activation/Hardcore settings require a choice
inside the main RA tab. Conflicting Dolphin Keychain/INI identities also remain
separate choices. The user may instead decline the import or log in explicitly.
The app does not infer opt-in from a missing legacy preference.

The native import first writes the new Keychain record together with its small
`migrationPolicy` metadata. Dart then commits the central preferences and
migration version in one SQLite statement. An interruption between stores
resumes the same central account and policy; no other old account may replace it.
Logout and declining import commit the migration version before deleting the
central token, so a later launch cannot re-import an old account. Stale candidate
handles are invalidated by explicit login/logout.

An unreadable store is not an empty store. Initialization keeps RA inactive and
offers retry. If only legacy input is unreadable, explicit login or declining the
import remains possible after the central database and Keychain were read
successfully. A central storage failure never triggers automatic deletion.

## Validation

`test/retro_achievements_session_test.dart` checks launch policy, next-launch
changes, serialized writes and capability boundaries. The separate migration
suite checks account conflicts, durable opt-out/logout, partial writes, retries
and explicit recovery. Native XCTest exercises the production Keychain/Hub and
INI parser; all require the corresponding Flutter/Xcode CI environment.

Portable C/C++ adapter checks run without Xcode. They do not establish real
device authentication, game recognition, award submission or Apple model
download/consent. The existing achievement translation/cache/presenter remains
the source of translated text and provenance, including its bounded toast
fallback; the session plugin never translates or delays an award.
