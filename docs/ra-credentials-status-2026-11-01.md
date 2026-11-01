# RetroAchievements credentials regression and in-game status (1 November 2026)

**Status:** source fix on branch `Claude`, after delivered Build 608. No IPA,
Core or CI build was produced. Physical-device validation is still required.

## Report and evidence

The maintainer reported that the last update "invalidates" RetroAchievements
credentials and that nothing in game showed whether RA was really active.
The screen recording of 1 November 2026 (16:05, Build 608) shows, in order:

1. The notification history: `Déconnecté de RetroAchievements` (only produced
   by the confirmed dashboard sign-out), then four
   `Connectez-vous ici pour activer les succès en jeu.` errors.
2. The Web form (username + Web API key): the API key field is focused but no
   keyboard is shown; the key is copied from the RA site and pasted after a
   long press.
3. The new `RetroAchievements en jeu` dialog: as soon as the password field is
   focused, the landscape keyboard leaves no room and the fields disappear.

No RA request was involved in step 1: the refusal is local.

## Root causes

| # | Layer | Cause | Since |
| --- | --- | --- | --- |
| 1 | Local validation | `_connectToRA` refused every Web sign-in while the in-game session was signed out (`raSessionLoginNeeded`), before any request. `RetroAchievementsProvider._authorityAllows` also refused or skipped the saved Web pair unless the in-game session was authenticated with the same name. | 608 (`906905a5`, `d7992b1f`) |
| 2 | Session persistence | At startup the dashboard was restored only through the in-game identity listener, so a player without an in-game token was signed out after every restart. Any in-game sign-in or sign-out reset the dashboard. | 608 |
| 3 | Form fields | `_syncAccountFields` rewrote the username and **cleared the API key** on every in-game account notification (for example right after signing in from the dialog). | 608 |
| 4 | Form layout | The in-game sign-in dialog kept the default `AlertDialog` insets, title padding and bottom action row. With a landscape keyboard (≈213 of 393 pt) its scroll viewport had 0 px: the focused password field was entirely hidden (measured −108/0 px visible). | 608 |
| 5 | Form input | `_buildFieldHighlight` inserted a wrapper only around the highlighted slot. When the gamepad highlight followed the focus to the API key field, the field state was re-created and its keyboard connection closed (field focused, keyboard gone). | before 608 (present since at least 25 October) |
| 6 | Session persistence | A failed startup Keychain/database read was cached by `initialize()`: RA stayed off for the whole run. | 608 |
| 7 | Error reporting | Web failures all became the raw English `User not found…`; the native sign-in treated an HTML/5xx answer or a missing token as a wrong password; libretro reported an unknown game (`RC_NO_GAME_LOADED`) as a load failure and a network failure of the token login as a login failure. | 608 and earlier |

The user's credentials were not at fault.

## Behaviour after the fix

### Credentials (main RetroAchievements tab)

- The Web dashboard (username + Web API key) and the in-game session (password
  → Connect token in the Keychain) are independent. A signed-out or unreadable
  in-game session never blocks the dashboard. Only a confirmed in-game account
  with a different name is refused (`raSessionDifferentAccount`): one screen
  never mixes two accounts. The Web key still never signs in an emulator or
  enables RA.
- The saved Web pair is restored at every start; an in-game sign-in with the
  same account or an in-game sign-out keeps the dashboard. The dashboard
  sign-out button still signs out both (unchanged).
- Typed or pasted values are never cleared by an account notification; the
  username is pre-filled only when empty or still equal to the previous value.
- The highlight wrapper keeps a constant widget structure.
- The in-game dialog uses compact chrome when the keyboard is up and puts
  `Close` in the title row: the focused field stays visible above the
  landscape keyboard. Usernames are protected from autocorrection, smart
  punctuation and capitalization (ASCII keyboard).
- Distinct messages, all in the 12 locales: empty fields
  (`pleaseCompleteAllFields`, `raSessionInputRequired`), refused Web key
  (`raWebKeyRejected`), unknown user (`raWebUserNotFound`), refused password
  (`raSessionLoginError`), refused stored token (`raSessionTokenRejected`),
  network (`raSessionNetworkError`) and unexpected server answer
  (`raSessionServerError`).
- A token refused by RetroAchievements during a game (`login_failed_-33/-34/-35`
  or `RA_AUTHENTICATION_FAILED` for the current launch generation) reopens the
  sign-in form with its own message; a new sign-in replaces it.
- The startup read is retried by the next consumer (tab, toggle or launch).
- The RA tab button shows the in-game state: not signed in, signed in · off,
  on, or sign in again. Activation stays an explicit choice in the main tab;
  when signed in but off, the dialog explains how to turn it on.

### In-game launch status

`RetroAchievementsSessionPlugin.m` owns one display-only status presenter per
launch (`RBRASetStatusPresenter`). Libretro, Dolphin and ARMSX2 register how
to present a toast on their own game view; the hub decides what to announce
from the facts the engine **published** (`RBRAStatusForState`). Labels come
from the application catalogs through the launch snapshot (`statusText`).

