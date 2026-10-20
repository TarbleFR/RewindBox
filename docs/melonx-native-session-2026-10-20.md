# MeloNX native session continuation

The embedded engine now has an owned session ABI, and the iOS host primitive
compiles against the iPhone SDK. This completes the lifecycle foundation after
the bootstrap milestone. The app's Switch route remains unavailable: the new
host sources are not registered as a Flutter plugin or included in Runner yet.

## Resulting ownership

The host passes borrowed UTF-8 strings, receives a positive session generation,
sets its retained CAMetalLayer and calls the synchronous run function on a
dedicated worker. Stop only signals the owner. The host reports the session
active and retains its layer until a clean run returns and its main-thread
completion executes. A quarantined run retains both its activity and surface
until process exit, including after the UI releases its host. Delayed stop/pause
calls carrying an earlier generation are rejected.

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

The final failure-path review strengthens quarantine: if guest termination
throws, GPU resources are retained, the render worker is joined and window
disposal is refused. Any failed execution retains remaining context/window
handles. Cleanup no longer falls through to freeing memory after an unproven
guest stop. The Swift host roots quarantined sessions for the process lifetime
and continues reporting active. The executable checks cover both refusal to
release unsafe resources and retention after the UI drops its last reference.

These changes affect the embedded fork. The host uses the new session ABI and
does not call the old standalone `main_ryujinx_sdl` entry point.

## Verification

| Evidence | Result |
| --- | --- |
| Engine source | `65f957e7278da94dee601d51e5c2265e64c60fdc` |
| Engine CI | [39510222541](https://github.com/TarbleFR/neostation-ios/actions/runs/39510222541), success |
| Engine artifact | `12304554717` |
| Artifact ZIP SHA-256 | `35a79c666657289e3ab4926f8a673f25192fddd379f3a257f9fab128a592be07` |
| Dylib SHA-256 | `7a37793779d5014d8686d34a9f6c7f9cddfcb5817372d6dd15b9b9d1dab882c5` |
| Dylib | 37,353,112 bytes; ARM64, iOS, MH_DYLIB; 22 required exports |
| Managed checks | 15 storage/initialization + 20 session/window ownership cases |
| Swift host source | `65f957e7278da94dee601d51e5c2265e64c60fdc` |
| Host CI | [39510222562](https://github.com/TarbleFR/neostation-ios/actions/runs/39510222562), success |
| Host artifact | `12304664296`; ZIP SHA-256 `1d63ae5ca340b740e01d81ede675f0aca5f93c6732681c53bc36f6ea705899a8` |
| Host checks | iPhone SDK type-check; 20 executable Swift/native ABI scenarios |

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
method fixes that scope error. The first successful engine run (39509076583, c49ef51) reused those
successful phases after comparing complete production/test inputs and .NET
identities. The final run reruns the 20 changed ownership cases for quarantine
retention and reuses only the unchanged 15 storage cases (host SDK 10.0.401,
runtime 8.0.32). The engine itself remains pinned
to SDK 10.0.100. LibHac's earlier reconstructed package and five layout tests
are reused with their existing proof. No unchanged emulator is rebuilt.

Host runs `39509076727` and `39509253111` failed an assertion in a test that
compared a borrowed game pathname to fixed C bytes. The harness now retains
failure diagnostics and checks Apple's URL pathname/Unicode semantics. The
initial 19 cases and SDK check passed on f04e265. The final hardened host
passes 20 cases on 65f957e; neither failed whole run is counted as passed.
The initial engine/host proof is preserved in
`docs/evidence/melonx-native-session-initial-2026-10-20.json`.

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
  Do not feed a live NeoSwap loan directly to upstream DonatedMemory: Offer and
  Withdraw erase its live-allocation ownership, after which shared-memory
  destruction falls through to `vm_deallocate`. The adapter must preserve broker
  ownership until all loans are retired; the existing six-owner ABI also has no
  dedicated MeloNX slot to reuse silently.

No firmware, key or game is bundled. No homebrew/game execution, firmware
installation, physical controller, on-device relaunch, NeoSwap behavior or
texture loading is claimed. No IPA/build number or public release was produced.
