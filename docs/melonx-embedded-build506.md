# Embedded MeloNX — test build 506

RewindBox's Nintendo Switch route loads the source-built MeloNX engine in the
host process. No separate MeloNX application or external launch URL is used.
The original Melo-Controller and layout editor are adapted to generation-bound
input; physical-controller mappings are saved per game. MeloNX has a separate
StikJIT helper, private MoltenVK, SDL and FFmpeg frameworks and a source-built
JIT mapping helper. The host reports success only after a presented Metal
frame and its JIT transaction complete.

Imports in the Switch playlist accept personal games, firmware and keys.
Native inspection identifies the title and validates update/DLC compatibility
before installing them into the engine's own layout. Firmware replacement is
recoverable after failure/interruption. The scan reads personal keys; previous
hardcoded decryption material is removed. No keys, firmware or games are shipped
or downloaded. Existing external virtual rows, play history and artwork are
preserved; their real games must be imported to launch in the embedded engine.

Per-game options expose the engine's internal resolution (0.5–2x), shader cache,
asynchronous shader compilation, VSync and bilinear/nearest/FSR/area filtering.
MetalFX is not exposed because its required native callbacks are not connected.

## Memory and textures

Host memory-budget tracking, texture recompression and the upstream host-mapped
memory manager are enabled. NeoSwap's existing RPCS3 integration is unchanged.
MeloNX's donated-memory Offer/Withdraw API resets ownership of live loans and
cannot safely receive a live NeoSwap allocation. This build deliberately does
not connect that API. No donated GiB, storage-backed Switch memory extension or
performance gain is claimed. A broker with explicit allocation/return ownership
and device pressure testing remains necessary before such integration.

Switch texture research remains research-only: no catalogue item is made
installable without a compatible format and target. Standalone PC texture
files are not advertised as Switch mods. RomFS/ExeFS mod loading exists in the
upstream engine, but no new installer is advertised without a verified payload.

## Verification limits

CI verifies the engine for iPhone and ARM64 simulator, Swift/Objective-C++ SDK
compilation, owned session and input teardown, firmware transactions with real
temporary files, the Flutter imports/settings route and the packaged framework
closure. ABI doubles and temporary firmware files are not commercial games.
Device rendering, audio output, physical controllers, two actual guest launches
and memory pressure remain physical iPhone tests. No gameplay or 120 FPS result
is inferred from compilation. Logs stay inside the application; no Jetsam/IPS
reports are required.

## Source and notices

Engine: https://starforgejo.dev/projects/MeloNX at
`13700519f3abc4e6d7ed8a065b118b2cc59bcd67`: root MIT notice retained;
the README separately declares GPLv3. Both declarations remain visible, and
RewindBox host modifications are distributed under its GPL-3.0 terms.
Melo-Controller: https://github.com/stossy11/Melo-Controller at
`c049ce88a5635bddcd88e1965c42aa8fc92fe961`.
The exact reconstructed LibHac source, native dependency pins, commands and
corresponding source archives accompany the Actions artifacts. Recipes and host
modifications remain in this repository. Original package byte equivalence for
the unavailable LibHac NuGet package is not asserted. Native dependency licenses
are extracted verbatim from their actual build-source archives and embedded
under Legal/MeloNX; upstream notices are also in assets/legal/melonx.
This test build creates no GitHub release or tag and does not modify main.
