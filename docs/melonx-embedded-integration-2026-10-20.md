# MeloNX embedded integration — work in progress

The maintainer requests an in-process Nintendo Switch engine, its independent
playlist and imports, firmware/keys, original touch controls with editable
layouts, controllers, compatible HD content and a test IPA. The subsequent
instruction explicitly retires the external MeloNX entry. Work stays on Claude;
there is no authorization for a public release.

## Source audit

The inspected engine is `projects/MeloNX` at
`13700519f3abc4e6d7ed8a065b118b2cc59bcd67` on
<https://starforgejo.dev/projects/MeloNX>. Its iOS frontend is Swift/SwiftUI;
`src/Ryujinx.Library` compiles a .NET 10 NativeAOT ARM64 dynamic library.
It exposes native window, game start/stop, input, firmware and game-info APIs.
The renderer uses Vulkan through MoltenVK with a CAMetalLayer. The .NET runtime
being AOT-compiled does not remove the guest CPU's JIT requirement.

Relevant source boundaries:

| Concern | Inspected source | Integration consequence |
| --- | --- | --- |
| Core ABI | `src/Ryujinx.Library/Library.cs`, `UnmanagedPassthrough.cs` | Preserve exact struct layout, allocator ownership and callback lifetime. |
| Storage | `Library.Initialize`, Swift `RyujinxController` URL helpers | Upstream starts at Documents. Confine embedded state to Documents/MeloNX before initialization. |
| Session lifetime | `Library.Load`, `StopEmulation`, `WindowBase.Exit` | Input manager disposal and synchronous stop need a dedicated relaunch proof before enabling the engine. |
| Original touch controls | Melo-Controller revision `c049ce88a5635bddcd88e1965c42aa8fc92fe961` | Retain original controls; do not substitute generic buttons and call them original. Evaluate the common NeoStation editor adapter. |
| GPU dependencies | committed SDL3, MoltenVK and codec libraries | Confirm binary/source/license provenance and coexistence with the delivered engines before packaging. |
| JIT | dual mapping and the upstream universal protocol | Verify the NeoStation PID and mapping handshake; do not repurpose a helper that also initializes another core. |
| NeoSwap | donated-memory exports and upstream RamDonor | Use one ownership/budget contract; do not run two independent donor managers or claim virtual space as RAM. |
| Mods | README and per-title mod-loading code | DLC/updates are supported upstream. RomFS/ExeFS/runtime mods are not guaranteed. No Switch HD download is enabled by this work. |

## Licenses observed

The engine root `LICENSE.txt` contains the Ryujinx MIT notice, while the README
also describes MeloNX as GPLv3. Preserve both facts in the audit; do not silently
relabel the complete engine. The separately pinned Melo-Controller package has
a GPLv3 license. Upstream also names BSD libvpx and LGPLv3 FFmpeg. A root license
alone is insufficient evidence for all committed native dependency binaries.
No engine/dependency binary, firmware, key, commercial game, or texture pack has
been added to NeoStation by this phase.

## External integration retired

- Removed the external library exporter/cache loader and URL callback, launch
  Shortcut installer, external StikJIT target discovery and foreground handoff.
- Removed the settings synchronization card. Switch has an embedded-only seed
  and route; it never falls through to RetroArch, a URL or a share sheet.
- Existing `melonx://` metadata rows are retained. Launch asks the user to import
  the actual game file; it never guesses a local game from a title. Existing
  personal files, saves, artwork, playtime and cached exports are not deleted.
- The shared StikJIT pod retains the read-only LocalDevVPN route probe and the
  same source-built framework ABI. The three other engines' dedicated helper
  sources and scripts are unchanged. The previous dynamic FFI export list is
  retained as data for validating the unchanged framework, not as an app launcher.
- Packaging removes and rejects the retired `melonx`/`atariemulator` query
  schemes. Switch engine availability requires a native runtime report; a Dart
  route declaration is not treated as an installed engine.
- Failure and reimport messages are translated in all twelve languages. Switch
  session monitoring retains frontend audio ownership until native teardown
  explicitly reports false.

## Engine build attempts

`build-utils/melonx/source.json` pins the engine, controller and SDK. The focused
`melonx-core.yml` lane builds no other emulator and creates no release.

1. Run `39498866032`: source fetched and SDK installed; NativeAOT publish stopped
   at NETSDK1147 (mobile-librarybuilder missing). No binary produced.
2. Run `39499119399`: pin SDK resolution to 10.0.100 and install the workload;
   restore stopped at NU1101 for exact `Ryujinx.LibHac` 0.21.0-alpha.129 in the
   upstream-declared Ryulynx feed. No binary produced. Nuget.org only lists older
   versions; no API downgrade was substituted.
3. Run `39499844255`: try the original Ryujinx projects feed retained by the
   inspected MeloNX mirror `f925129209afd55927a0201d82285b8fa4b7ba30`, preserving
   the exact package version and source mapping. Result pending.

## Validation and remaining work

Local checks passed: protected library/native baseline (3 tests), bounded
LocalDevVPN route contract (5), embedded routing contract, unchanged dedicated
JIT source/patch fingerprints, and packaging parser tests (25, including refusal
of each retired query scheme). These are source/parser checks, not gameplay.
Focused Flutter/analyzer and iPhone SDK plugin checks are pending in
`melonx-integration.yml`; results will be recorded after execution.

The native embedded-session adapter, runtime packaging, game/firmware/key/DLC
imports, original-control/editor adapter, graphics settings and NeoSwap mapping
integration are not complete. No firmware installation, homebrew execution,
physical controller, on-device relaunch or HD mod loading is claimed. No build
number has been allocated and no test IPA has been produced for this task.
