# Nextendo online lot — handoff for the next MeloNX Core

Version 2 (15 November, after the MeloNX session's adversarial review of version 1): `wiring.patch` now installs
v2; `v1-to-v2.patch` turns an applied version 1 (adapter, `EmbeddedOnline.cs`, fixture) into v2 for a freeze that
already took v1. Same files, same BASELINE, same plan entries. Changes: a refused or failed TLS handshake to a
configured server is the game's connection error (`ConnectionAbort`) instead of an exception through the service;
no reverse lookup for a missing SNI (refused); the host's request belongs to the next session only
(`EmbeddedOnline.BeginSession` from the session's `HleConfiguration`); serverAuth is required of the leaf; the game
version is read only online; the exact hosts-file entry is compared without case. The fixture adds the one-shot
session, the largest token (id_token under 0xC00) and four real handshakes through `SslManagedSocketConnection`
against a local TLS server (accepted with ALPN http/1.1 and SNI from the redirected name; refused for another host,
another root, no host name). Extended nifm-network-watch gate on the v2 final preparation: passed (54 + 146
checks, 9 post-images). Not taken here (documented limits): roots bound per host (the guide does not say which root
signs the NEX hosts), DNS limited to redirected names while online. A homebrew launch never receives the token (app
side, 1d1572027).

Source only until a Core freeze takes it. Owner of the freeze: the MeloNX session (single freeze, all gates run
there). Nothing here is read by `prepare_embedded.py` or the Core contract as committed.

## Contents

- `adapt_nextendo_online.py`: the adapter (BASELINE = the bytes the Core 030cc14f preparation leaves).
- `../../../native/melonx/online/EmbeddedOnline.cs`: the engine class (namespace `Ryujinx.HLE`).
- `wiring.patch`: everything the freeze needs on the committed tree, checked with `git apply --check`:
  - moves the adapter to `build-utils/melonx/` and `EmbeddedOnline.cs` to `native/melonx/` (mapped to `Ryujinx.HLE`
    in `prepare_embedded.py`'s native copy);
  - `prepare_embedded.py`: import, call last (after `adapt_queued_variant_record`), input list;
  - `test/melonx_adapter_control.py`: `adapt_nextendo_online` last in `ORDER`;
  - `dma-core-plan.json`: two added preparation inputs, six production changes
    (`HleConfiguration.cs`, `ManagerServer.cs`, `DnsMitmResolver.cs`, `DnsBlacklist.cs`,
    `SslManagedSocketConnection.cs`, `EmbeddedContent.cs`), one production addition (`EmbeddedOnline.cs`), the
    fixture input, and the nifm-network-watch gate's seven new required post-images and `onlineFixturePassed`;
  - `test/melonx_nifm_network_watch_test.py` + `test/melonx_nifm_network_watch/Online.cs`: the existing network gate
    also binds this lot (no new gate): control = final preparation with the lot reversed, fail closed on an adapted
    tree, 135 checks on the candidate's production `Ryujinx.HLE`, seven post-images in the receipt.

## Left to the freeze

- `test/melonx_dma_core_contract_test.py`: composition 244 inputs / 227 members; `CHANGES` plus the six files
  (115); `productionAdditions` = {`src/Ryujinx.HLE/EmbeddedOnline.cs`} instead of empty; the two added inputs.
- Gates to run on the final preparation: nifm-network-watch (extended) and the gates that iterate `ORDER`; no
  other gate binds the lot's files (EmbeddedSession.cs is not touched).
- Core request (`[melonx-dma-core]`), pin, then the IPA that replaces MeloNX.

## Checked locally (Linux x86_64, .NET SDK 10.0.100)

- Unwired preparation of 030cc14f equals contract 1362352a exactly (242 inputs, 221 members); wired: 244 / 227.
- `Ryujinx.HLE` and `Ryujinx.Library` build with the lot, 0 errors.
- Extended nifm-network-watch gate on the wired final preparation: passed (54 checks of its own, online fixture
  135 checks, 9 post-images).
- Not done here: the other 108 gates, the NativeAOT/iOS build, the simulator sessions; nothing on an iPhone. TLS
  was exercised on Linux's stack only (iOS uses Apple's).
