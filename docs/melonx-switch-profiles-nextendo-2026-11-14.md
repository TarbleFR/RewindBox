# Switch profiles and Nextendo Network — 14 November 2026

Maintainer request: add Nextendo to the embedded MeloNX engine, let players
create a Switch profile, reach the original Switch menus "if possible", sign in
to their Nextendo account and play online on Nextendo's servers, all from
RewindBox.

Status in one table. "Local" is this session's Linux x86_64 container; nothing
below has run on an iPhone.

| Part | State |
| --- | --- |
| Switch profiles screen | Written; Dart analysed and tested locally; not compiled into an IPA |
| Nextendo sign-in and account screen | Written; Dart analysed and tested locally against a stand-in server; Swift sheet written, not compiled; needs RewindBox's registration on Nextendo's side |
| Game token at launch (Dart → Swift → engine request) | Written; inert with the current Core, which has no such request |
| Engine online lot | Source only, outside every Core; builds locally on the current preparation; behaviour checked locally |
| Online play on Nextendo's servers | Not possible yet: needs the three items of "What the maintainer must obtain" and a Core that includes the engine lot |
| Original HOME menu | Not possible with the pinned engine (see below) |
| Mii Maker applet | Present upstream, not exposed by RewindBox's launch path; not done |

## What Nextendo Network is, and how a third party may use it

