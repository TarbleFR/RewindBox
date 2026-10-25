# RPCS3 memory audit — Build 508 assembly

This candidate integrates the attached ARM64/iOS audit on top of Claude
`741918e1`, retaining the delivered507 motion and the concurrent Switch library
corrections. The new MeloNX library ABI2 engine, its host and its Flutter/SDK
checks must succeed at their exact pinned sources before assembly. The five
private dependencies remain from506; the old ABI1 library engine is not used.
Startup, catalogues and the remaining engines retain their validated sources. The only changed host product inputs
are the shared NeoSwap compiler coordinator and RPCS3's optional binder/log
admission. Core ABI 30 and the existing allocator/relay/storage ABIs remain.

The F1–F9 implementation and research limits are mapped in
`rpcs3-memory-audit-2026-10-23.md`. Direct bounded object loading, validated
buffer reuse, measured compiler admission, in-phase observations, data-only
free-page advice, reservation fault ordering and small-heap VMA granularity are
in the canonical source delta. Arena capacities and existing LLVM feature and
pipeline choices remain. The minimal-object linker is tested research code;
the production SPU translator does not invoke it. Further hot-block NEON
rewrites and capacity tuning require actual title/device evidence.

The immutable Core candidate is built separately by the memory-audit workflow.
Final assembly must require its successful exact source, patch, binary, recipe,
native acceptance inputs, passive initialization and new optional export. Its
artifact identity is never normalized or rewritten. The package adds
`RPCS3-memory-audit-identity.json`, binding the compiled payload before signing
to that source artifact. The final signed IPA must retain the same code/data
and ABI fingerprint and contain the shared broker and optional binder.

Existing Build 507 Flutter/native motion evidence is reused only after exact
source comparison. The final Xcode Release build compiles the changed native
host. All prior engine, lazy loading, license, entitlement, distribution,
catalogue and signing gates remain. The original motion package validator now
accepts an explicit build number, defaulting to its original 507.

No physical game session, measured FPS/RAM gain or device relaunch is claimed.
Internal app logs JITMEM/JITPAGES/JITCPU/VMAHEAP support the audit's suggested
cold/warm/second-title comparisons. The app still requires Apple signing for
installation with SideStore. No main change, public release or tag is made.

Build 508 is delivered and independently verified. Source
`e44b0d34bcca18a193793704ca01db1eccf819a4`, tree
`24106680143456f7572ad406805b2789f9e12f1a`, completed the checks, native-source
and Release device jobs in [run 39880551632](https://github.com/TarbleFR/RewindBox/actions/runs/39880551632).
The decrypted IPA is version 0.0.8 (508), requires iOS 18.0, and contains
186,077,551 bytes. Its SHA-256 is
`17431aedb8ee3c87f7b868d9a59db2944be783a681250d1606b71c3505198ab6`.
The machine-readable receipt is `evidence/rpcs3-memory508-delivery.json`.

Independent verification checked 83 compiled Mach-O payloads against the final
package identities; CI verified 86 ad hoc signatures. The new RPCS3 Core,
shared compiler broker and optional binder are present. Its compiled payload
fingerprint matches the successful Core source/run without rewriting the
original artifact identity. The 38 other emulator payloads and five private
MeloNX dependency payloads remain identical to Build 506. The current MeloNX
ABI2 engine and concurrent Switch library fixes are included. Final motion
assets, notices, native channels and compiled Dart checks also passed.

The final IPA still requires Apple re-signing with SideStore. Physical
installation, game sessions, relaunch behavior and FPS/RAM measurements remain
unverified. The minimal-object SPU linker remains disabled in production.
Main, releases and tags were not changed.

Broad touch/cheat bridge path triggers reuse their existing proofs only for the
closed `[rpcs3-memory508]` integration. The delivery gate proves every original
command is retained and only that job condition differs; manual runs still
execute. Product-source closure proves the touch/cheat/UI inputs are unchanged.
