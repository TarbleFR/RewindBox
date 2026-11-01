# Hogwarts Legacy: JIT liveness, GC diagnostics and private IPA609

1 November 2026. Game: Hogwarts Legacy `0100F7E00C70E000` (1.0.5); target
device: iPhone 16 Pro Max. Branch `Claude`. This report separates established
facts, remaining hypotheses and what still needs a physical-device run.

## 1. Verified starting point

- HEAD `68a45ef` and delivered 608 (`90a9e8f`, IPA `575321ba…`) matched their
  receipts.
- Preparing HEAD on the pinned upstream `13700519` reproduces **exactly** the
  125 inputs and 163 prepared members of Core `ae78b4b`:
  `embedded-inputs.json` is `c36ae921…`, the value in the compile proof of run
  41239330287 (iPhone dylib `a1a0068d…`, packaged fingerprint `66124c2a…`,
  verified in IPA608).
- No `Diagnostics/Switch/MeloNX-*.log` newer than Build 604 is available (the
  repository holds only the sanitized 604 excerpt; the Desktop Commander
  device was offline). **No new physical measurement exists.**

### State matrix before this work

| Change | Source | Prepared | Compiled (`ae78b4b`) | Embedded 606–608 | Activation | iPhone |
| --- | --- | --- | --- | --- | --- | --- |
| V31, TBX, modulo-32 register lists | yes | yes | yes | yes | always | 604: ~198 s without a crash, inconclusive |
| Guard context (last guest dispatch) | yes | yes | yes | yes | on a fault | not observed |
| Occlusion (lot 1), batching (lot 2) | yes | yes | yes | yes | Hogwarts default, can be disabled; re-derived from the launched content | not measured |
| JIT reservation 1024→512 MiB, 64 MiB steps (lot 3) | yes (helper + Core) | yes | yes | yes | only on an explicit `_M` refusal | refusal never observed |
| Unreal profiles (lot 4) | yes | — | — | yes | OFF by default | loading not proven |
| Depth readback, small mips (lot 5) | yes | yes | yes | yes | always | black textures not rechecked |
| Cache pacing, CounterCache, single dependency, 606 diagnostics | yes | yes | yes | yes | always | no journal |

Option chain verified in source: `MeloNXHogwartsGraphics.resolve` →
`prepareGraphics` (drops `donateMemory`/`showRamGraph`) →
`neostation_melonx_configure_graphics` → `InitializeEmulationContext`
(`EmbeddedIsHogwarts` re-reads the launched title) →
`SynchronizeOcclusionReports` and `RelaxQueryFlushing`.

## 2. Stability: demonstrated and corrected JIT defects

LightningJit keeps guest registers in host registers inside a translation
unit. Its prologue, its reload after a host call and its epilogue transfer only
what the masks declare live. Three metadata defects for the guest profile
(**Cortex-A57: ARMv8.0 + AES/SHA1/SHA256/PMULL/CRC32**) lose guest state:

1. **FMOV (general) was marked as writing NZCV** (`InstFlags.S`). FMOV never
   changes the flags. A `B.cond`/`CSEL` after an FMOV at the start of a unit
   or after a host call read the host flags, and the epilogue copied those
   arbitrary flags back into the guest context. General FMOV is one of the
   most frequent floating-point instructions in compiled code.
2. **Missing destination read** on 41 ARMv8.0 entries:
   SMLAL/SMLSL/UMLAL/UMLSL (vector and by element), SQDMLAL/SQDMLSL,
   SSRA/USRA/SRSRA/URSRA, SABA/UABA/SABAL/UABAL, vector ORR/BIC immediate,
   AESE/AESD, SHA1C/M/P/SU0/SU1, SHA256H/H2/SU0/SU1; plus FMOV `Vd.D[1], Xn`
   (keeps `Vd<63:0>`). The MOVI entry captured ORR-immediate words and the BIC
   entry captured MVNI/vector FMOV; constraints return them to their exact
   entries.
3. **16-bit by-element forms**: the architecture limits `Vm` to `Rm<3:0>`
   (bit 20 is the index bit `M`); the mask used 5 bits and named `V(16+m)`
   for odd indexes.

Fix: `build-utils/melonx/adapt_register_liveness.py` (table and
`RegisterUtils`; no emitted instruction changes). Instructions beyond ARMv8.0
are rejected by the A57 profile and left unchanged.

Executable evidence (real sources: A57 decoder, masks,
Block/MultiBlock/DataFlow, context transfer methods and the ARM64 assembler;
emitted words decoded independently; the ARM64 code itself is not executed):

