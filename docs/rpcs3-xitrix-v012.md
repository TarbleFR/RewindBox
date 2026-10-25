# RPCS3 selective XITRIX Preview 0.12 integration

Requested on 24 October 2026. Work started from Claude
`555603e541dc586b60d27cac28b38e62f7df12a0`; concurrent changes must be retained.
Only RPCS3 code, its acceptance checks and build/delivery evidence are changed.
No main update, tag or GitHub release is authorized.

## Exact starting components and provenance

| Component | Starting identity |
| --- | --- |
| Delivered Core | Host `a69860297d7b26dbb688df0daf16a31b42046462`, Actions `39982269326`, SHA-256 `cb2877b7558a589554c9c923b71f20129433c40654232ee706545dd7622da7cb` |
| RPCS3 source | XITRIX/rpcs3 `22f1152783cef1f7e04af7b1c895173e28fd5b03` plus canonical delta `388c5c37ed89c97d2b2aebd7642b611fd5a5ef2ed1d3c0cfa2be815357f66767` |
| Native bridge | Local CocoaPod 0.1.0, host source `555603e`, main Core ABI 30; optional NeoSwap interfaces remain ABI 1 |
| Renderer | Vulkan through pinned MoltenVK 1.4.2; FFmpeg 8.1.1 |
| JIT | LLVM `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` (22.1.8), pinned AArch64 GHC spill fix; passive dlopen and Core-owned sealed RX/RW arenas |
| Compiled ISA | Core uses `-march=armv8.4-a`; this is more restrictive than the arm64 Mach-O architecture label |
| Compared public source | [XITRIX/rpcs3 `8f7ca53`](https://github.com/XITRIX/rpcs3/commit/8f7ca53e72331e7d365776f6a21227ab9e45f986) |

The [release tag](https://github.com/XITRIX/RPCS3-iOS-Releases/releases/tag/v0.12)
contains a README, not a source snapshot of its complete app. The supplied
ARMv8-A IPA independently matches the release SHA-256
`cf1c76d062152daa26100f8b1290f8e2b151d811dcaf1864dd55f59db2c50773`.
Its Core build_info reports ABI 30, legacy/armv8-a and the same LLVM/MoltenVK/
FFmpeg versions, but its upstream string names August base `fdcfded8`, not
the complete October source. Exact release binary/source correspondence is
therefore unproven. The executable was inspected for identity only; no code
or framework was copied from it into RewindBox.

## Selected source changes

| Public commit | Selected change |
| --- | --- |
| [6e9c8e38](https://github.com/XITRIX/rpcs3/commit/6e9c8e3841a633711e2971d54822586a1d4a3e6c) | Preserve ISO parent entry `..`; trimming its final dot could cause recursive startup scans. Tests use our existing parser signature and LV2 directory ordering. |
| [0c416661](https://github.com/XITRIX/rpcs3/commit/0c416661fb4d096dac2d43c09b3510e33958073f) | PPU ARM64 far-jump stub takes its thread from GHC x20, calls the C helper and escapes to the host. Grown Vulkan rings receive dedicated ordinary memory; resource retirement still waits for the existing GPU lifetime. ARMSX3 attribution in the upstream patch is preserved. |
| [4ca7dc4](https://github.com/XITRIX/rpcs3/commit/4ca7dc4bfbf783141f0b3ca5c3fa0dd13b4d3648) | Fold fully specified constant NEON TBL1 masks and single-use nested tables. No shared expressions or guest memory operations move. Other reservation, timing and floating-point changes from this commit are excluded. New helper participates in the SPU object-cache codegen identity. |
| [f3d91587](https://github.com/XITRIX/rpcs3/commit/f3d91587e9d628e32468217da5224020a0d6ec71) | Check physical shader-interpreter limits, including MoltenVK extended sampler limits. Unsupported GPUs use synchronous recompilation for that renderer session; saved settings remain unchanged. |
| [15a318e3](https://github.com/XITRIX/rpcs3/commit/15a318e39afb5e5ad53f74bee268010f4c722523) | Omit a redundant clear of pooled color mipmaps only when the subsequent copies cover every complete mip. Partial, depth, missing-level and offset cases retain their clear. Transfer barriers remain. |

All selected engine code and upstream fixtures remain GPL-2.0-only.
Commit and path provenance is retained in `canonical-source.json`.
The source is regenerated as one canonical delta; historical patch chains
are not applied during CI.

The native host additionally checks CPU features **before the initializer's
early JIT escrow reservation, before prepareJit and before dlopen**.
Failed/unknown sysctl results reject the modern Core. The policy
distinguishes ARMv8-A from ARMv8.4-A; no ARMv8-A Core is bundled or falsely
selected. Older devices receive an explicit compatibility error without
deleting data. This does not add older-device support.

The early escrow guard is a host-only follow-up to Core source `407ea8f`.
The Core artifact keeps its original input identity: an exact, hash-pinned
reverse fixture proves that the initializer is its only subsequent host input
change, and every compiled engine input remains byte-identical. A separate
Apple SDK test executes the production initializer with real Foundation and
dispatch, controlled sysctl/escrow doubles, eight feature scenarios and a
pre-fix negative control. The complete bridge is then compiled into the IPA.

## Already present or excluded

- The nonblocking controller input API is already present: pad updates do not
  acquire the global boot/firmware mutex. Existing direct input is retained.
- Persistent relocatable SPU object caching, selected ARM64 lowering, the
  ARMSX3/RPCS3 SHUFB and branch-order fixes, Vulkan image-pool race fix,
  MoltenVK occlusion completion wait, fault-before-reservation ordering and
  measured VMA granularity already exist. They are not claimed as new.
- No wholesale core rebase, reservation-stride migration, experimental texture
  hashing omission or relaxed RSX synchronization is introduced.
- XITRIX Regular/Dual-mapping JIT selection is not imported: it replaces an
  allocator that already differs from our validated sealed arenas and helper
  protocol. Existing adaptive standard/expanded capacity and manual choice are
  retained. TrollStore is not added without an independently validated host
  route. StikJIT, LocalDevVPN and user choices stay intact; no internal VPN.
- No XMB, MetalFX interface effects, automatic reporting, visionOS components,
  frameskip UI or unrelated frontend changes. Existing per-game profiles and
  custom settings remain. MeloNX and all other engines are outside the delta.

## Validation and measurement limits

Local Linux execution: production ISO parser/enumerator and LV2 ordering
(14 cases plus failing old-condition control), CPU baseline/probe failures,
100 shader mode/limit cases, 374 complete/partial mip coverage cases, and
existing 30 SHUFB masks × 1024 inputs plus branch/diagnostic negative controls
passed. Portable cases ran with ASan/UBSan; the sandbox cannot run LeakSanitizer.
The generated canonical delta was independently applied on a pristine upstream
worktree; every materialized postimage matched the reviewed source bytes.

The [dedicated Actions campaign](https://github.com/TarbleFR/RewindBox/actions/runs/40039707148)
passed the actual AArch64 PPU stub (10,000 GHC-style entries and a
poisoned-context control), 68 emitted SPU mask pairs in batch/chained modes
against 8192 scalar results each, and actual LLVM pipeline checks. It then
compiled the modified Core for iPhoneOS. The downloaded artifact independently
passed the input-identity, binary-hash, architecture/export and static passive
load checks. Static direct ARM64 B/BL reachability (depth 16) is not an actual
device dlopen or boot test.
Unchanged authenticated Core 515 campaigns are reused by exact source hashes;
they are not reported as newly run.

The resulting Core is 76,976,960 bytes, ARM64/iPhoneOS, ABI 30, SHA-256
`f3662c28c835173389e41cd78b331cf350b8c2f03ae8a8041ca0112c24612e8b`.
Its host source is `407ea8f`; canonical patch SHA-256 is
`3f8dbbee3e228ed965aae750fcd95bddc13910c71fe279695aede05b60320a9a`.
Actual PPU/SPU cache identities are `9013390836efe46e` and `a601a98f20f30c80`
(previously `8f9b154eb34feabb` / `7c226c2359020e20`).

The production host initializer also passed its eight Apple SDK scenarios and
pre-fix negative control in native job `120711477329`, run `40040875173`.
That native job succeeded; its sibling delivery job was superseded. Subsequent
candidates reuse only the exact hash-matched native proof, not a claim that the
entire older delivery workflow succeeded.

### Observed native microbenchmarks

One macOS ARM64 runner, LLVM 22.1.8, emitted baseline/candidate kernels with
all prior table/reversal folds enabled. Twelve alternating rounds, first two
discarded; median of ten samples, each 500 × 8192 vectors. These are warmed
component kernels, not cold/warm game-cache measurements. No confidence
intervals were calculated; small batch differences are not established gains.

| Mask kind | Input mode | Before ns/vector | After ns/vector | Observed time reduction |
| --- | --- | ---: | ---: | ---: |
| 0 | independent | 0.355891 | 0.340500 | 4.32% |
| 0 | dependent chain | 2.029251 | 0.675237 | 66.72% |
| 1 | independent | 0.350586 | 0.353109 | -0.72% |
| 1 | dependent chain | 1.344162 | 0.675507 | 49.75% |
| 2 | independent | 0.336604 | 0.333827 | 0.83% |
| 2 | dependent chain | 2.000320 | 0.664230 | 66.79% |
| 3 | independent | 0.375717 | 0.379120 | -0.91% |
| 3 | dependent chain | 2.067093 | 1.334244 | 35.45% |

Full artifact IDs, hashes, methodology and limitations are retained in
[`evidence/rpcs3-v012-delivery.json`](evidence/rpcs3-v012-delivery.json).
No GPU timing, peak-memory reduction, game launch improvement or FPS gain is
established by these component measurements.

No physical iPhone or legal game image is available in this environment.
Cold/warm game startup, CPU/GPU time, frame regularity, stutters, peak memory,
pause/resume, real controllers, closure and second launch remain unverified
on device. Host policy fixtures and compiler-kernel timings do not establish
gameplay speed. Both PPU and SPU codegen identities change, requiring one
recompile; no user cache is purged or migrated by the integration.

For device comparison, use the same title/update, firmware, scene, saved
settings and thermal state in the previous and new builds. Capture separate
cold-cache and warm-cache sessions using the existing local JITPROF/SPUPROF,
COREPROF, JITMEM/JITPAGES and guest-frame diagnostics. Measure launch time,
PPU/SPU/RSX CPU windows, p95/p99 frame times, stutters and sampled maximum
footprint. Distinguish native progress-dialog frames from game frames. No
automatic telemetry or performance gain is claimed.

## Delivered build 520

[Actions run 40044710281](https://github.com/TarbleFR/RewindBox/actions/runs/40044710281)
succeeded for app source `91040ba37e3ab0f5aef01ce3dff18f079568f3ed`.
Both modified bridge translation units were compiled for iPhoneOS ARM64;
the source-built Core remains the independently verified `407ea8f` artifact.
The unchanged application components come from successful concurrent Build 519,
run `40043376467`, frozen source `f93323768831428186c3aeb21b7e7a6130897836`.
No MeloNX code was edited by this RPCS3 task.

The final IPA is 186,250,708 bytes, version 0.0.8 / build 520, minimum iOS 18.0,
SHA-256 `5625290ad436b8b06c5ab0fccec04163b8df27163c92e4dc0135aa0521f8a9e3`.
It was recovered unchanged from four hash-verified, source/run-bound Actions
transport artifacts. Independent checks passed for ZIP CRC, structure,
dependencies, original Core identity and signed payload fingerprint, embedded
runtime entitlements, and the compiled `early_jit_escrow_skipped` guard marker.
The distribution has one IPA, seven extensions and no internal packet tunnel
or VPN entitlement across the 87 inspected Mach-O images.

CI verified all 87 ad-hoc signatures and confirmed that signing preserved
compiled code/data and ABI metadata. The IPA still requires user re-signing
with SideStore; Apple provisioning, installation, launch and effective runtime
entitlements have not been verified on an iPhone. ARMv8.4-A remains required;
an ARMv8-A compatibility Core is not included. Existing PPU/SPU caches remain
on disk, but their new codegen identities require recompilation on first use.

Only `Claude` was updated. No main change, tag or GitHub release was made.
