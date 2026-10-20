# MeloNX native session continuation

The embedded engine now has an owned session ABI, and the iOS host primitive
compiles against the iPhone SDK. This completes the lifecycle foundation after
the bootstrap milestone. The app's Switch route remains unavailable: the new
host sources are not registered as a Flutter plugin or included in Runner yet.

## Resulting ownership

The host passes borrowed UTF-8 strings, receives a positive session generation,
sets its retained CAMetalLayer and calls the synchronous run function on a
dedicated worker. Stop only signals the owner. The host reports the session
active and retains its layer until run returns and its main-thread completion
executes. Delayed stop/pause calls carrying an earlier generation are rejected.

The adapted WindowBase stops input updates, terminates the guest while GPU
service remains available, ends and joins rendering, then releases resources.
GPU destruction executes on the render worker when that worker exists. Failed
loading before rendering has a separate owner cleanup path. A partial failure
quarantines execution instead of starting a second game over unknown handles.
A stuck worker keeps ownership; there is no timeout followed by unsafe release.

The adapter removes repeated context disposal, keeps the input drivers alive
across clean sessions, withdraws live controls before cleanup and recreates
per-game pad bindings. The bootstrap's FS/ARP/BCAT servers are reused instead
of abandoned on each game. Native touch snapshots use a concurrent dictionary.
The simple new API avoids the upstream OptionsNative allocation/free mismatch.
Required mobile defaults are explicit because CLI attributes do not initialize
properties on `new Options()`.

These changes affect the embedded fork. The host uses the new session ABI and
does not call the old standalone `main_ryujinx_sdl` entry point.

## Verification

| Evidence | Result |
| --- | --- |
| Engine source | `c49ef51a488f30fc9a79aecb18dd0127fa439f80` |
| Engine CI | [39509076583](https://github.com/TarbleFR/neostation-ios/actions/runs/39509076583), success |
| Engine artifact | `12305056007` |
| Artifact ZIP SHA-256 | `dac395b9fb9443682cfc7ba1e5a6484ada421fe956cdcd5cabfd32d8022407b0` |
| Dylib SHA-256 | `93e5e57f4da8ff64688a529d33b2526542826661440cbc3bc0f97d4fd82e6b71` |
| Dylib | 37,353,112 bytes; ARM64, iOS, MH_DYLIB; 22 required exports |
| Managed checks | 15 storage/initialization + 20 session/window ownership cases |
| Swift host source | `f04e265ffb5d0fe573aba4dd891e7393ef6bb70e` |
| Host CI | [39509399261](https://github.com/TarbleFR/neostation-ios/actions/runs/39509399261), success |
| Host artifact | `12304433388`; ZIP SHA-256 `cdeb9c3b3ca6037d120faf8d8d6d7a6b0999c93713252fcd4fca06ec4a6ad6df` |
| Host checks | iPhone SDK type-check; 19 executable Swift/native ABI scenarios |

The downloaded engine ZIP, dylib hash, Mach-O platform/install name and all 22
exports were independently parsed. Every current adapted native input matches
the compiled receipt. The downloaded host receipt also matches its current
Swift/header/test inputs. Full evidence is in
`docs/evidence/melonx-native-session-2026-10-20.json`.

The production managed ownership classes execute with deterministic fake
workers. Cases cover concurrent reservation, stop before run, stale commands,
paused stop, render/input/guest/GPU cleanup exceptions, joining before release,
refusal to dispose live workers and repeated clean generations. The Swift host
executes against a small compiled C ABI double on macOS. Its cases cover missing
symbols/incompatible ABIs, borrowed Unicode paths, pause, overlap rejection,
stop completion, layer retention, relaunch and quarantine diagnostics. They do
not execute the actual emulator, UIKit presentation or guest code on a device.

Run `39508485894` passed the 15 and 20 managed cases, then failed at C# CS0103
because WindowBase referenced a private Library field. An internal withdrawal
method fixes that scope error. The successful engine run reuses only those
successful phases after comparing complete production/test inputs and .NET
identities (host SDK 10.0.401/runtime 8.0.32). The engine itself remains pinned
to SDK 10.0.100. LibHac's earlier reconstructed package and five layout tests
are reused with their existing proof. No unchanged emulator is rebuilt.

Host runs `39509076727` and `39509253111` failed an assertion in a test that
compared a borrowed game pathname to fixed C bytes. The harness now retains
failure diagnostics and checks Apple's URL pathname/Unicode semantics. The
final 19 cases and SDK check pass; neither failed whole run is counted as passed.

## Work required before activation

Eleven committed ARM64/iOS dependency binaries have been inspected without
copying them into NeoStation. Their hashes, IDs, versions, strong/weak imports,
adjacent license files and inspected source inputs are recorded in
`docs/evidence/melonx-native-dependencies-2026-10-20.json`.

- The supplied MoltenVK has a **strong** import of
  `/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit`. Its iOS load
  compatibility needs resolution; a platform tag alone does not prove loading.
- FFmpeg's source resolver requests versioned dylib names, while the committed
  binaries identify themselves as frameworks. Add an explicit isolated resolver
  and resolve their dependency closure. Identify corresponding build-source and
  license provenance before delivery; the engine's source pin only identifies
  where those binaries were committed.
- The native driver's `GetGamepad` returns its actual shared pad. The upstream
  configuration method disposes that object, whose Dispose marks it disconnected.
  Fix this ownership before activating original controls and validate it with the
  actual production driver. Late input must also carry the session generation.
- Adapt the pinned original Melo-Controller controls/editor, then connect a
  dedicated JIT transaction to NeoStation's own PID and verify its mapping
  handshake. The upstream blanket SIGTRAP handler must not overwrite the other
  embedded engines' handlers.
- Complete Flutter registration, native dependency packaging, keys/firmware and
  game/update/DLC imports, graphics settings and the shared NeoSwap ownership
  contract. Preserve the established engine/helper identities and personal data.

No firmware, key or game is bundled. No homebrew/game execution, firmware
installation, physical controller, on-device relaunch, NeoSwap behavior or
texture loading is claimed. No IPA/build number or public release was produced.
