# Modifications made by RewindBox to the engines it ships

RewindBox (an independent iOS/iPadOS fork of NeoStation, maintained by TarbleFR)
ships the engines below **modified**. As their licences ask (GPL-2.0 section
2(a), GPL-3.0 section 5(a), Apache-2.0 section 4(b), MPL-2.0 section 3), this
notice states that RewindBox changed them, when, and where the changes are.
Each engine keeps its own licence and authors (see THIRD_PARTY_NOTICES.md and
the engine folders of this Legal directory); these changes do not imply any
endorsement by the original authors. The changes were made in 2026, from
August onwards, and are published in https://github.com/TarbleFR/RewindBox;
docs/SOURCE_CODE_ACCESS.md and docs/ENGINE_CORRESPONDING_SOURCES.md there
describe how to obtain the corresponding source.

| Engine (licence) | Upstream and revision the changes apply to | RewindBox's changes (repository paths) |
| --- | --- | --- |
| Dolphin / DolphiniOS (GPL-2.0-or-later) | https://github.com/OatmealDome/dolphin-ios at `7cac54161659421ed95c2cd1c0b0746539a4cd38` | Embedding as DolphinCore.framework and its host integration: `build-utils/patch_dolphin_internal_core_v2.py`, `build-utils/patch_dolphin_build267_account.py`, `packages/dolphin_internal_bridge` |
| RPCS3 (GPL-2.0) | XITRIX/rpcs3 at `22f1152783cef1f7e04af7b1c895173e28fd5b03` | iOS JIT, memory, Metal/Vulkan presentation and embedding in libRPCS3Core: `build-utils/rpcs3/*.patch`, `build-utils/rpcs3/canonical-source.json` (also an LLVM AArch64 GHC patch, `llvm_aarch64_ghc_patch` there), `packages/rpcs3_internal_bridge` |
| ARMSX2 (GPL-3.0) | https://github.com/ARMSX2/ARMSX2.git at `9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe` (iOSv2.6.0) | Embedding in ARMSX2Core.framework: `build-utils/armsx2/neostation-core.patch`, `packages/armsx2_internal_bridge` |
| MeloNX (MIT notice and GPL-3.0 declarations, see Legal/MeloNX) | https://starforgejo.dev/projects/MeloNX.git at `13700519f3abc4e6d7ed8a065b118b2cc59bcd67` | Embedding in MeloNXCore.framework, iOS GPU, audio and memory adaptations: `build-utils/melonx/` (the `adapt_*.py` source adapters and build scripts), `packages/melonx_internal_bridge`; the standalone MoltenVK patch is in Legal/MeloNX/StandaloneMoltenVK |
| XeniOS (BSD-3-Clause) | https://github.com/xenios-jp/XeniOS.git at `5533fbfd19d45f32b40283de2382e7f54248bea9` | Embedding in XeniaCore.framework: `build-utils/xenia/rewindbox-core.patch` and the facade `packages/xenia_internal_bridge/core` |
| S2Arm (Apache-2.0) | S2Arm at `6b6a571553f7a687af46e03e2cdbf8ef4d77f335` | iOS embedding patches `build-utils/s2arm/engine/patches/*.patch` (and the preparation library's series, docs/s2arm-legal-notices.md), `packages/s2arm_engine_bridge`; RewindBox's notice is Legal/S2Arm/RewindBox-S2Arm-NOTICE.txt |
| StikJIT (MPL-2.0 for its own files) | https://github.com/StikDebug/StikJIT.git 1.9.0 at `32287268fa5824f9edce4cb359f5833ce0cf7b00` | Full-width JIT address transport and compatibility changes: `build-utils/patch_stikjit_rpcs3.py`, `build-utils/patch_stikjit_compat.py` |
| Nestopia (libretro, GPL-2.0-or-later) | https://github.com/libretro/nestopia at `135dfa6dfda5e7603d61e751b9ddd0cc42546bc3` | `native/nestopia` |
| PPSSPP (libretro, GPL-2.0-or-later) | https://github.com/hrydgard/ppsspp at `1bd28b0d634d4ec31acb7092563f3e1e247d1e9c` | `native/ppsspp` |

Engines and libraries not listed here ship unmodified, as their notices in
this directory state. The revisions above are those of the engines in the
build this notice was written for; test/legal_modifications_notice_test.py
keeps them equal to the repository's pins.
