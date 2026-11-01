# Dolphin RetroAchievements session migration

The `retro_achievements_session` plugin owns account migration and storage. The
Dolphin bridge only consumes its immutable, one-use launch snapshot. It must not
read, validate, update or delete the old account on its own.

## Legacy stores verified in the delivered sources

### Keychain

- Class: `kSecClassGenericPassword`.
- Service: `(NSBundle.mainBundle.bundleIdentifier ?: @"neostation") +
  @".dolphin.retroachievements"`.
- Account: `emulator-player`.
- Value: UTF-8 JSON object with string keys `username` and `token`.
- Accessibility used by the old writer:
  `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`.
- No explicit access group or synchronizable attribute was supplied.
- The old validator accepted nonempty usernames up to 256 characters and tokens
  up to 4096 characters. The token came from the emulator login response's `Token`
  field; it is not the dashboard Web API key. No password was stored.

Only the central migration may import this record. A failed or locked-Keychain
read must not be treated as evidence that the player has no account. Retire the
old value only after the central store has confirmed its own successful write;
do not overwrite an existing central account silently.

### Dolphin INI

The previous Core also persisted credentials through Dolphin's base layer:

`<Application Support>/NeoStation/Dolphin/User/Config/RetroAchievements.ini`

The filename is **RetroAchievements.ini**, not Achievements.ini. Within section
`[Achievements]`, the relevant keys are `Username`, `ApiToken`, `Enabled`,
`HardcoreEnabled`, `ProgressEnabled` and `HostUrl`.

The path combines `DolphinInternalV2Service.rootDirectory()` and its `User`
launch argument with the pinned `CommonPaths.h` `RETROACHIEVEMENTS_CONFIG` and
`BaseConfigLoader.cpp` mapping for `System::Achievements`. The field names are
defined by `Core/Config/AchievementSettings.cpp` at upstream
`7cac54161659421ed95c2cd1c0b0746539a4cd38`.

The central migration should handle any retained INI credentials according to
its reviewed conflict policy. Do not remove or replace game files, saves, NAND,
other INI sections or emulation settings. Dolphin no longer uses these legacy
credentials as launch authority, even when the old record remains on disk.

## New native contract

The host imports `<retro_achievements_session/RBRASession.h>` and calls
`RBRATakeLaunchConfiguration(arguments, @"dolphin")` once after acquiring launch
ownership. Missing/invalid/unsupported snapshots disable RA. It reports only
`active`, `gameLoaded`, `hardcoreActive` and a technical `errorCode`, then calls
`RBRAEndSession` after failed launch or completed shutdown. It never publishes
the snapshot's username or token.

Two additive C exports are required in the rebuilt pinned Core:

```c
int32_t neostation_dolphin_configure_achievements_session(
    int32_t enabled, int32_t hardcore, int32_t notifications,
    const char* username, const char* api_token);
char* neostation_dolphin_achievements_snapshot(void);
```

The caller frees the returned JSON with `free`. `hardcoreEnforced` is an
additional internal host/Core field for unsafe-action guards; it is not
published as proof of active Hardcore awards. The original two-argument
`neostation_dolphin_configure_achievements` ABI remains exported but cannot
enable achievements from a credential pair alone.

Policy and credentials use `CurrentRun`, including the three upstream native
login/logout credential writes. `HostUrl` is explicitly the official HTTPS RA
server in that layer. No new token or host override is saved to the legacy INI.
The same session policy is reapplied after a console restart, because Dolphin
clears `CurrentRun` during shutdown. Full stop destroys the session client and
clears the in-memory credentials.

Requested Hardcore blocks state loading and cheat activation from launch,
including while login is pending or after a login failure. This restriction is
independent of the observed `hardcoreActive` value. Creating states and normal
in-game saves remain available. The published active state requires a logged-in
client, a recognized game and a set requiring native processing. Native login,
GameCube/Wii hashing, unlock evaluation and award callbacks remain Dolphin's.

The in-game account screen has been removed. The historical
`DolphinRetroAchievementsAccount.h/.mm` filenames retain only
`DOLSerializeMenuRequest` for existing menu/build manifests. The old Build 267
generator is a read-only validator and cannot recreate account UI or storage.

## Validation boundary

Portable C++ session/presentation helpers and pinned-source patch idempotence
have executable tests. UIKit account-removal/menu regressions are authored in
`test/dolphin_account_267_test.py --native`. They require Xcode and an iOS
simulator; neither these UIKit tests nor a full iOS Core/application build were
executed while preparing the isolated patches. Real RA login, game recognition,
Hardcore awards and notification rendering still need device validation.