[Nextendo Network](https://nextendo.network) is a community-run replacement for
the Switch online services (accounts, friends, matchmaking), independent of
Nintendo. Its own clients are Ryujinx-Nextendo, Citron-Nextendo and the Prelude
homebrew.

Two facts decide how RewindBox integrates it:

1. **Licence.** Nextendo's client and server sources are published under the
   PolyForm Shield License 1.0.0, which forbids using them for a product that
   competes with Nextendo's own. None of that code is copied or adapted in
   RewindBox. Everything here is written from Nextendo's public
   [developer documentation](https://wiki.nextendo.network/developers), which
   addresses "emulator forks" explicitly.
2. **Access.** Nextendo runs a developer portal
   (<https://nextendo.network/developers>). An application is registered there,
   gets a client identifier (`nxc_…`), and players sign in on nextendo.network
   through OAuth 2.0 with PKCE. Nextendo states that a player must never type
   their password into another application, and that unregistered clients are
   refused. RewindBox follows that path and no other: it never asks for a
   Nextendo password and never calls the routes reserved to Nextendo's own
   applications.

Nextendo keeps three things for its own builds, and RewindBox does not take
them from those builds:

- the two game-server addresses (`NEXTENDO_SERVER_IP`, `NEXTENDO_NAT_IP`), which
  Nextendo's documentation says "official builds provide" and its public source
  omits;
- the RSA key that signs the account `id_token`. A third-party build signs with
  a throwaway key, so games that verify that signature themselves (Splatoon 2
  is the documented example) refuse it online;
- cloud saves, account management and console linking, reserved to official
  applications.

## What the maintainer must obtain

1. **A client identifier.** Sign in on <https://nextendo.network/developers>
   (the account needs a verified e-mail address and a linked Discord account),
   create a *public* application (PKCE, no secret), and register the redirect
   address `rewindbox-auth://nextendo/callback`. Scopes used: `identity` and
   `game.matchmaking`. The application's name may not contain "nextendo",
   "nintendo" or "ryujinx".
2. **The two server addresses** (IPv4), asked from Nextendo's team for this
   registered application.
3. Optionally, Nextendo's position on the `id_token` signing key for a
   third-party emulator, which decides whether titles such as Splatoon 2 can
   ever work.

Where the values go: build defines `NEXTENDO_CLIENT_ID`, `NEXTENDO_SERVER_IP`
and `NEXTENDO_NAT_IP` (`.env.example`). The standard delivery workflow does not
pass them yet; that is a small recipe change to make once the values exist. A
build without them shows three fields at the bottom of the Nextendo screen
("Application registration"), so the maintainer can enter the values on the
device and test without a new build. A build with them hides those fields.

## Switch profiles (application side, no engine change)

The engine rebuilds its account manager from
`Documents/MeloNX/system/Profiles.json` at every game launch, and the standalone
MeloNX application edits the same file from its own profile screen. RewindBox
therefore reads and rewrites that file directly, while no game runs.

- `lib/services/melonx_profiles_service.dart`: list, create, rename, picture,
  delete, select the profile games open (`last_opened`). Unknown fields are kept;
  the file is replaced atomically; an unreadable file is reported and never
  overwritten.
- Limits taken from the console: 8 profiles, a nickname of 10 characters at most
  (and 31 UTF-8 bytes, the guest's field), a JPEG picture of 128 KiB at most.
- The default profile (`00000000000000010000000000000000`) cannot be deleted:
  the engine recreates it when missing and then opens it instead of the selected
  one. For the same reason a file written here always contains it.
- A profile a game is pinned to (`rewindboxSaveProfileId`, written when its saves
  were imported) cannot be deleted: that game would refuse to start.
- Deleting a profile removes it from the list only. Its saves stay on the device.
- `lib/services/melonx_profile_avatar.dart` and `lib/utils/baseline_jpeg.dart`:
  a profile picture is a 256 × 256 JPEG. Flutter decodes images but only encodes
  PNG, so RewindBox carries its own baseline JPEG encoder (ITU-T T.81 Annex K
  tables). A picture is either RewindBox's own drawing on one of eight colours
  or an image the player chooses, cropped to its centred square.
- `lib/widgets/melonx_profiles_dialog.dart`: the screen, opened from the Switch
  playlist menu ("Switch profiles"). Every write holds the native launch gate
  (`MelonxInternalService.editLibrary`).

Known limit: an engine already loaded in the process keeps the profile list it
read earlier, and the save-import dialog asks that engine. After a change made
here, a new profile appears there at the next game launch or application start.
The engine lot adds a request that closes this gap (operation 12).

## Nextendo account (application side, no engine change)

- `lib/services/nextendo/nextendo_config.dart`: client identifier and server
  addresses, from build defines or, without them, on-device values.
- `lib/services/nextendo/nextendo_service.dart`: the documented flow.
  `GET /api/oauth/authorize` (S256 challenge, `state`), `POST /api/oauth/token`
  (authorization code, then rotating refresh token), `GET /api/oauth/userinfo`,
  `POST /api/oauth/revoke` at sign-out, `GET /api/nex-token` for the game token,
  `GET /api/online-status` with that token. Tokens are sent to
  `https://nextendo.network` only and kept in the keychain
  (`flutter_secure_storage`). A refresh token is single-use: concurrent callers
  share one refresh, and the new token is stored before anything else uses the
  session. A session kept for another client identifier is discarded.
- `packages/melonx_internal_bridge/ios/Classes/MeloNXWebAuth.swift`: the system
  sign-in sheet (`ASWebAuthenticationSession`), channel `neostation/web_auth`.
- `lib/widgets/nextendo_dialog.dart`: the screen, opened from the Switch playlist
  menu ("Nextendo Network"): sign in, linked identity and friend code, the
  online-play switch, "Check online access" (Nextendo's own reasons: unverified
  e-mail, no linked Discord account, account online elsewhere…), sign out.
- `lib/l10n/switch_online_locale.dart`: both screens in the twelve languages.

## Launch

`MelonxInternalService._launch` asks `NextendoOnlinePlay.forLaunch` for the game
token of that launch (8 s at most). It answers only when a player is signed in,
online play is switched on and the build knows both servers. Anything else
leaves the game starting offline exactly as before; a launch is never refused
for it. The token travels in memory (`online` launch argument →
`MeloNXInternalBridgePlugin.configureOnline` → engine request 11) and is never
written to a file or a journal.

With the Core in place today the engine has no request 11: the bridge journals
"this engine does not accept an online configuration" and the game starts
offline.

## Engine online lot (source only)

Another session freezes and compiles MeloNX Cores on this branch, so this lot is
kept out of the preparation: `prepare_embedded.py` does not import it, and its
C# file is in a subdirectory that the preparation does not copy.

- `native/melonx/online/EmbeddedOnline.cs` (project `Ryujinx.HLE`): the
  configuration of one session and the documented rules.
- `build-utils/melonx/online/adapt_nextendo_online.py`: fail-closed edits pinned
  to the preparation of Claude `b83935f0` (Core contract `4396d7b0`):

| File | Edit |
| --- | --- |
| `EmbeddedSession.cs` (prepared copy) | Guest network access only for a launch configured for online play |
| `EmbeddedContent.cs` (prepared copy) | Request 11 (online configuration), request 12 (read the profile file again) |
| `DnsBlacklist.cs` | A redirected host name is no longer refused as a Nintendo server |
| `DnsMitmResolver.cs` | Exact hosts-file entry, then the documented built-in rules, then wildcards and real DNS |
| `ManagerServer.cs` | The `id_token` gets Nextendo's key identifier and the claims `jti`, `hm`, `tv`, `nnex` |
| `SslManagedSocketConnection.cs` | The certificate of the two configured servers is accepted, for those two addresses only; SNI is the name last redirected there |

Everything is guarded by `EmbeddedOnline.Enabled`; without a configuration the
engine behaves as today.

Known limits of the lot: no ALPN is offered (enough for NEX over WebSocket;
NPLN titles need HTTP/2 and stay out of reach); nothing keeps the UDP NAT
mapping alive during peer-to-peer set-up, which Nextendo's own emulator does;
`nifm`'s network-interface queries have never run on an iPhone with guest
network access on; the token is built by the same JSON Web Token library as
today, whose behaviour under NativeAOT with the added claims is unobserved.
Online play also needs the exact game version Nextendo supports for each title.

To take the lot into a Core: move the adapter to `build-utils/melonx/` and the
C# file to `native/melonx/` mapped to `Ryujinx.HLE`, call the adapter last in
`prepare_embedded.py`, add it to `ORDER`, the plan and the contract, add its
gate, and freeze. That belongs to the Core's owner and is worth doing once the
maintainer has Nextendo's values, so the result can be tried against the real
servers.

## Original Switch menus

- **HOME menu.** Not possible with the pinned engine (MeloNX `13700519`). Its
  system-applet services are placeholders: `IApplicationCreator` has no command,
  `IHomeMenuFunctions` has two that do nothing. Ryujinx-Nextendo, which shows
  a HOME menu, implements those services (two and seven commands there) in
  source published under PolyForm Shield, which cannot be brought into
  RewindBox.
- **Mii Maker.** The pinned engine can start the firmware's Mii editor (the
  standalone MeloNX application offers "Launch Mii Maker"). RewindBox's launch
  path accepts game files only (Dart, the Swift bridge, the launch preflight and
  `EmbeddedPrepare` each check for a `.nsp`, `.xci`, `.nro` or `.nso` file), so
  offering it needs an engine and bridge change. Not done.

## Verification

Local, Linux x86_64. Flutter 3.47.2 (Dart 3.13.2), .NET SDK 10.0.100, MeloNX
`13700519`, RewindBox `b83935f0`.

- `flutter analyze` on the new Dart files: no issue. The two edited files keep
  the 20 informational notes they had.
- Local Dart tests, not added to the repository (no new test in the delivery
  path): 18 passed. JPEG encoder decoded back by Flutter at five qualities and
  an odd size; generated and imported pictures; the profile file's format,
  refusals and preservation; the whole Nextendo flow against a stand-in HTTP
  client (PKCE challenge, state, refresh rotation shared by two callers, expiry,
  game token, refusals, sign-out); both screens driven through their buttons.
- Existing Dart tests that open the Switch menu: 26 passed
  (`melonx_playlist_skins`, `melonx_import_completion`, `navigation512_switch`,
  `melonx_presentation_widgets`, `jit_backend_preference_service`).
- Engine: one `prepare_embedded.py` pass on a copy of pristine upstream (216
  prepared members), LibHac rebuilt by `build_libhac.py`. Control: `Ryujinx.HLE`
  builds. Candidate (adapter applied, digests matched): `Ryujinx.HLE` and
  `Ryujinx.Library` build, 0 errors. A harness on the candidate's assembly
  passed 102 checks: offline by default with the blacklist and the token
  unchanged; refused requests leave the engine offline; the documented rules
  through the real resolver and blacklist; the real token generator's header and
  claims; a clear returns everything to the default. The harness is kept as
  [evidence](evidence/melonx-online/README.md).

Not done: the Swift files were not compiled (no Apple toolchain here); no
NativeAOT build, no Core, no IPA; no request was sent to Nextendo's servers; no
TLS handshake was exercised; nothing was observed on a device.