- `test/melonx_register_liveness_test.py`: 3,200 cases, 11,614 checks,
  **2,204 defects reproduced on the delivered Core**, 672 unchanged controls,
  6 decode identities, and **6 cross-unit scenarios** that lose the guest
  value with the delivered Core and keep it after the fix (CSEL after FMOV,
  flags after an FMOV-only unit, USRA, MLA lane 1, ORR immediate,
  FMOV `D[1]`).
- `test/melonx_register_liveness_audit.py` (optional independent Capstone
  6.0.0a4 oracle): 26,511 encodings including 18,143 ARMv8.0; 53 corrected
  findings, 32 pre-existing conservative reads unchanged, **0 unexplained
  difference**. Reports: `docs/evidence/melonx-register-liveness-20261101/`.

Limits: these defects can produce wrong branches, wrong vector values and,
by propagation, accesses to invalid addresses. **They are not proven to cause
the `InvalidMemoryRegionException`** (a write to an unmapped guest page, at
page offset 3).

Unchanged: the guard page (still fatal; nothing is hidden) and stop/relaunch
(the CI smoke still runs two sessions with distinct generations and backing
release). A diagnostic for the exact host PC of the fault was studied and
rejected: it would change the ABI of the native signal handler that runs on
every tracking fault.

## 3. Performance

Without a 606+ journal, no FPS fix can be chosen by frequency × cost. The most
visible 604 cost remains `.NET_BGC` at ~50 % of one core. To decide the Build
575 hypothesis (GC "high memory load" mode caused by a device-wide memory load
measurement), every 5 s sample now adds: generation, kind
(background/blocking), compaction and promoted bytes of the last collection,
**GC-observed memory load, high-load threshold, available memory**, and the
indexes of the last background and full blocking GCs. No GC setting, budget
or hot path changed. Bench: 108 runtime checks, 0 bytes allocated on the hot
path, maximum payload 2,784/4,000 characters.

Simulator fact (Core run, not the iPhone): the threshold is 99 % of available
memory (7.44/7.52 GB), so `HighMemoryPercent=99` is applied by the NativeAOT
binary.

## 4. Graphics and Unreal

No reproducible black-texture case is available, so nothing changed. For
Unreal, the game reads the RomFS image itself: proving that `UserEngine.ini`
is loaded requires observing the ranges read from the image composed by
`ModLoader.ApplyRomFsMods`. That instrumentation is not part of this work.

## 5. Compilation and delivery

| Item | Reference |
| --- | --- |
| Core | source `1f12796`, run 41323968050 / job 124899905807 (success, 11 min); artifact 13090479414, 88,300,108 bytes, `83827a94…`; iPhone dylib `34fb7a5c…` (37,732,912 bytes), simulator `669adbd0…`; packaged fingerprint `c43a80bf…` |
| Core contract | `build-utils/melonx/liveness-core-contract.json` (`4e899e79…`): 126 inputs, 163 members, 3 production changes, 5 fresh gates, 31 reused proofs, 44 historical receipts |
| IPA recipe | `.github/workflows/rewind609-hogwarts-liveness-delivery.yml`, a verified transformation of the 608 recipe; scope `build-utils/rewind609-source-scope.json` |
| Retained from 608 | RPCS3 607 (`7289ce4e…`), Dolphin (`640e4389…`) and ARMSX2 (`fab55193…`) from `0279198`, libretro, MeloNX native dependencies; Flutter/native test evidence from `0279198` (not re-executed) |
| Recorded failure | run 41325670644: `preflight` stopped because the 608 run now shows a failed attempt 2 created after the delivery (attempt 1); fixed by authenticating the pinned attempt |

## 6. Delivered IPA609

**Delivered and independently verified:** RewindBox 0.0.8 (609), private IPA.

| Item | Value |
| --- | --- |
| File | `RewindBox-609.ipa`, 189,813,193 bytes, SHA-256 `7908d1283f722e6b8ed7999c374aab073736740a4cb9f0ce588468bf95620f97` |
| Producer | source `3d92f19ee9c1e37d0813bc4a44a775923ccc2f5a` (tree `5b8090c5…`), run 41325785563 attempt 1: preflight job 124905314379 and application job 124905435858, both successful; 10 min 22 s end to end, Xcode phase 217 s |
| Toolchain | Flutter 3.47.2, Xcode 26.3 (17C529), iOS SDK 26.2, macOS 15.8.2, CocoaPods 1.17.0, identical to 608 |
| Receipts | [delivery](evidence/rewind609/delivery.json), [downloaded-file checks](evidence/rewind609/download609-verification.json), [CI IPA validation](evidence/rewind609/rewind609-ipa-validation.json), [signatures](evidence/rewind609/signature.json), [signed payload identity](evidence/rewind609/signed-payload-identity.json), [compiler log review](evidence/rewind609/warning-review.json) |

