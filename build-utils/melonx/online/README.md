# Nextendo online lot — handoff for the next MeloNX Core

Version 3 (15 November, after the MeloNX session's review of version 2): `wiring.patch` installs v3;
`v2-to-v3.patch` turns an applied version 2 into v3. Same files, same BASELINE, same plan entries. Changes:
- the session's request is taken by the configuration of the host session's first program
  (`HleConfiguration.Configure`, `UserChannelPersistence.PreviousIndex == -1`); a program the game starts in the same
  session (ExecuteProgram, RestartProgram: Library's load loop builds a new configuration) keeps it instead of going
  offline;
- while online, a refused or failed handshake on the default branch (any host other than the two servers) is also
  `ConnectionAbort` instead of an exception; offline, the default handshake is byte-for-byte the original behaviour;
- `Read`, `Write` and `GetServerCertificate` answer `ConnectionAbort` while online when no handshake succeeded (no
  `NullReferenceException` on a refused connection);
- the gate requires the fixture's six real handshakes (`handshakes == '6 handshakes'`, a runner without a local IPv4
  address fails) and its exact check count (`ONLINE_CHECKS`);
- an aborted launch cannot leave a request for a later one: the bridge sends operation 11 before every launch (`{}`
  offline), which replaces any armed request; documented in `EmbeddedOnline.cs`.

Review of v3 by the MeloNX session (15 November): freeze, no defect; the v2 probes pass. Known limits kept, shared
with upstream: an unsupported SSL version (`TranslateSslVersion`, NotImplementedException) or an ArgumentException
still leaves the handshake as an exception, so "never an exception" means the TLS and I/O failures listed above; the
handshake blocks without a timeout, and while online (DNS open) a silent host can hold the SSL thread.

Version 2 (after the review of version 1): a refused or failed TLS handshake to a configured server is the game's
connection error (`ConnectionAbort`); no reverse lookup for a missing SNI (refused); serverAuth is required of the
leaf; the game version is read only online; the exact hosts-file entry is compared without case. Not taken (documented
limits): roots bound per host (the guide does not say which root signs the NEX hosts), DNS limited to redirected names
while online. A homebrew launch never receives the token (app side, 1d1572027).

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
    tree, 154 checks on the candidate's production `Ryujinx.HLE` (pinned, six real handshakes required), seven
    post-images in the receipt.

## Left to the freeze

- `test/melonx_dma_core_contract_test.py`: composition 244 inputs / 227 members; `CHANGES` plus the six files
  (115); `productionAdditions` = {`src/Ryujinx.HLE/EmbeddedOnline.cs`} instead of empty; the two added inputs.
- Gates to run on the final preparation: nifm-network-watch (extended) and the gates that iterate `ORDER`; no
  other gate binds the lot's files (EmbeddedSession.cs is not touched).
- Core request (`[melonx-dma-core]`), pin, then the IPA that replaces MeloNX.

## Checked locally (Linux x86_64, .NET SDK 10.0.100)

- Unwired preparation of 030cc14f equals contract 1362352a exactly (242 inputs, 221 members); wired: 244 / 227.
- `Ryujinx.HLE` and `Ryujinx.Library` build with the lot, 0 errors.
- Extended nifm-network-watch gate on the wired v3 final preparation: passed (54 checks of its own, online fixture
  154 checks with six real handshakes, 9 post-images).
- Not done here: the other 108 gates, the NativeAOT/iOS build, the simulator sessions; nothing on an iPhone. TLS
  was exercised on Linux's stack only (iOS uses Apple's).
