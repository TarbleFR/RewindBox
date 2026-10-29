# Private test IPA 588 — RPCS3 runtime592 and MeloNX, 29 October 2026

The maintainer authorized the push on `Claude` and a private test IPA containing
the latest fixes for both engines. No public release is authorized.

Baseline: delivered private IPA587, source `cd7ed1e2`, run40789729450, tree
`fed8b77804738d471dc983853c2e1cd3f15ffb9c`. Its recorded product index is retained
with file modes; older delivery recipes, receipts and tests are not replayed.

## Components

- RPCS3 runtime source `9938d918`: early texture hits, normalized dynamic-state
  pipeline keys, bounded recent pipeline lookup, exact 1 GHz clock conversion,
  typed descriptor storage on demand and coalesced flush notifications.
  Core592 recipe source `27b5cc99a0763c0a2c3939bf6b6b0d022a1a026f`, run40800626294.
  Six new ARM64 native suites (three normal and three ASan/UBSan) passed before
  the single iPhone Core compilation. PPU/SPU codegen identities remain unchanged.
- MeloNX engine source `7be2a83b`, successful Apple run40794453036,
  artifact12864051465. Reused without another engine build. Contains the
  29 October CPU/JIT, GPU cache/upload/queue and controller changes documented in
  `melonx-engine-optimization-2026-10-29.md`. All 57 compilation input digests
  are retained, including the updated native gamepad lease.
- Other application product sources remain those of the delivered 587. The
  only changed product source path is `native/melonx/EmbeddedNativeGamepadLease.cs`.
  The other engines retain their existing binary pins, exports and resources.

## Delivery checks

The recipe builds the iPhone application once and reuses the successful MeloNX
artifact and unchanged native components. New Core592 and MeloNX588 receipts bind
the binaries to their exact compiled input maps and successful runs. Raw Core
identity is checked before signing; signed Core and MeloNX payloads are checked
against their verified originals afterward. Every executable is signed and
verified from the final ZIP. Legal notices and application/extension versions
are checked on the final IPA.

Delivered: private IPA588, source `4a20e8e9`, successful run40803513166,
artifact12867282283. IPA 188,291,408 bytes, SHA-256
`dfa8aa7a1d60e29226dbaa260cd12bf44a9a91510d4e25805ec6aaa0a1af9b70`.
Delivery took 601 s; the Xcode phase took 218.46 s and signing/export 36.10 s.
Exact receipt: `evidence/rewind588-delivery.json`.

Core592 run40800626294 completed successfully.
The Core is 77,232,008 bytes, SHA-256
`436830efb07b1204f57713dfd1ecd242d7f36bed3f55aea01a25cc0ff6a7a8ac`.
Its exact identities and artifact pins are in `evidence/rpcs3-runtime592-macos.json`.
The decrypted final IPA matches SHA256SUMS and the signed-payload receipt.
Its signed Core and MeloNX binary were independently compared with their
verified raw artifacts. All 85 Mach-O images pass the delivery signing/ABI checks.
No physical-device performance result is inferred. The IPA requires SideStore/Apple re-signing
for installation. No caches, saves or per-game settings are cleared.

First assembly run40802595865 stopped before Xcode because the MeloNX guard
expected JSON receipts for two tests that write only stdout. Their successful
official step is now authenticated directly. The complete actual engine archive
was then downloaded, SHA-256 checked and passed the production guard: both
binaries/platforms, 57 inputs, 12 source groups, seven JSON receipts and the
stdout-only pool/range step. See `evidence/melonx-engine588-archive.json`.
Both compiled engines are reused by the corrected assembly.

Static inspection of the exact linked Core confirms zero executed UDIV on
each 1 GHz path, two on each 24 MHz fallback path. This uses the preinstalled
LLVM20.1.2 disassembler, with no compilation or execution of the inspected code.
See `evidence/rpcs3-runtime592-linked-clock.json` and the accompanying `.txt`.

Next device comparison: the same restored God of War III, Assassin's Creed and
MeloNX scenes with the existing counters and retained caches. Host tests and
successful compilation do not prove additional FPS, RAM reduction or gameplay
compatibility on an iPhone.