The CI job authenticated delivered 608, the new Core producer with its five
fresh gates and runtime evidence, and the retained producers. It rebuilt the
full application, then checked the packaged MeloNX exports, all 90 signed
images, the retained RPCS3/Dolphin/ARMSX2 payloads against 608, the legal
bundle and the eight bundle versions.

The four encrypted transport parts were downloaded separately. Their ZIP
digests match the API, and they reassemble to the manifest payload. The
private key matches `build-utils/delivery-609-recipient.pem`; decryption
produced 25 safe regular files. The IPA matches its `SHA256SUMS`, the signer
receipt and the CI validation receipt, and passes ZIP/CRC checks. Offline
checks confirmed eight bundles at 0.0.8 (609), the exact 90-image inventory
and the packaged identity. The MeloNX Core has normalized fingerprint
`c43a80bf…` and the iPhone dylib `34fb7a5c…`. RPCS3, Dolphin and ARMSX2 equal
608, and the MeloNX JIT helper equals the source. All six offline validators
pass: MeloNX, NeoPlay, shaders, legal, no-KartPad and no-Dusklight. The
private key was deleted after verified delivery. Linux did not reproduce
Apple's codesign cryptography, and SideStore re-signing is still required.

**Images that differ from 608:** 86 of 90 images keep their 608 code/data
fingerprints. `MeloNXCore` is the intended change. `Runner` carries the
Apple-generated `PROJECT:Runner-609` version string. `armsx2_internal_bridge`
and `libretro_internal_bridge` also differ, although `lib/`, `ios/`,
`packages/`, `assets/` and pubspec are byte-identical to 608 and the toolchain
is the same. No build number, commit or date string is present in them. The
cause is **not identified**: the 608 binaries are not available here for a
section comparison. `melonx_internal_bridge` and `dolphin_internal_bridge`
are unchanged.

The Xcode log has one `BUILD SUCCEEDED` marker and no errors. Every
repository-owned warning listed for 608 is still present verbatim,
including the four existing `NPMuxer.swift` concurrency warnings. The
application sources are unchanged, so these warnings are retained, not fixed.

### State matrix after this work

| Change | Source | Prepared | Compiled (`1f12796`) | Embedded 609 | Activation | iPhone |
| --- | --- | --- | --- | --- | --- | --- |
| A57 register/NZCV liveness | yes | yes | yes | yes | always | not tested |
| GC memory-load diagnostics | yes | yes | yes | yes | every 5 s sample | not tested |
| All rows of the earlier matrix | unchanged | unchanged | yes (same inputs) | yes | unchanged | unchanged |

## 7. iPhone test protocol

Same device, Hogwarts 1.0.5, same save and settings:

1. cold launch after installation, then a warm launch;
2. menu, cutscene, then the same playable section for at least 10 minutes;
3. return to the RewindBox menu and relaunch;
4. provide `Diagnostics/Switch/MeloNX-core.log`, `MeloNX-launch.log`,
   `MeloNX-performance.log`, `MeloNX-stderr.log` and their `.1` files.

Read: FPS and frame time, `managed.collections` and `lastGcMemoryLoadBytes`
against `lastGcHighMemoryLoadThresholdBytes`, `.NET_BGC` CPU, phases and
waits, startup traces (any ~60 s GPU wait), and any guard exception with its
context.

Interpretation:

- If `lastGcMemoryLoadBytes` stays at or above the threshold while gen2
  collections and `.NET_BGC` CPU rise, the GC "high memory load" hypothesis
  is supported. If it stays well below the threshold, that hypothesis is
  rejected and allocation volume becomes the next suspect.
- A guard crash after this build would still carry `lastGuestDispatch`. The
  liveness fixes would then be excluded as a sufficient fix, though they
  remain valid corrections.
- A session without a crash is an observation, not proof: the 604 session
  already ran ~198 s without a crash, which was inconclusive.

## 8. Remaining work

- Unreal: a RomFS read-range monitor around the storage that
  `ModLoader.ApplyRomFsMods` builds, to prove that `UserEngine.ini` is read.
- Black textures: needs a reproducible scene with a journal before any change.
- Performance: choose the next fix from 609 journals by frequency × cost.
- `armsx2_internal_bridge`/`libretro_internal_bridge` rebuild differences:
  compare sections against a retained unencrypted build of identical sources.
