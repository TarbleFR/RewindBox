# Switch 2 playlist (S2Arm) — notices ready for integration

**Nothing here is in a delivered IPA yet.** The separate test line is retired: the S2Arm pieces now reach the common
delivery as its pinned-engine component `s2arm` (`build-utils/s2arm/engine-pin.json`), and the sections below that say
"test IPA" describe that application. The
common line's notice files (`docs/LEGAL_AND_CREDITS.md`, `NOTICE.md`,
`docs/PACKAGE_SOURCES_AND_LICENSES.md`, `licenses/`) are not modified by this branch. The test IPA
carries the engine's own licence and notice texts in its legal bundle, `Legal/S2Arm`
([The texts in the test IPA](#the-texts-in-the-test-ipa-legals2arm), main's decision of 11 Nov); the
draft lines for `docs/LEGAL_AND_CREDITS.md` stay main's decision. The first build of the Switch 2 test
line that declares `s2arm.prepare` and `s2arm.sysdata` ships all of it: the engine frameworks, the
preparation library linked into Runner and the system data
([What the test IPA ships](#what-the-test-ipa-ships-with-the-engine-and-its-bridge) below);
the tables after it detail `S2ArmPrepare.xcframework` and the RewindBox code derived from S2Arm.

## What the test IPA ships with the engine and its bridge

Every piece comes from an authenticated producer run of the test line
([delivery](s2arm-engine-bridge.md#delivery-pinned-engine-component-s2arm)); S2Arm is at commit
`6b6a571553f7a687af46e03e2cdbf8ef4d77f335` (`tools/s2arm_prototype/pin.json`). Third parties
of the engine are those S2Arm's own `THIRD_PARTY_LICENSES.md` marks "进 IPA" (in the iPhone
package) at that commit, completed by what the engine build really keeps: the kept-code inventory
(`build-utils/s2arm/engine/kept_code_inventory.py --check`, a blocking step of `s2arm-engine.yml`, runs 43119291210
and 43122083170) settles it for the NuGet packages and for the linked native archives.

### Draft notice lines (for `docs/LEGAL_AND_CREDITS.md`, main's decision)

```
## Switch 2 (S2Arm) engine — private test IPA only

The private test IPA of the Switch 2 line embeds the S2Arm engine (S2ArmEngine.framework,
NS2Pro.framework), its preparation library (linked into the application) and its system data
(S2ArmSystemData), all built in CI from S2Arm commit 6b6a571553f7a687af46e03e2cdbf8ef4d77f335.

- S2Arm — Copyright 2026 S2Arm contributors — Apache License 2.0 —
  https://github.com/jhaizhou-ops/S2Arm. RewindBox modified S2Arm files for its engine
  (build-utils/s2arm/engine/patches, changes marked "RewindBox") and ported some of its tools
  to C (native/s2arm/prepare); both are changed works under Apache-2.0 section 4.
- ns2pro-bridge — Copyright (c) 2026 DanielZhangyc, Copyright (c) 2026 jhaizhou — MIT.
- Ryujinx — Copyright (c) Ryujinx Team and Contributors — MIT.
- S2Arm direct graphics layer parts — Copyright (c) 2026 seedds — MIT.
- MacNativeGames (nvn_bcdec, nvn_mtl.m parts) — Copyright (c) 2026 MacNativeGames contributors — MIT.
- bcdec — Copyright (c) 2022 Sergii Kudlai — MIT or The Unlicense.
- nvn.h — Copyright (c) 2020 h1k421 — MIT.
- D3D11 fixed-function tessellator reference — Copyright (c) Microsoft Corporation (through Mesa) — MIT.
- SMAA — Copyright (C) 2013 Jorge Jimenez, Jose I. Echevarria and the other authors in its notice — MIT.
- deko3d texture layout (ported) — Copyright (C) 2018-2020 fincs — zlib; the port is marked as altered.
- SPIRV-Cross (vulkan-sdk-1.4.363.0) — Apache License 2.0.
- .NET runtime 10 (compiled ahead of time into the engine) — Copyright (c) .NET Foundation and Contributors — MIT,
  with its third-party notices.
- libvpx 1.17.0 — BSD-3-Clause with its patent grant; libopus 1.6.1 — BSD-3-Clause with its patent grant;
  dav1d 1.5.4 — BSD-2-Clause.
- Capstone 5.0.7 — BSD-3-Clause, LLVM-derived parts under the LLVM Release License; LZ4 1.9.4 — BSD-2-Clause
  (inside the preparation library).
- Noto Sans 2.015 and Noto Sans CJK 2.004 (converted by S2Arm into the Switch shared-font format) —
  SIL Open Font License 1.1; texts in S2ArmSystemData/licenses/fonts.
- IANA time zone database 2026f — public domain (some files BSD-3-Clause); text in
  S2ArmSystemData/licenses/tzdata.
No Nintendo data ships: no system file, firmware, key, font or game content of a console. The
system data (S2ArmSystemData) is only fonts under the SIL Open Font License, the IANA time zone
database and empty system data synthesised by S2Arm's generator.
```

The test IPA does not wait for these lines: its `Legal/S2Arm` holds the full texts and RewindBox's
notice for the engine, which makes the same statement word for word (next section).

## The texts in the test IPA (`Legal/S2Arm`)

Main's decision (11 Nov): the test IPA carries the full texts, collected from the pinned sources,
never copied by hand into this repository, and the legal gate requires them for an application that
carries `S2Arm-native-identity.json` (and only for it).

1. **Producer.** `s2arm-engine.yml`, after `make ios-guest`, runs
   `build-utils/s2arm/engine/collect_licenses.py`: each text is read where the build took its code,
   then listed in `license-sources.json` with its component, licence, origin, size and SHA-256:
   a file of the pinned S2Arm commit (from the repository objects, not the patched tree) or the exact
   licence comment of a header (its lines recorded); a member of a source archive the build fetched,
   checked against the SHA-256 its S2Arm build script pins; a file of a .NET package the NativeAOT build
   restored, at the restored version, checked against NuGet's SHA-512; for the packages and the deko3d port whose text the
   archives lack, a text fetched over HTTPS from the pinned source commit and accepted only with the SHA-256 fixed in the
   collector (kind `pinned-url`). The result must pass the gate's
   rule, then goes into the engine artifact as `licenses/`, recorded by `s2arm-engine-identity.json`.
2. **Launcher.** `engine-download` checks the texts against that record, the gate's rule, the pin and
   the producer commit's RewindBox notice; `engine-embed` puts them in `Runner.app/Legal/S2Arm` after
   `embed_legal_bundle.py` wrote `Legal/`, and records them in `S2Arm-native-identity.json`
   (`licenses`); `engine-check-app`, `engine-check-ipa` and the offline verification check them again.
3. **Gate.** `build-utils/embed_legal_bundle.py --validate-only --app <app>` (its S2Arm conditional,
   handed to main) runs on the built application right after `engine-check-app`: the manifest, every
   text it lists with its digest and size and nothing else, the required texts below, the statement
   that no Nintendo data ships, the manifest and S2Arm commit the identity records. Without the
   identity file the gate behaves exactly as before (`test/s2arm_legal_bundle_test.py`).

| `Legal/S2Arm/…` | Component | Origin | Required by the gate |
| --- | --- | --- | --- |
| `RewindBox-S2Arm-NOTICE.txt` | RewindBox's notice for the engine: S2Arm's licence and NOTICE, the engine patch series and the preparation library's patch series (`build-utils/s2arm/prepare/patches`, recorded as `preparePatches` in `S2Arm-native-identity.json`) (Apache-2.0 §4(b)), where the texts are, no Nintendo data | `build-utils/s2arm/engine/RewindBox-S2Arm-NOTICE.txt` at the producer commit | yes, with its statement |
| `S2Arm/LICENSE`, `S2Arm/NOTICE` | S2Arm, Apache-2.0 §4(a) and (d) | `LICENSE`, `NOTICE` of the pin | yes |
| `S2Arm/THIRD_PARTY_LICENSES.md` | S2Arm's own third-party table | `THIRD_PARTY_LICENSES.md` of the pin | yes |
| `dotnet/Microsoft.NETCore.App.Runtime.NativeAOT.ios-arm64/LICENSE.TXT`, `…/THIRD-PARTY-NOTICES.TXT` | .NET runtime compiled into the engine (10.0.15 at E0; the version restored is recorded) | the runtime pack's archive | yes |
| `dotnet/Microsoft.DotNet.ILCompiler/THIRD-PARTY-NOTICES.TXT` | the NativeAOT compiler | the ILCompiler package's archive | yes |
| `dotnet/runtime.<host>.Microsoft.DotNet.ILCompiler/THIRD-PARTY-NOTICES.TXT` | the compiler's host package | its archive, when the build restored one | no |
| `libvpx/LICENSE`, `libvpx/PATENTS` | libvpx 1.17.0 | `services/vpx/build.sh` archive | yes |
| `opus/COPYING` | libopus 1.6.1 | `services/opus/build.sh` archive | yes |
| `dav1d/COPYING` | dav1d 1.5.4 | `services/dav1d/build.sh` archive | yes |
| `glslang/LICENSE.txt` | glslang 16.6.0, in `libglx.a` of the iOS engine | `graphics/third_party/glslang/build.sh` archive | yes |
| `bcdec/LICENSE` | bcdec | `graphics/nvn/third_party/bcdec/LICENSE` | yes |
| `ns2pro-bridge/LICENSE` | ns2pro-bridge (`NS2Pro.framework`) | `runtime/ns2pro/LICENSE` | yes |
| `Ryujinx/LICENSE.txt` | the Ryujinx tree compiled into the services | `compat/tree/LICENSE.txt` | yes |
| `SPIRV-Cross/LICENSE` | SPIRV-Cross vulkan-sdk-1.4.363.0 | `graphics/third_party/spirv_cross/LICENSE` | yes |
| `dotnet/Gommon/content/LICENSE` | Gommon 2.8.1.2 (MIT), kept | the package archive (`content/LICENSE`, not the `contentFiles` copy) | yes |
| `dotnet/Open.Nat.V2/LICENSE` | Open.Nat.V2 3.2.1 (MIT), kept | the package archive | yes |
| `dotnet/Ryujinx.LibHac/LICENSE` | Ryujinx.LibHac 0.21.0-alpha.133 (MIT, with the ISC hactool and XTSSharp notices), kept | the package archive | yes |
| `dotnet/System.IO.Hashing/THIRD-PARTY-NOTICES.TXT`, `System.IO.Hashing/LICENSE.TXT` | System.IO.Hashing 10.0.9 (MIT), kept | the package archive; the licence from the pinned `dotnet/dotnet` commit named by its nuspec | yes |
| `Humanizer/license.txt` | Humanizer.Core 3.0.10 (MIT), kept | pinned source commit `90f0cb1d` of its nuspec repository (HTTPS, SHA-256 fixed in the collector) | yes |
| `RecyclableMemoryStream/LICENSE` | Microsoft.IO.RecyclableMemoryStream 3.0.1 (MIT), kept | pinned commit `e29a2838` (same way) | yes |
| `NetCoreServer/LICENSE` | NetCoreServer 8.0.7 (MIT), kept | pinned commit `cb58a43b` (same way) | yes |
| `MsgPack.Cli/LICENSE.txt` | MsgPack.Cli 1.0.1 (Apache-2.0), kept; its nuspec has no repository, only a licenceUrl | commit `e1b574a0` (git tag 1.0.1), same way | yes |
| `deko3d/LICENSE` | deko3d texture layout (zlib, © 2018-2020 fincs), ported in `nvn_tex.c`, linked as `libnvn.a(nvn_tex.c.o)` | pinned commit `373bfd43` of devkitPro/deko3d (same way) | yes |
| `direct-graphics-layer/LICENSE` | S2Arm direct graphics layer parts (© 2026 seedds) | `graphics/nvn/LICENSE` | no |
| `MacNativeGames/LICENSE` | nvn_bcdec, parts of `nvn_mtl.m` | `graphics/nvn/third_party/macnativegames/LICENSE` | no |
| `SMAA/AA-LICENSE.txt` | SMAA shaders through Ryujinx | `graphics/metal/shaders/AA-LICENSE.txt` | no |
| `nvn.h/NOTICE.txt` | nvn.h (h1k421) | the licence comment of `graphics/nvn/gfx/nvn/include/nvn.h` (lines 1–21 at the pin) | no |
| `D3D11-tessellator/NOTICE.txt` | D3D11 tessellator reference (Microsoft, through Mesa) | the licence comment of `graphics/metal/gal_tess_d3d.h` (lines 30–47 at the pin) | no |
| `Capstone/capstone.txt`, `Capstone/capstone-llvm.txt`, `LZ4/lz4.txt` | Capstone and LZ4 in `S2ArmPrepare.xcframework` | `runtime/rewriter/LICENSES/` | no |
| `license-sources.json` | the manifest: component, licence, origin, size, SHA-256 of each text | written by the collector | yes |

Checked here: the collector on a synthetic commit, cache and NuGet folder and on the pinned S2Arm
commit read from its repository objects (all 13 files and the two comments;
`test/s2arm_engine_licenses_test.py` with `S2ARM_PINNED_TREE`), and by hand on the real dav1d 1.5.4
archive (its pinned SHA-256) and the real .NET 10.0.15 packs. Only the engine producer run shows the
four archives and the packs as that build restored them.

The settled state, from the kept-code inventory (runs 43119291210 and 43122083170: the services library's symbols per
package assembly, and the final link's map):

- **Kept code, text shipped.** Eight NuGet packages have NativeAOT code kept in the engine; each ships its text, taken
  from its own archive (Gommon, Open.Nat.V2, Ryujinx.LibHac, System.IO.Hashing's notices; SHA-512 checked against
  NuGet's record) or from the pinned source commit its nuspec names, fetched over HTTPS in CI and accepted only with
  the SHA-256 fixed in `collect_licenses.py` (Humanizer.Core, Microsoft.IO.RecyclableMemoryStream, NetCoreServer,
  MsgPack.Cli, System.IO.Hashing's licence). The deko3d port is the same: its zlib text comes from the pinned
  devkitPro/deko3d commit. The libnvn rule of the check covers it, with S2Arm, MacNativeGames' `nvn_bcdec`, the direct
  graphics layer and `nvn.h`.
- **No kept code, no text.** The other 62 packages of the restore (the Humanizer.Core resource packages,
  Microsoft.IdentityModel.*, System.CodeDom, Microsoft.Bcl.Cryptography, the Extensions abstractions, the ILCompiler and
  ILLink build packages) have no kept code: "no kept code, inventory of run 43122083170" (listed one by one in the
  inventory output of that run, `proof/kept-code-inventory.txt`). A package that gains kept code makes the check fail
  until its text is added.
- **Not in the restore.** ZstdSharp.Port and SkiaSharp are not among the restored packages, so neither has a text.
- **Linked archives.** `libs2a_cs.a` (S2Arm, Ryujinx, the .NET runtime, the packages above), `libnvn.a`, `libdsx.a`
  (SPIRV-Cross, S2Arm), `libglx.a` (glslang, S2Arm's `gl_xlate`), `libnxgal.a` (S2Arm, the D3D11 tessellator
  reference), the `obj_app` objects (S2Arm), `libs2a_dav1d.a`, `libs2a_vpx.a`, `libs2a_opus.a` and the runtime pack's
  native archives each map to a rule of the check. `libclang_rt.ios.a` is LLVM compiler-rt (Apache-2.0 with the LLVM
  exception, which asks for no notice for compiled object code): recorded, no text. Apple SDK stubs and system
  libraries are not distributed.
- **glslang.** Its `LICENSE.txt` includes the GPL-3 Bison exception section, which covers `glslang_tab.cpp` (Bison
  output): nothing more is needed for it.
- **`nvn_deswizzle.c`.** Its "reference port fdb3710d" is seedds's upstream direct graphics chain (nxnative, MIT,
  © 2026 seedds), whose text already ships as `direct-graphics-layer/LICENSE`.
- **ICU.** Absent: the engine builds with `InvariantGlobalization=true`.

### `S2ArmEngine.framework`, `NS2Pro.framework` (`s2arm-engine.yml`)

| Component | Version / identity | Licence | Licence text (at the S2Arm pin) | In the IPA (S2Arm's table) |
| --- | --- | --- | --- | --- |
| S2Arm runtime, services, graphics, iOS guest (with RewindBox patches 0001–0009) | `6b6a5715` | Apache-2.0; keep `NOTICE` | `LICENSE`, `NOTICE` | yes |
| ns2pro-bridge | baseline `4d7ce092` | MIT | `runtime/ns2pro/LICENSE` | yes (`NS2Pro.framework`) |
| Ryujinx tree | `compat/tree` | MIT | `compat/tree/LICENSE.txt` | yes |
| Ryujinx NuGet packages kept in the engine: Gommon 2.8.1.2, Open.Nat.V2 3.2.1, Ryujinx.LibHac 0.21.0-alpha.133 (MIT; LibHac also the ISC hactool and XTSSharp notices), System.IO.Hashing 10.0.9, Humanizer.Core 3.0.10, Microsoft.IO.RecyclableMemoryStream 3.0.1, NetCoreServer 8.0.7 (MIT), MsgPack.Cli 1.0.1 (Apache-2.0) | `compat/tree/Directory.Packages.props` | as listed | the package archive or the pinned source commit of its nuspec (table above) | kept (inventory of runs 43119291210, 43122083170) |
| Other NuGet packages of the restore (62, e.g. Microsoft.IdentityModel.*, System.CodeDom, Humanizer.Core resource packages) | — | — | none | no kept code, inventory of run 43122083170 |
| ZstdSharp.Port, SkiaSharp | — | — | none | not in the restore |
| .NET runtime (NativeAOT) | 10.x | MIT | dotnet `LICENSE.txt`, `ThirdPartyNotices.txt` | yes (statically compiled) |
| Direct graphics layer parts | `86d9ba12` | MIT (© 2026 seedds) | `graphics/nvn/LICENSE` | yes |
| SPIRV-Cross | vulkan-sdk-1.4.363.0 | Apache-2.0 | `graphics/third_party/spirv_cross/LICENSE` | yes (`libnxgal.a`) |
| glslang | 16.6.0 (`graphics/third_party/glslang/build.sh`) | BSD-3-Clause and others | its source archive (`LICENSE.txt`) | not per S2Arm's table, but linked into the iOS app (`libglx.a`, `graphics/build.mk`) |
| bcdec | `80859ed` (through MacNativeGames) | MIT or Unlicense | `graphics/nvn/third_party/bcdec/LICENSE` | yes |
| nvn_bcdec, parts of `nvn_mtl.m` | MacNativeGames `84eebcd0985c` | MIT | `graphics/nvn/third_party/macnativegames/LICENSE` | yes |
| nvn.h | h1k421 | MIT | its file header | yes |
| D3D11 tessellator reference | Mesa main, 2026-10-21 | MIT (Microsoft) | `graphics/metal/gal_tess_d3d.h` header | yes |
| SMAA shaders | through Ryujinx | MIT | `graphics/metal/shaders/AA-LICENSE.txt` | yes |
| deko3d texture layout (port) | devkitPro/deko3d `373bfd43` | zlib (© 2018-2020 fincs) | `deko3d/LICENSE` (pinned commit, SHA-256 checked) | yes (`libnvn.a(nvn_tex.c.o)`) |
| libvpx (S2Arm patches `services/vpx/patches/`) | 1.17.0 | BSD-3-Clause + patent grant | its source archive (`LICENSE`, `PATENTS`) | yes (static) |
| libopus | 1.6.1 | BSD-3-Clause + patent grant | its source archive (`COPYING`) | yes (static) |
| dav1d | 1.5.4 | BSD-2-Clause | its source archive (`COPYING`) | yes (static) |

Not in the IPA per S2Arm's table: Vulkan-Headers, Capstone/LZ4 of S2Arm's own rewriter
tool, Python packages, the macOS launcher's runtime, Homebrew libraries, GNU bash.

### `S2ArmSystemData` (`s2arm-prepare.yml`, macOS artifact)

Shipped whole as `Runner.app/S2ArmSystemData`, every file checked against its `SHA256SUMS`;
the licence texts are part of the tree:

| Part | Origin | Licence | Text in the IPA |
| --- | --- | --- | --- |
| `systemdata/fonts/*.bfttf` (7 files) | S2Arm `pack/fonts/make_open_fonts.py` (Apache-2.0) from Noto Sans 2.015 and Noto Sans CJK 2.004 at google/fonts `45e3d526…`; pad icons drawn by the generator; Unihan 17.0.0 read for character lists only | SIL OFL 1.1 | `S2ArmSystemData/licenses/fonts/OFL-*.txt`, `MANIFEST.tsv`, `LICENSES.md` |
| `systemdata/010000000000080E/` | IANA tz 2026f (`services/systemdata/tzdata-pins.sh`, SHA-512 checked), compiled by `make_tzdata.sh` | public domain (some files BSD-3-Clause) | `S2ArmSystemData/licenses/tzdata/LICENSE` |
| `systemdata/<id>/`, `<id>.synth` | S2Arm `pack/sysdata_synth.py`: empty but well-formed structures, no Nintendo data | output of Apache-2.0 code | S2Arm's (above) |
| `SOURCES.tsv`, `SHA256SUMS` | provenance of the tree (S2Arm commit, generators, tz release) | — | — |

### Preparation library (`s2arm-core.yml`), linked into Runner

`S2ArmPrepare.xcframework` is linked statically into the Runner executable through
`packages/s2arm_engine_bridge` (RewindBox code, repository licence); its contents are the
next two tables (S2Arm rewriter, Capstone, LZ4; RewindBox's ports of S2Arm tools).

### Points for main (with the ones at the end of this page)

- Apache-2.0 section 4: the test IPA's `Legal/S2Arm` carries S2Arm's `LICENSE` and `NOTICE` and
  RewindBox's statement of its changes; font and tz texts travel inside `S2ArmSystemData/licenses/`.
- The .NET notices and the licence texts of libvpx (with its `PATENTS`), libopus, dav1d and glslang come
  from the build's own packs and source archives (no copy in the repository).
- glslang: S2Arm's table marks it as not in the IPA, but S2Arm's `graphics/build.mk` links `libglx.a`
  (`graphics/third_party/glslang/build.sh`, glslang 16.6.0) into the iOS application, hence the guest
  framework: its text is required.
- Settled by the kept-code inventory (see "The settled state" above): deko3d's zlib text, the Ryujinx NuGet
  references, ZstdSharp.Port, LibHac (kept in the engine although S2Arm's table says otherwise: its text ships).

## Components in `S2ArmPrepare.xcframework`

| Component | Version / identity | Source | Licence | Use |
| --- | --- | --- | --- | --- |
| S2Arm rewriter (`runtime/rewriter`) | commit `6b6a571553f7a687af46e03e2cdbf8ef4d77f335` | https://github.com/jhaizhou-ops/S2Arm | Apache-2.0; keep S2Arm's `NOTICE` ("S2Arm, Copyright 2026 S2Arm contributors") | linked unmodified, built from the pinned source in CI |
| Capstone | 5.0.7 (PyPI source archive, SHA-256 `796bdd69b05fa124fc2aa2e74b9a0b3d4c4e7f3e02add5e583cf2f3bca282ede`) | https://pypi.org/project/capstone/5.0.7/ · https://github.com/capstone-engine/capstone | BSD-3-Clause; LLVM-derived parts under the LLVM Release License (texts: S2Arm `runtime/rewriter/LICENSES/capstone.txt`, `capstone-llvm.txt`) | AArch64 disassembly inside the rewriter |
| LZ4 | 1.9.4, as bundled by python-lz4 4.4.5 (source archive SHA-256 `5f0b9e53c1e82e88c10d7c180069363980136b9d7a8306c4dca4f760d60c39f0`) | https://pypi.org/project/lz4/4.4.5/ · https://github.com/lz4/lz4 | BSD-2-Clause (text: S2Arm `runtime/rewriter/LICENSES/lz4.txt`) | decompression of NSO segments |

## RewindBox code derived from S2Arm

These files are ports to C of S2Arm tools, written for RewindBox and kept under the
repository's licence with S2Arm's Apache-2.0 notice; each states its origin in its header.
Apache-2.0 section 4 applies: keep the licence text and the `NOTICE`, and state that the
files were changed (they are translations, not copies).

| RewindBox file | S2Arm origin (same pinned commit) |
| --- | --- |
| `native/s2arm/prepare/s2arm_prepare.c` | `pack/stage_rewrite.sh` (module list, order of steps) |
| `native/s2arm/prepare/s2arm_addr_need.c` | `tools/addr_need.py` |
| `native/s2arm/prepare/s2arm_modules.c` | `graphics/nvn/games/profile_guess.py` (`gpu_driver_modules`), `graphics/nvn/tools/nso_syms.py` |
| `native/s2arm/prepare/s2arm_nro.c` | `tools/nro_exports.py`, `runtime/rewriter/nro_to_nso.py`, `graphics/nvn/tools/romfs_list.py` (walk rules) |
| `native/s2arm/prepare/s2arm_zbic.c` | `pack/nx_unpack/ZbicDecoder.cs`, `pack/nx_unpack/NsoZbic.cs` (BIC header rules credited there to Atmosphère / kinnay zbic as facts, no code taken) |
| `native/s2arm/prepare/s2arm_ns2_dump.c` | `pack/ns2_dump.py` (including its README.synth note text) |
| `native/s2arm/prepare/s2arm_pack.c` | `ios/embed.py`, `ios/macho_dylib.py`, `pack/ship_ext.py` (container per-game files, `ctx_text`), `pack/save_identity.py` (validation), `pack/pkg_srcs.py` (`srcs`, the `app_tables()` list), `pack/pack.py`, `graphics/tools/direct/runtime_only_lib.sh` (including its texts), `tools/module_order.py`, `runtime/src/pack_apply.c` (bookkeeping file names) |
| `native/s2arm/prepare/s2arm_caps.c` | `pack/gen_caps.sh` (including its texts), `tools/caps_policy.py` (`decide`, `sources`, `engine_l1`, reason texts), `graphics/nvn/games/profile_guess.py` (`facts_of`, `guess`, `engine`), `graphics/nvn/tools/nso_syms.py`, `graphics/nvn/tools/romfs_list.py` (walk rules) |
| `tools/s2arm_prototype/run_pack_test.py`, `tools/s2arm_prototype/build_sysdata_bundle.sh` | test and build drivers only (CI): they run S2Arm's tools and generators from the pinned checkout; no S2Arm source stored |
| `build-utils/s2arm/engine/patches/0003-guest-configure-launch-context-and-window.patch` (engine framework, not in an IPA yet) | modifies `runtime/src/launchctx.c`, `runtime/src/vawin.c`, `runtime/include/s2a_launch_ctx.h`; adds `runtime/src/rb_guest.c`, `runtime/src/rb_guest.h` (written for RewindBox, built inside S2Arm's tree); changes marked `RewindBox` in comments |
| `build-utils/s2arm/engine/patches/0004-guest-code-pages-through-host-hook.patch` | modifies `runtime/src/imgpack.c`, `runtime/src/vawin.c`; changes marked `RewindBox` in comments |
| `build-utils/s2arm/engine/patches/0005-guest-signal-handlers-chained.patch` | modifies `runtime/src/crash.c` (chaining modelled on S2Arm's own `runtime/src/crash_android_fatal.inc`); changes marked `RewindBox` in comments |
| `build-utils/s2arm/engine/patches/0006-guest-session-end-instead-of-exit.patch` | modifies `runtime/src/lifecycle.c`, `runtime/src/native.h`, `runtime/src/host_main.c`, `runtime/src/ap_host.c`, `runtime/src/pack_apply.c`, `ios/app.m`; changes marked `RewindBox` in comments |
| `build-utils/s2arm/engine/patches/0007-guest-view-controller-and-start.patch` | modifies `ios/app.m`, `ios/vpad.m`, `runtime/src/host_main.c`; changes marked `RewindBox` in comments |
| `build-utils/s2arm/engine/patches/0008-guest-strings-and-game-files-from-engine-bundle.patch` | modifies `ios/s2a_l10n.h`, `ios/save_transfer.m`; changes marked `RewindBox` in comments |
| `build-utils/s2arm/engine/patches/0009-guest-log-in-docs-pad-recording-off-engine-resources.patch` | modifies `runtime/src/os.c`, `runtime/src/logcap.c`, `runtime/src/native.h`, `runtime/src/launchctx.c`, `runtime/src/sesdiag.c`, `runtime/include/s2a_launch_ctx.h`, `ios/diag.m`, `ios/loadpage.m`, `ios/hud.m`, `ios/cpatch_settings.m`, `ios/controller.m`, `ios/vpad.m`, `ios/s2a_l10n.h`, and the RewindBox files `runtime/src/rb_guest.c`, `runtime/src/rb_guest.h` of 0003; changes marked `RewindBox` in comments |
| `build-utils/s2arm/engine/patches/0010-guest-park-and-resume-the-same-game.patch` | modifies `runtime/src/session.c`, `runtime/include/s2a_session.h`, `runtime/src/rb_guest.c`, `runtime/src/rb_guest.h`, `ios/app.m`: Quit parks the session through S2Arm's own in-process restart retirement, and the same game resumes; changes marked `RewindBox` / `patch 0010` in comments |
| `build-utils/s2arm/prepare/patches/0001-rewriter-progress-report.patch` (on-device preparation library, S2ArmPrepare.xcframework) | modifies `runtime/rewriter/rewriter.c`, `runtime/rewriter/rewriter.h`: a progress callback per thread (`s2a_rewrite_set_progress`) called at each pass and inside the long loops; it only reads loop counters, no output byte depends on it (`test/s2arm_rewriter_progress_test.py`; outputs compared with the unpatched rewriter in `s2arm-prepare.yml`); changes marked `RewindBox` in comments |

`native/s2arm/prepare/s2arm_sha256.c` is not derived from S2Arm (SHA-256 written from FIPS 180-4).

## System data tree (CI artifact of `build_sysdata_bundle.sh`; not in the repository)

To ship in the app with the engine, together with the licence texts in its `licenses/` folder:

| Part | Origin | Licence |
| --- | --- | --- |
| `systemdata/fonts/*.bfttf` (7 files, Switch shared-font names, fonts named "S2Arm Sans …" / "S2Arm Pad Icons") | generated by S2Arm `pack/fonts/make_open_fonts.py` (Apache-2.0) from Noto Sans JP/SC/TC/KR 2.004 and Noto Sans 2.015 at google/fonts commit `45e3d5269e4a17d823f6d84470bc084dc5ae46f6` (SHA-256 per file in S2Arm `pack/fonts/LICENSES.md`); Unihan 17.0.0 read for character lists only | SIL Open Font License 1.1 (`OFL-NotoSansCJK.txt`, `OFL-NotoSans.txt`); the icon glyphs are drawn by the generator |
| `systemdata/010000000000080E/` (time zone data) | IANA tz release pinned in S2Arm `services/systemdata/tzdata-pins.sh` (2026f, SHA-512 checked), compiled by `make_tzdata.sh` | public domain (tz `LICENSE`) |
| `systemdata/<id>/` + `<id>.synth` (0802, 0823, 0849 …) | empty but well-formed structures written by S2Arm `pack/sysdata_synth.py`; no Nintendo data | generated output of Apache-2.0 code |
| `tools/s2arm_prototype/zbic_batch/Program.cs` | test driver only (CI): compiles S2Arm's two ZBIC files from the pinned checkout; no S2Arm source stored |

## Points for the integration owner

- Apache-2.0 code linked into a GPL-3.0 application is compatible in that direction; the
  combined work is distributed under GPL-3.0 with the Apache notices kept.
- S2Arm's own notice says some of its upstream sources have no declared licence (community
  patches); none of that is used here, and the optional patch tables are left out of the port.
- No game, key, firmware or other protected content is in the repository or in the xcframework.
- The xcframework's identity file (`S2ArmPrepare-identity.json`, produced by
  `.github/workflows/s2arm-core.yml`) records the S2Arm commit, both archive hashes and the
  binary hashes for the pin.
