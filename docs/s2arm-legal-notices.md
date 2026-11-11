# Switch 2 playlist (S2Arm) — notices ready for integration

**Nothing here is in a delivered IPA yet** (no build of the test line carries the engine so far). The
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
([delivery](s2arm-engine-bridge.md#delivery-test-line)); S2Arm is at commit
`6b6a571553f7a687af46e03e2cdbf8ef4d77f335` (`tools/s2arm_prototype/pin.json`). Third parties
of the engine are those S2Arm's own `THIRD_PARTY_LICENSES.md` marks "进 IPA" (in the iPhone
package) at that commit; what the guest framework actually links is to be confirmed against
the framework before the notices are final (two rows are conditional in S2Arm's own table).

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
   restored, at the restored version, checked against NuGet's SHA-512. The result must pass the gate's
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
| `RewindBox-S2Arm-NOTICE.txt` | RewindBox's notice for the engine: S2Arm's licence and NOTICE, the patch series (Apache-2.0 §4(b)), where the texts are, no Nintendo data | `build-utils/s2arm/engine/RewindBox-S2Arm-NOTICE.txt` at the producer commit | yes, with its statement |
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

Not located, so not shipped (no text invented): the zlib licence text of deko3d (S2Arm ports its
texture layout in `graphics/nvn/gfx/nvn/nvn_tex.c`, whose line 2 names "zlib license, Copyright (C)
2018-2020 fincs"; S2Arm pins no deko3d commit and keeps no copy of the text; zlib asks for its notice
in source distributions only); the texts of the Ryujinx NuGet references (MsgPack.Cli 1.0.1 under
Apache-2.0 and eight MIT packages of `compat/tree/Directory.Packages.props`) and ZstdSharp.Port, which
S2Arm lists as in the reference closure without having checked what NativeAOT keeps; LibHac, which
S2Arm marks as not in the IPA although `Ryujinx.HLE`, which references it, is a trimmer root of
`services/aot/S2A.Aot.csproj`. These are points for main below.

### `S2ArmEngine.framework`, `NS2Pro.framework` (`s2arm-engine.yml`)

| Component | Version / identity | Licence | Licence text (at the S2Arm pin) | In the IPA (S2Arm's table) |
| --- | --- | --- | --- | --- |
| S2Arm runtime, services, graphics, iOS guest (with RewindBox patches 0001–0009) | `6b6a5715` | Apache-2.0; keep `NOTICE` | `LICENSE`, `NOTICE` | yes |
| ns2pro-bridge | baseline `4d7ce092` | MIT | `runtime/ns2pro/LICENSE` | yes (`NS2Pro.framework`) |
| Ryujinx tree | `compat/tree` | MIT | `compat/tree/LICENSE.txt` | yes |
| Ryujinx NuGet references: MsgPack.Cli 1.0.1 (Apache-2.0); Humanizer 3.0.10, Gommon 2.8.1.2, Microsoft.IO.RecyclableMemoryStream 3.0.1, Microsoft.IdentityModel.JsonWebTokens 8.19.1, SkiaSharp 3.119.4, NetCoreServer 8.0.7, Open.Nat.V2 3.2.1, System.IO.Hashing 10.0.9 (MIT) | `compat/tree/Directory.Packages.props` | as listed | each package's `LICENSE` | in the reference closure; kept after NativeAOT trimming not verified by S2Arm |
| ZstdSharp.Port | 0.8.8 | MIT | nupkg in `compat/packages` | if the host build references it |
| .NET runtime (NativeAOT) | 10.x | MIT | dotnet `LICENSE.txt`, `ThirdPartyNotices.txt` | yes (statically compiled) |
| Direct graphics layer parts | `86d9ba12` | MIT (© 2026 seedds) | `graphics/nvn/LICENSE` | yes |
| SPIRV-Cross | vulkan-sdk-1.4.363.0 | Apache-2.0 | `graphics/third_party/spirv_cross/LICENSE` | yes (`libnxgal.a`) |
| glslang | 16.6.0 (`graphics/third_party/glslang/build.sh`) | BSD-3-Clause and others | its source archive (`LICENSE.txt`) | not per S2Arm's table, but linked into the iOS app (`libglx.a`, `graphics/build.mk`) |
| bcdec | `80859ed` (through MacNativeGames) | MIT or Unlicense | `graphics/nvn/third_party/bcdec/LICENSE` | yes |
| nvn_bcdec, parts of `nvn_mtl.m` | MacNativeGames `84eebcd0985c` | MIT | `graphics/nvn/third_party/macnativegames/LICENSE` | yes |
| nvn.h | h1k421 | MIT | its file header | yes |
| D3D11 tessellator reference | Mesa main, 2026-10-21 | MIT (Microsoft) | `graphics/metal/gal_tess_d3d.h` header | yes |
| SMAA shaders | through Ryujinx | MIT | `graphics/metal/shaders/AA-LICENSE.txt` | yes |
| deko3d texture layout (port) | — | zlib (© 2018-2020 fincs) | `graphics/nvn/gfx/nvn/nvn_tex.c` header | yes |
| libvpx (S2Arm patches `services/vpx/patches/`) | 1.17.0 | BSD-3-Clause + patent grant | its source archive (`LICENSE`, `PATENTS`) | yes (static) |
| libopus | 1.6.1 | BSD-3-Clause + patent grant | its source archive (`COPYING`) | yes (static) |
| dav1d | 1.5.4 | BSD-2-Clause | its source archive (`COPYING`) | yes (static) |

Not in the IPA per S2Arm's table: Vulkan-Headers, LibHac, Capstone/LZ4 of S2Arm's own rewriter
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
- To decide: deko3d's zlib text, the Ryujinx NuGet references and ZstdSharp.Port, LibHac (see
  "Not located" above); a check of the engine framework's symbols would settle what NativeAOT kept.

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

`native/s2arm/prepare/s2arm_sha256.c` is not derived from S2Arm (SHA-256 written from FIPS 180-4).

## System data tree (CI artifact of `build_sysdata_bundle.sh`; not in the repository)

To ship in the app with the engine, together with the licence texts in its `licenses/` folder:

| Part | Origin | Licence |
| --- | --- | --- |
| `systemdata/fonts/*.bfttf` (7 files, Switch shared-font names, fonts named "S2Arm Sans …" / "S2Arm Pad Icons") | generated by S2Arm `pack/fonts/make_open_fonts.py` (Apache-2.0) from Noto Sans JP/SC/TC/KR 2.004 and Noto Sans 2.015 at google/fonts commit `45e3d5269e4a17d823f6d84470bc084dc5ae46f6` (SHA-256 per file in S2Arm `pack/fonts/LICENSES.md`); Unihan 17.0.0 read for character lists only | SIL Open Font License 1.1 (`OFL-NotoSansCJK.txt`, `OFL-NotoSans.txt`); the icon glyphs are drawn by the generator |
| `systemdata/010000000000080E/` (time zone data) | IANA tz release pinned in S2Arm `services/systemdata/tzdata-pins.sh` (2026f, SHA-512 checked), compiled by `make_tzdata.sh` | public domain (tz `LICENSE`) |
| `systemdata/<id>/` + `<id>.synth` (0802, 0823, 0849 …) | empty but well-formed structures written by S2Arm `pack/sysdata_synth.py`; no Nintendo data | generated output of Apache-2.0 code |
| `tools/s2arm_prototype/zbic_batch/Program.cs` | test driver only (CI): compiles S2Arm's two ZBIC files from the pinned checkout; no S2Arm source stored |
| `packages/s2arm_probe/ios/Classes/S2ArmSynthModule.h` | output of the S2Arm rewriter for a synthetic module written for the test; no S2Arm source |

## Points for the integration owner

- Apache-2.0 code linked into a GPL-3.0 application is compatible in that direction; the
  combined work is distributed under GPL-3.0 with the Apache notices kept.
- S2Arm's own notice says some of its upstream sources have no declared licence (community
  patches); none of that is used here, and the optional patch tables are left out of the port.
- No game, key, firmware or other protected content is in the repository or in the xcframework.
- The xcframework's identity file (`S2ArmPrepare-identity.json`, produced by
  `.github/workflows/s2arm-core.yml`) records the S2Arm commit, both archive hashes and the
  binary hashes for the pin.
