# ARMSX2 RetroAchievements launch contract — ABI 9

The application owns account selection, activation and the requested Hardcore
mode through `retro_achievements_session`. The native bridge consumes one
`raSessionId` via `RBRATakeLaunchConfiguration(arguments, @"armsx2")` before
preparing the VM. No engine preference can substitute for a missing handle.
Configuration changes apply to the next launch; the current session keeps its
immutable snapshot until native shutdown completes.

## Native execution and credentials

`NeoARMSX2Configuration.achievements` points to a sized
`NeoARMSX2RALaunchConfiguration`. `prepare()` copies its username and token before
starting the worker. Invalid or disabled configurations produce an empty,
disabled native policy. The pointers supplied by the host are never retained.
The token is not added to events, JSON status, diagnostics or INI writes.

`ARMSX2RALaunchSettings` adapts the existing native settings interfaces. Its base
and secrets adapters retain the real INI objects for unrelated settings. A top
priority command-line layer also covers later per-game INI loads. The pinned
native `Achievements::Initialize()` consequently uses its normal
`rc_client_begin_login_with_token` path with the central account. Achievement
evaluation, unlock submission, synchronization and rcheevos callbacks remain
upstream implementations.

The base-layer Token is deliberately empty: the pinned engine otherwise moves
an old base-INI token into `secrets.ini` during initialization. The secrets and
top-priority layers supply the launch token. The old `Achievements/Host` override
is also masked so it cannot receive the central credential; an empty Host selects
the native client's default RetroAchievements service.

The native worker owns the overlays until `CPUThreadShutdown()`. Teardown restores
the prior command-line layer, removes the adapters, and clears the copied token
after joining the worker. A failed cleanup retains session ownership and blocks
a second launch. This does not claim that the process or upstream network client
can erase every historical in-memory copy of a string.

## Requested and observed Hardcore

`hardcoreActive` comes from the real native achievement client. Published `active`
requires an authenticated client, an identified game and available achievements;
merely retaining a username or initializing the client is insufficient.

Restrictions are armed earlier: `hardcore_restrictions_active()` combines the
validated launch request with the actual native Hardcore state. The host menu's
`hardcoreGuardActive` is distinct from `hardcoreActive`. This closes the window in
which login is pending and a load-state or cheat command could otherwise execute.

During a requested Hardcore launch, the settings overlay disables cheats,
recording tools and PINE; clamps speed scalars to at least normal speed; restores
the native NTSC/PAL frame rates; and disallows EE underclocking and cycle skip.
Allowed acceleration and overclocking are retained. These are runtime reads;
the user's stored settings are not rewritten by the overlay. Existing native
Hardcore enforcement continues after authentication.

The host and native adapter reject loading states and enabling cheats while the
guard is active. Saving states and normal memory-card saves remain available.
The patch catalogue exposes the same guard and rejects cheat activation. The
embedded host exposes no rewind or slow-motion command and does not auto-load a
state at boot. This change does not add such commands.

## Notifications and UI

`Notifications`, `LeaderboardNotifications`, `Overlays` and `LBOverlays` follow
central activation for the entire launch, including when an old INI says false.
Notification filtering occurs only in the presentation adapter, after the native
event is consumed. It cannot suppress the native award or synchronization path.
The existing translated presenter, original-source matching and controller
ownership checks remain; asynchronous presentation also checks the immutable
session identity. Failed/stopped sessions cannot present a delayed translated
toast in a later game.

The ARMSX2 RA settings/account screen and its menu route are removed. ABI 9 removes
the interactive option/login/logout operations. The only in-game RA ABI operation
is the read-only status query; preparation remains the private configuration
entry point. Upstream authentication and achievement event handling stay native.

## Legacy migration boundary

The shared plugin, not the running engine, owns any one-time migration. The
embedded ARMSX2 data directory is the launch argument `dataPath`, normally
`Documents/ARMSX2`. The exact legacy files and keys are:

| File relative to `dataPath` | Section | Keys |
| --- | --- | --- |
| `inis/PCSX2.ini` | `Achievements` | `Username`, `LoginTimestamp`, `Enabled`, `ChallengeMode`, `Notifications`, `LeaderboardNotifications`, `Overlays`, `LBOverlays` |
| `inis/secrets.ini` | `Achievements` | `Token` |
| `inis/PCSX2.ini` (older installations) | `Achievements` | `Token` |

Do not log these values or pass a token through Dart, status events or diagnostics.
The native adapter does not erase or migrate these files. It ignores their
account/activation/Hardcore/presentation values whenever a new launch is prepared,
including launches with no valid central session. An account switch or logout
never triggers an engine re-import of a legacy token during the current game.

## Build and validation requirements

ABI 9 must be rebuilt from the pinned upstream revision
`9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe`. The host intentionally rejects ABI 8;
an old cached framework cannot silently use the new configuration layout. Update
the Core manifest, CI expectations and receipt validators together. The host pod
now depends on `retro_achievements_session`; standalone syntax/UIKit checks must
stage its public headers and link its implementation where applicable.

`test/armsx2_ra_launch_settings_test.py` compiles and runs the production settings
adapter with a recording `SettingsInterface` boundary fixture. It checks missing
and invalid sessions, copied credentials, a changed legacy account, next-launch
replacement, presentation policy, pending-login restrictions, per-game overlays,
preserved legacy storage and unaffected non-RA settings. This is a C++ regression
test, not an iOS or emulator build.

The existing macOS Foundation save-state and patch-catalogue fixtures additionally
cover requested-but-not-yet-active Hardcore; save-state creation still succeeds.
They require their actual native CI environment. Real login, game identification,
unlock delivery, model downloads, UIKit presentation and a full signed-device
session still require their appropriate native build/device checks.