| Observed state | Notice |
| --- | --- |
| Player switched RA off | none |
| RA on, system/core not supported | not available for this game/core |
| RA on, no usable account | sign-in required (RA tab) |
| Engine `active` (signed in, game identified, set evaluated) | `Achievements active · account · x/y unlocked · Hardcore on/off/not applied` |
| Recognized game without achievements | recognized, nothing to track |
| Set not supported by the emulator | recognized, unsupported set |
| Unknown hash | not recognized (unlisted version or dump) |
| Token refused / network / other sign-in failure | refused / unreachable / could not sign in |
| Hardcore-incompatible options | achievements off (Hardcore options) |
| Nothing final after 3 s | signing in… / identifying the game… |
| Nothing final after 40 s | tracking not confirmed (game not recognized or server unreachable) |

Hardcore is shown only from the engine's observed `hardcoreActive`. Each
distinct final status is shown once (at most four notices per launch); the
presenter is detached when the launch ends or another starts. Status toasts
use the shared FIFO presenter (kind 3): no trophy, no translation note, never
overlapping an unlock. MeloNX has no RA integration and shows none. RPCS3
(PS3) was added afterwards, see [PS3 through RPCS3](ra-ps3-rpcs3-2026-11-01.md).

Per engine:

- **libretro** (rcheevos in the host): unknown game → `RA_GAME_NOT_RECOGNIZED`;
  token refusal → `RA_AUTHENTICATION_FAILED`; no answer → `RA_NETWORK_UNAVAILABLE`;
  publishes `loggedIn` and counts.
- **Dolphin** (pinned Core unchanged): a recognized game that its rc_client
  does not need to process for two consecutive polls is published as
  `RA_NO_ACHIEVEMENTS`. The pinned snapshot cannot distinguish an unknown game
  from an unreachable server: that case ends as "not confirmed" after 40 s.
- **ARMSX2** (pinned Core unchanged): publishes `loggedIn`; signed in with an
  identified set without achievements → `RA_NO_ACHIEVEMENTS`. A token-login
  failure is not exposed by the pinned Core state: "not confirmed" after 40 s.

### Unlock notifications

- libretro: title, description and localized points (`RBRAPointsText`, existing
  `points` label); Dolphin: localized points instead of a bare number;
  ARMSX2: points of the matched achievement.
- Translation, ordering and stale-session checks are the existing ones; the
  ARMSX2 Core's English login and game-summary notices are no longer shown
  because the localized launch status replaces them.

### Diagnostics without secrets

- App log (`LoggerService`, central redaction): session readiness, sign-in
  request/result codes, launch preparation (engine, system, core, capability,
  requested/enabled/Hardcore, generation), every session state transition
  (active, game, observed Hardcore, counts, error code), dashboard sign-in
  results by failure kind.
- libretro journal: `retroachievements: status <key>`, `unlock <id> presented`;
  token login result in the host log. Dolphin JSON log: `achievements.status`.
  Native sign-in and launch preparation `NSLog` lines carry codes and HTTP
  status only.
- No password, token, Web key, request URL or response body is logged.

## PlayStation 3

At the time of this fix the embedded RPCS3 Core (ABI 30) exposed neither
guest-memory reads nor a per-frame hook, so PS3 stayed "not supported". The
follow-up integration (optional Core hooks staged without a Core build, host
rcheevos client, Hardcore gates) is described in
[PS3 through RPCS3](ra-ps3-rpcs3-2026-11-01.md).

## Validation

Executed on Linux (Flutter 3.47.2, Dart 3.13.2, same version as CI):

- The new regression suite first reproduced all eight reported symptoms on the
  unmodified 608 sources (local refusal, no restore, dashboard resets, cached
  startup failure, the exact French error, cleared pasted key, 0 px password
  field), then passed after the fix.
- RA Dart suites: account consistency, capabilities, credentials, layout,
  migration, repository, session, session localization, login form selection,
  RA service and achievement translation — all green. Three existing
  expectations that encoded the 608 coupling were updated.
- The exact Build 608 CI Flutter scope plus the new file: 16 files, 187 tests
  passed; `flutter analyze` on the 608 analysis scope plus the new files: no
  issues. Whole-project analysis: 121 pre-existing infos in unrelated tests,
  identical on `68a45efd`.
- Python contracts: `rewind608_delivery_contract_test.py` (36),
  `rewind608_reuse_test.py` (32), Dolphin/ARMSX2/libretro RA policy and legacy
  contracts, achievement translation contracts, central native harness
  `--check-only` (39 XCTest methods).
- Clang ARC syntax/type checks with GNUstep and stub headers: the central
  plugin, `LibretroAchievements.m`, and the changed libretro, Dolphin and
  ARMSX2 methods compiled in isolation; the new XCTest methods compiled in
  isolation. This is not an Apple SDK build.
- Full Dart suite: 3783 passed, 8 skipped, 25 failed. The same 25 tests (in
  15 unrelated files: library, MeloNX, NeoPlay, RPCS3 import/locale, Dolphin
  import, storage rotation, external display) fail identically on an untouched
  worktree of `68a45efd`; none involves RetroAchievements.

Not executed: Xcode/Swift compilation, XCTest (central hub and toast
presenter), the application build, and anything on an iPhone (sign-in,
restart persistence, game recognition, status toasts, unlocks, Hardcore).

## Delivery impact

Only application-side sources changed (Dart, host plugins, shared presenter and
central plugin). Dolphin, ARMSX2, RPCS3 and MeloNX Core sources are unchanged.
The 608 reuse of product tests no longer applies to these inputs: a new IPA
needs fresh Flutter/native tests and a full application build, which require
the maintainer's explicit authorization.
