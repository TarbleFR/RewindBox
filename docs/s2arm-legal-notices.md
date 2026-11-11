# Switch 2 playlist (S2Arm) — notices ready for integration

**Draft for the integration owner. Nothing here is in a delivered IPA yet.** The delivery
notice files (`docs/LEGAL_AND_CREDITS.md`, `NOTICE.md`,
`docs/PACKAGE_SOURCES_AND_LICENSES.md`, `licenses/`) are not modified by this branch; the
entries below are to be copied there when S2Arm code enters an IPA. Scope today: what
`S2ArmPrepare.xcframework` contains. The list grows with each S2Arm component that enters
the app (runtime, graphics, services each bring their own third parties, listed in S2Arm's
`NOTICE` and `THIRD_PARTY_LICENSES.md`).

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
