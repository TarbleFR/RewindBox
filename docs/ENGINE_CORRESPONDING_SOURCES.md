# Engine corresponding sources

## Current published Build 530 source addendum (25 October 2026)

The published [**fix 0.0.9 / Build 530**](https://github.com/TarbleFR/RewindBox/releases/tag/0.0.9-fix.1)
is newer than this document's original 21 October audit snapshot.
Its **host application source** is
[`3f0c706afe1d0faa635465517871a500c3289582`](https://github.com/TarbleFR/RewindBox/tree/3f0c706afe1d0faa635465517871a500c3289582);
the release workflow completed in [run **40156236364**](https://github.com/TarbleFR/RewindBox/actions/runs/40156236364).
See the [exact Build 530 release/source manifest](RELEASE_0.0.9_FIX_1_SOURCE_MANIFEST.md)
rather than treating the older Build 499/500 and unfinished-MeloNX records
below as the current build identities.

- **MeloNX is now embedded** in the IPA, not an external handoff or a
  future/unpackaged engine. Its patched NativeAOT core uses source
  `ab6d87ebb8b33d0151953b1b9ea7cefaab7a4b12`,
  [successful CI run **40152134234**](https://github.com/TarbleFR/RewindBox/actions/runs/40152134234)
  and upstream [MeloNX revision `13700519f3abc4e6d7ed8a065b118b2cc59bcd67`](https://starforgejo.dev/projects/MeloNX/src/commit/13700519f3abc4e6d7ed8a065b118b2cc59bcd67).
  The [pinned build adapter](../build-utils/melonx/adapt_runtime.py)
  avoids the unsupported iOS `VK_EXT_external_memory_host` buffer import and
  retains the existing GPU readback fallback.
- **RPCS3 is Core 528**, source
  `17ee65469c39e560c91fdb6d55604ab590992f59`,
  [successful run **40142369420**](https://github.com/TarbleFR/RewindBox/actions/runs/40142369420).
  This supersedes the core binary mentioned in the historical Build 499/500
  rows, but does not establish a God of War III FPS gain.
- **Libretro has 35 bundled cores**, including Mesen and the rebuilt PPSSPP
  core; the binary remains tied to the immutable source/identity receipts
  and still has the 32 buildbot-source-attestation gaps documented below.

The bundle's `Legal/Sources/BUILD_SOURCE_EVIDENCE.json` sets
`complete_corresponding_source_attested: false`. The newer host and engine
source links do not remove previously identified component source, license
or commercial SDK obligations. Build 530 validation includes the ARM64 iOS
simulator; long-duration real-iPhone gameplay has not been independently
verified.

---

## Historical engine source-rights audit (21 October 2026)

Review: **21 October 2026**, development source
`fab5ecf3b119b4d84636ad4f4d03218a96279871` on `Claude`. This record prepares
source access for a future distribution. It does not change an engine binary,
create an IPA, publish a release or establish distribution clearance.

The current package contains **35 Libretro cores**. Three have exact upstream
source-revision evidence: **Nestopia, Azahar and the replacement PPSSPP core**.
The other **32** still lack a reviewed source-build attestation: **23** have
binary-version candidates, and **nine** have no recovered binary source
revision. All 23 candidate commits remain publicly retrievable, but their
availability does not prove the full inputs used to build those binaries.
Public **0.0.8 contains 34 cores**; Mesen was added subsequently. These counts
come from the [preserved original identity](evidence/build479-libretro-source-identity.json),
the [current inventory](../build-utils/libretro/cores.json), the
[Mesen addition](hd-textures-nes-mesen.md) and the
[PPSSPP replacement receipt](evidence/psprelaunch497-delivery.json).

The [machine-readable audit](evidence/engine-source-license-audit-2026-10-21.json)
records full binary/source hashes, download observations, engine recipes and
**91 first-level Git submodule entries, representing 87 distinct
repository/revision pairs**. All 87 exact commits were resolved publicly.
This is a source inventory, not a claim that every listed dependency is linked
into iOS or that every nested dependency has been independently materialized.
The broader [source-access record](SOURCE_CODE_ACCESS.md),
[package audit](PACKAGE_SOURCES_AND_LICENSES.md) and
[dedicated PPSSPP audit](PPSSPP_SOURCE_AND_LICENSE_AUDIT.md) cover adjacent scope.

## Main engines: available sources and remaining work

Automatically generated GitHub source archives contain tracked files from
their own repository. They do **not** include the contents of Git submodules.
For a modified engine, retain its upstream source, recursive dependencies,
RewindBox patches/adapters, build recipe and actual dependency resolution
together. A binary hash, a source URL and a license text each answer different
questions.

| Component | Identified source and download | RewindBox build evidence | Concrete remaining boundary |
| --- | --- | --- | --- |
| RPCS3 / XITRIX | [`22f1152783ce`](https://github.com/XITRIX/rpcs3/tree/22f1152783cef1f7e04af7b1c895173e28fd5b03), [root source archive](https://github.com/XITRIX/rpcs3/archive/22f1152783cef1f7e04af7b1c895173e28fd5b03.tar.gz), 28 direct submodules | Core 499, ABI 30; [receipt](evidence/rpcs3audit499-core.json); [host source and patches](https://github.com/TarbleFR/RewindBox/tree/0b18a23460b0a9840406fda2e3d6da4c5cdb7273/build-utils/rpcs3). Core 500 reuses it. | No consolidated export of the patched engine, recursive dependencies, LLVM changes and other actual source inputs. |
| ARMSX2 / PCSX2 | [`9d989ca933a8`, iOSv2.6.0](https://github.com/ARMSX2/ARMSX2/tree/9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe), [source archive](https://github.com/ARMSX2/ARMSX2/archive/9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe.tar.gz) | Core 485, ABI 8; [receipt](evidence/hdtex485-delivery.json); [host patch and recipe](https://github.com/TarbleFR/RewindBox/tree/1343906f05e33b40f10f7026a1a6e2327c338d0e/build-utils/armsx2) | Actual librashader Cargo resolution and dependency source collection were not retained with the binary. The existing host-source artifact does not contain the separately fetched engine. |
| Dolphin / DolphiniOS | [`7cac54161659`](https://github.com/OatmealDome/dolphin-ios/tree/7cac54161659421ed95c2cd1c0b0746539a4cd38), [root source archive](https://github.com/OatmealDome/dolphin-ios/archive/7cac54161659421ed95c2cd1c0b0746539a4cd38.tar.gz), 27 direct submodules | Stable Core SHA-256 `7129d9c654fb…`; [record](dolphin-retro-rewind-online-audit-2026-10-20.md); [host patch](https://github.com/TarbleFR/RewindBox/blob/ae7d46f90dff64ce698b8c18e0c12510dbae96fe/build-utils/patch_dolphin_internal_core_v2.py) | Source pins and patch are available, but the framework workflow does not export a consolidated recursive source collection. |
| StikJIT | [`32287268fa58`, 1.9.0](https://github.com/StikDebug/StikJIT/tree/32287268fa5824f9edce4cb359f5833ce0cf7b00), [wrapper source archive](https://github.com/StikDebug/StikJIT/archive/32287268fa5824f9edce4cb359f5833ce0cf7b00.tar.gz) | [Source pin](../build-utils/stikjit/source.json), [build recipe](../build-utils/build_patched_stikjit.py), [compatibility patcher](../build-utils/patch_stikjit_compat.py) | The Swift wrapper links a precompiled Rust FFI archive whose exact source revision, Cargo lock and matching notices are not identified. |
| Nestopia | [`135dfa6dfda5`](https://github.com/libretro/nestopia/tree/135dfa6dfda5e7603d61e751b9ddd0cc42546bc3), [verified source archive](https://codeload.github.com/libretro/nestopia/tar.gz/135dfa6dfda5e7603d61e751b9ddd0cc42546bc3) | [Source/patch identity](../native/nestopia/source.json), [RewindBox patch](../native/nestopia/reset-background.patch), [recipe](../.github/diagnostics/nestopia_bgcolor/build.py) | Original source and exact modification are available; retain them together with the historical build inputs. |
| Azahar | [`5f3306d13cab`, 2127.0-alpha1](https://github.com/azahar-emu/azahar/tree/5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6), [verified unified source archive](https://github.com/azahar-emu/azahar/releases/download/2127.0-alpha1/azahar-unified-source-2127.0-alpha1.tar.xz) | [Official binary release](https://github.com/azahar-emu/azahar/releases/tag/2127.0-alpha1), [recorded binary identity](evidence/build479-libretro-source-identity.json) | Unified archive includes submodule content. Upstream SBOM/attestation verification and reproducible-build proof are separate; this review does not claim them. |
| PPSSPP | [`1bd28b0d634d`](https://github.com/hrydgard/ppsspp/tree/1bd28b0d634d4ec31acb7092563f3e1e247d1e9c) | Source-built replacement, Core 497; [dedicated source/license audit](PPSSPP_SOURCE_AND_LICENSE_AUDIT.md) | Follow that audit for FFmpeg, dependency notices and exact modified-source requirements. |
| MeloNX / LibHac | [MeloNX `13700519f3ab`](https://starforgejo.dev/projects/MeloNX/src/commit/13700519f3abc4e6d7ed8a065b118b2cc59bcd67), [LibHac `23e402ebb6de`](https://starforgejo.dev/archive/LibHac_Ryubing/src/commit/23e402ebb6dedc517e34a98a033078dc0f6fd478), [source pins](../build-utils/melonx/source.json) | [Historical native-session receipt](evidence/melonx-native-session-2026-10-20.json) | Source-built embedded test integration: [scope and limitations](melonx-embedded-build506.md). Original MIT notice and GPLv3 README declarations preserved; physical gameplay remains unverified. |

### RPCS3: retain the entire patched source chain

The [canonical source manifest](../build-utils/rpcs3/canonical-source.json)
identifies the upstream base and RewindBox patch; the core receipt retains
input hashes and binary identity. The patch SHA-256 is
`6a88c3f5046bbbbd52113ba691cc2f9074e4ebc260f195c1e73776a8c9f876e1`.
The build also applies a separate LLVM AArch64 patch to
[`llvm-project@ca7933e47d3a`](https://github.com/llvm/llvm-project/tree/ca7933e47d3a3451d81e72ac174dcb5aa28b59d1).
Preserving only RPCS3's root archive omits that submodule and the other 27 direct
Git dependencies. The [build script](../build-utils/build_rpcs3_embedded_core.sh)
also identifies the following inputs:

- **FFmpeg 8.1.1 source tarball**, pinned to SHA-256
  `b6863adde98898f42602017462871b5f6333e65aec803fdd7a6308639c52edf3`.
  Its [official download](https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz)
  returned HTTP 503 during this audit. The signed `n8.1.1` tag resolves to
  [`239f2c733de4`](https://github.com/FFmpeg/FFmpeg/tree/239f2c733de417201d7ad3b3b8b0d9b63285b2b1),
  whose [Git source archive](https://github.com/FFmpeg/FFmpeg/archive/239f2c733de417201d7ad3b3b8b0d9b63285b2b1.tar.gz)
  is a source retrieval alternative, not an assertion of byte equality with
  the release tarball. Retain the actual configured source used by the recipe.
- **MoltenVK 1.4.2**, linked from the upstream iOS archive. The recipe's
  SHA-256 `b5d947b1660e6e9fed40b9cd2387e160aaab9e80b775c0cef7e14059405178c1`
  matches the digest published for the
  [official release asset](https://github.com/KhronosGroup/MoltenVK/releases/download/v1.4.2/MoltenVK-ios.tar).
  The [source revision `db66022459ff`](https://github.com/KhronosGroup/MoltenVK/tree/db66022459ffb663aa2b50f6b018bc2e124f5edf)
  pins seven external repositories in `ExternalRevisions`. Their full revisions
  and individual source-download links are retained in the audit JSON.
- **RewindBox integration source**, including ABI, native adapter and NeoSwap
  files listed by the core receipt. Their historical
  [host source archive](https://github.com/TarbleFR/RewindBox/archive/0b18a23460b0a9840406fda2e3d6da4c5cdb7273.tar.gz)
  supplies the host side, separately from upstream engine dependencies.

The inspected core workflow exposes two retained artifacts: binary/identity
and diagnostics. Neither is a consolidated corresponding-source archive.
The binary artifact was listed as expiring on **19 November 2026**. Existing
`validate_source_archive_evidence.py` and similarly named NeoSwap tests concern
cached GLSL/pixels; they do not validate distribution of emulator source code.
See the [artifact observations and exact workflow](evidence/engine-source-license-audit-2026-10-21.json)
and [RPCS3 core workflow](../.github/workflows/rpcs3-core.yml).

### ARMSX2: vendored C/C++ sources plus a Rust resolution gap

The pinned ARMSX2 tree has no Git submodules. Its iOS dependency recipe uses
vendored sources under `3rdparty` and
`platforms/android/app/src/main/cpp/3rdparty`, plus system facilities and a
separately fetched
[`librashader@87e8a97b5051`](https://github.com/SnowflakePowered/librashader/tree/87e8a97b50516d997defeaa168173dcd185d4022).
The upstream iOS recipe applies its
[Apple-vendor patch](https://github.com/ARMSX2/ARMSX2/blob/9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe/platforms/ios/patches/librashader-ctypes-apple-vendor.patch)
and builds the Metal runtime with Cargo. The exact
[Cargo.lock](https://github.com/SnowflakePowered/librashader/blob/87e8a97b50516d997defeaa168173dcd185d4022/Cargo.lock)
is public and hashes to
`9abad84ffcf6761b3b69ba82cca398224fe43ca472652b5f8ef04421f0af2d50`.
It contains 479 workspace packages, including 460 registry packages; those
numbers do not mean all packages are linked into the iOS engine.

The inspected [librashader CMake recipe](https://github.com/ARMSX2/ARMSX2/blob/9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe/platforms/ios/app/src/main/cpp/3rdparty/librashader/CMakeLists.txt)
does not pass `--locked` or `--frozen`, and the historical artifact does not
retain the actual resolved build lock. This does not prove that Cargo changed
the lock; it identifies the evidence that is missing. Future collection needs
the resolved lock, the selected registry crate sources/notices and the actual
patched source, together with the RewindBox adapter and build configuration.

The artifact named `ARMSX2-host-source-1343906…` is produced by archiving the
**RewindBox host repository**. It does not archive the separately cloned
ARMSX2 or librashader tree. It was still listed by GitHub during review, with
expiry **22 October 2026 at 00:11:39 UTC** and three-day retention. The public
[host Git archive](https://github.com/TarbleFR/RewindBox/archive/1343906f05e33b40f10f7026a1a6e2327c338d0e.tar.gz)
remains a useful resource, with that limited scope. Evidence:
[workflow](../.github/workflows/armsx2-core.yml),
[artifact metadata](evidence/engine-source-license-audit-2026-10-21.json).

### StikJIT: the wrapper source does not identify its Rust library

The exact [project definition](https://github.com/StikDebug/StikJIT/blob/32287268fa5824f9edce4cb359f5833ce0cf7b00/project.yml)
links `idevice/libidevice_ffi.a`. The public file was downloaded and statically
inspected: **57,017,464 bytes**, SHA-256
`4db23fe1d342927b9480bb9a8577f219994365621dc28aa0018e23ea1990ecc8`,
Git blob `3fb7e2dbfdb9db3d47bd6364a435bbc10d5581f9`. The wrapper pin has no
Cargo source tree, Cargo.lock or exact idevice source revision. Its
[upstream workflow](https://github.com/StikDebug/StikJIT/blob/32287268fa5824f9edce4cb359f5833ce0cf7b00/.github/workflows/build.yml)
uses the committed static library; it does not rebuild that dependency.

The [README](../assets/legal/engines/StikJIT-Upstream-README.md) credits the
idevice project and explicitly preserves separate licensing for the Rust FFI
and bundled JavaScript. Compiler and crate-version strings found in the static
archive do not establish a complete source revision or dependency lock.
Therefore the notice manifest records this missing correspondence explicitly;
it does not copy a license from an arbitrary current idevice HEAD. Obtain the
matching source, resolved lock, flags and notices for the existing library, or
prepare a separately authorized replacement from known sources. Export the
RewindBox-patched Swift/JavaScript wrapper as well: a source-identity JSON
alone does not contain the modified source.

### Nestopia and Azahar: usable source downloads verified now

Nestopia's original source archive was retrieved successfully and matches the
SHA-256 in [source.json](../native/nestopia/source.json):
`e1a8a853e919cb46a33b48702d703d2e8019d6bc8aff7c3fab88828f8e3c1619`.
It has no Git submodules. Its RewindBox reset-background patch has SHA-256
`53847d26b0f914e6fe7ae00415a91f93a5d9573a78453b4947b752b0f9e10d59`.
The historical recipe checks the original and patched file hashes. Collecting
that source and patch does not require rebuilding the core.

Azahar supplies a real unified source archive, produced by
[`git archive-all --force-submodules`](https://github.com/azahar-emu/azahar/blob/5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6/.ci/source.sh).
The **43,056,616-byte** download matches its published SHA-256:
`5a45c813fc371f6a1d2721ce614225650728a7d6be22dc52e6b55718534590f9`.
Its `GIT-COMMIT` is the exact core pin, and the archive contains **20,994
regular files**. All 35 first-level submodule directories contain source files.
The [inspection record](evidence/engine-source-license-audit-2026-10-21.json)
retains their individual file counts and commit identities. No execution,
rebuild or verification of upstream attestations is claimed by this inspection.

## Every current Libretro core

“Exact revision” means the source identity in the retained build/release record;
it does not mean complete dependency or license closure. “Candidate” means an
observed binary version string resolved to a public full commit. “Unresolved”
means no binary source revision was recovered. An immutable notice-reference
snapshot is provided for those rows only to identify the existing legal
reference; it is **not** presented as matching binary source. Full hashes and
the 23 candidate API lookups are in the audit JSON.

| Core | Source evidence | Source resource |
| --- | --- | --- |
| `nestopia` | Exact revision `135dfa6dfda5` | [Source](https://github.com/libretro/nestopia/tree/135dfa6dfda5e7603d61e751b9ddd0cc42546bc3) · [archive](https://github.com/libretro/nestopia/archive/135dfa6dfda5e7603d61e751b9ddd0cc42546bc3.tar.gz) |
| `snes9x` | Candidate `fae2fea08f74` | [Candidate source](https://github.com/libretro/snes9x/tree/fae2fea08f74180759ef540ee94259213f503480) · [candidate archive](https://github.com/libretro/snes9x/archive/fae2fea08f74180759ef540ee94259213f503480.tar.gz) |
| `gambatte` | Candidate `d9d6cd06382d` | [Candidate source](https://github.com/libretro/gambatte-libretro/tree/d9d6cd06382d1ced30de34d56d3609452323dab1) · [candidate archive](https://github.com/libretro/gambatte-libretro/archive/d9d6cd06382d1ced30de34d56d3609452323dab1.tar.gz) |
| `mgba` | Candidate `7a12d6d4b9ac` | [Candidate source](https://github.com/libretro/mgba/tree/7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6) · [candidate archive](https://github.com/libretro/mgba/archive/7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6.tar.gz) |
| `genesis_plus_gx` | Candidate `393f70cd64c7` | [Candidate source](https://github.com/libretro/Genesis-Plus-GX/tree/393f70cd64c7334564c19a424c383f53986c13f4) · [candidate archive](https://github.com/libretro/Genesis-Plus-GX/archive/393f70cd64c7334564c19a424c383f53986c13f4.tar.gz) |
| `genesis_plus_gx_wide` | Candidate `b7ad005431f5` | [Candidate source](https://github.com/libretro/Genesis-Plus-GX-Wide/tree/b7ad005431f5f0b55e559f6d598d1ed2479bf13b) · [candidate archive](https://github.com/libretro/Genesis-Plus-GX-Wide/archive/b7ad005431f5f0b55e559f6d598d1ed2479bf13b.tar.gz) |
| `picodrive` | Candidate `1890c2932234` | [Candidate source](https://github.com/libretro/picodrive/tree/1890c2932234c9d30f4cd3851d02228baae8f09e) · [candidate archive](https://github.com/libretro/picodrive/archive/1890c2932234c9d30f4cd3851d02228baae8f09e.tar.gz) |
| `fbneo` | Unresolved | [Notice-reference snapshot only](https://github.com/libretro/FBNeo/tree/95153da1f113c56735bd9a818171f908df628421) |
| `desmume` | Unresolved | [Notice-reference snapshot only](https://github.com/libretro/desmume/tree/95b4d798731caa809125b6c3c11d17cc332ff6ef) |
| `mupen64plus_next` | Candidate `12edd2c74a51` | [Candidate source](https://github.com/libretro/mupen64plus-libretro-nx/tree/12edd2c74a517ff86dfa8cfc71ad75e4c10486d5) · [candidate archive](https://github.com/libretro/mupen64plus-libretro-nx/archive/12edd2c74a517ff86dfa8cfc71ad75e4c10486d5.tar.gz) |
| `mednafen_psx_hw` | Candidate `10e4b0c6ceae` | [Candidate source](https://github.com/libretro/beetle-psx-libretro/tree/10e4b0c6ceae20daa65ddf436a4445dddd0982d2) · [candidate archive](https://github.com/libretro/beetle-psx-libretro/archive/10e4b0c6ceae20daa65ddf436a4445dddd0982d2.tar.gz) |
| `mednafen_psx` | Candidate `10e4b0c6ceae` | [Candidate source](https://github.com/libretro/beetle-psx-libretro/tree/10e4b0c6ceae20daa65ddf436a4445dddd0982d2) · [candidate archive](https://github.com/libretro/beetle-psx-libretro/archive/10e4b0c6ceae20daa65ddf436a4445dddd0982d2.tar.gz) |
| `ppsspp` | Exact revision `1bd28b0d634d` | [Source](https://github.com/hrydgard/ppsspp/tree/1bd28b0d634d4ec31acb7092563f3e1e247d1e9c) · [archive](https://github.com/hrydgard/ppsspp/archive/1bd28b0d634d4ec31acb7092563f3e1e247d1e9c.tar.gz) |
| `azahar` | Exact revision `5f3306d13cab` | [Source](https://github.com/azahar-emu/azahar/tree/5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6) · [archive](https://github.com/azahar-emu/azahar/releases/download/2127.0-alpha1/azahar-unified-source-2127.0-alpha1.tar.xz) |
| `mednafen_pce_fast` | Unresolved | [Notice-reference snapshot only](https://github.com/libretro/beetle-pce-fast-libretro/tree/3f946f277aef3aa99a95551618bbcd1dd2bda0d9) |
| `mednafen_wswan` | Candidate `4b01295838ea` | [Candidate source](https://github.com/libretro/beetle-wswan-libretro/tree/4b01295838ea89e3f1355bbe4cb5cf98aa6108cd) · [candidate archive](https://github.com/libretro/beetle-wswan-libretro/archive/4b01295838ea89e3f1355bbe4cb5cf98aa6108cd.tar.gz) |
| `mednafen_ngp` | Candidate `a50d5ac288a8` | [Candidate source](https://github.com/libretro/beetle-ngp-libretro/tree/a50d5ac288a81f2104ddf43195a4efdd15c72227) · [candidate archive](https://github.com/libretro/beetle-ngp-libretro/archive/a50d5ac288a81f2104ddf43195a4efdd15c72227.tar.gz) |
| `handy` | Candidate `bc55d462f0b2` | [Candidate source](https://github.com/libretro/libretro-handy/tree/bc55d462f0b2d6b073ea93dc552ebd73cec60fd1) · [candidate archive](https://github.com/libretro/libretro-handy/archive/bc55d462f0b2d6b073ea93dc552ebd73cec60fd1.tar.gz) |
| `mednafen_vb` | Candidate `d5ae54c8e23b` | [Candidate source](https://github.com/libretro/beetle-vb-libretro/tree/d5ae54c8e23b573a3b34e888b2d48a588027e92c) · [candidate archive](https://github.com/libretro/beetle-vb-libretro/archive/d5ae54c8e23b573a3b34e888b2d48a588027e92c.tar.gz) |
| `stella` | Candidate `b52ccb02eea5` | [Candidate source](https://github.com/stella-emu/stella/tree/b52ccb02eea5e117c142421a2b5ba289f2c7c2c5) · [candidate archive](https://github.com/stella-emu/stella/archive/b52ccb02eea5e117c142421a2b5ba289f2c7c2c5.tar.gz) |
| `prosystem` | Unresolved | [Notice-reference snapshot only](https://github.com/libretro/prosystem-libretro/tree/8a88014287c7a01cd568067e5a557d0a2b2a051f) |
| `a5200` | Candidate `40c6f2f1ad4a` | [Candidate source](https://github.com/libretro/a5200/tree/40c6f2f1ad4a3145b328d5baaf010fae6c7e752b) · [candidate archive](https://github.com/libretro/a5200/archive/40c6f2f1ad4a3145b328d5baaf010fae6c7e752b.tar.gz) |
| `gearcoleco` | Candidate `d74e9b82f6bb` | [Candidate source](https://github.com/drhelius/Gearcoleco/tree/d74e9b82f6bba36610ea7823b11e95202c1d8e29) · [candidate archive](https://github.com/drhelius/Gearcoleco/archive/d74e9b82f6bba36610ea7823b11e95202c1d8e29.tar.gz) |
| `pokemini` | Unresolved | [Notice-reference snapshot only](https://github.com/libretro/PokeMini/tree/132111b76343559860532a1ccc094f93f1ed5650) |
| `gw` | Unresolved | [Notice-reference snapshot only](https://github.com/libretro/gw-libretro/tree/91d599b951e7bfe7e040347f58667cba20074adc) |
| `sameduck` | Candidate `040e19c379f0` | [Candidate source](https://github.com/libretro/sameduck/tree/040e19c379f00dae10afe0eb0c1b2b019b985bbe) · [candidate archive](https://github.com/libretro/sameduck/archive/040e19c379f00dae10afe0eb0c1b2b019b985bbe.tar.gz) |
| `potator` | Candidate `227c5f6f3ce7` | [Candidate source](https://github.com/libretro/potator/tree/227c5f6f3ce74d32e9002ce24c1420288559a860) · [candidate archive](https://github.com/libretro/potator/archive/227c5f6f3ce74d32e9002ce24c1420288559a860.tar.gz) |
| `ardens` | Unresolved | [Notice-reference snapshot only](https://github.com/tiberiusbrown/Ardens/tree/ba7ad0dcfc196459859d304a8c483b38621c7cfa) |
| `wasm4` | Candidate `9d6c962785cf` | [Candidate source](https://github.com/aduros/wasm4/tree/9d6c962785cfe3719d0245fd279ecbe98a4dbb63) · [candidate archive](https://github.com/aduros/wasm4/archive/9d6c962785cfe3719d0245fd279ecbe98a4dbb63.tar.gz) |
| `uzem` | Unresolved | [Notice-reference snapshot only](https://github.com/libretro/libretro-uzem/tree/d991ee94547c8294abc1c4cb73d63116aa58b5bc) |
| `freechaf` | Candidate `76c7a84f1f7e` | [Candidate source](https://github.com/libretro/FreeChaF/tree/76c7a84f1f7e80f3e6f2bba96fe100cb24e99124) · [candidate archive](https://github.com/libretro/FreeChaF/archive/76c7a84f1f7e80f3e6f2bba96fe100cb24e99124.tar.gz) |
| `freeintv` | Candidate `ef3e0fe322be` | [Candidate source](https://github.com/libretro/FreeIntv/tree/ef3e0fe322bec62a7f916c0bb0834c08c348d0b4) · [candidate archive](https://github.com/libretro/FreeIntv/archive/ef3e0fe322bec62a7f916c0bb0834c08c348d0b4.tar.gz) |
| `o2em` | Candidate `679d6fec0496` | [Candidate source](https://github.com/libretro/libretro-o2em/tree/679d6fec04963f6e70a7ec217e3d0ebb1fe472fc) · [candidate archive](https://github.com/libretro/libretro-o2em/archive/679d6fec04963f6e70a7ec217e3d0ebb1fe472fc.tar.gz) |
| `mednafen_pcfx` | Candidate `c1650bad5fbd` | [Candidate source](https://github.com/libretro/beetle-pcfx-libretro/tree/c1650bad5fbdcc3c3ccd45e29e3983e1ccf16cff) · [candidate archive](https://github.com/libretro/beetle-pcfx-libretro/archive/c1650bad5fbdcc3c3ccd45e29e3983e1ccf16cff.tar.gz) |
| `mesen` | Unresolved | [Notice-reference snapshot only](https://github.com/libretro/Mesen/tree/0102910c39ad1a62bc3f784466f3f67ca9eae335) |

### What the public buildbot metadata actually proves

The [current `.index-extended`](https://buildbot.libretro.com/nightly/apple/ios-arm64/latest/.index-extended)
contains a date, an eight-digit **CRC32** and a filename. The
[RetroArch parser](https://github.com/libretro/RetroArch/blob/df16ef193cbe385b87e8a1cf27b66da35bf3c0e0/core_updater_list.c)
defines that field as a CRC; it is not a shortened Git commit.

For Mesen, the public ZIP was downloaded and its core hashes to the exact
recorded Core 495 value:
`547b840f3911dfe52bc1ce3b44f6bd4a137c869f21cb25e280434818ef06d2b6`.
The binary's CRC32 is `f739eea7`, matching the index line. This strengthens the
public binary-origin record, but it supplies **no source-build revision**.
The Mesen license-reference commit `0102910c39ad…` therefore remains a legal
reference, not a recovered binary source pin.

The inspected official
[Libretro build recipes](https://github.com/libretro/libretro-super/tree/1d9f13453bc28eb629856c3ac7ca28f79b459df1/recipes/apple)
name repositories, branches and options. Their current snapshot is not a
historical full-commit/configuration manifest for the delivered binaries.
The buildbot `/logs/` endpoint returned 404 and `buildserver.libretro.com`
returned 503 during review. These are session observations, not a claim that
all historical evidence is permanently unavailable. **No additional source
attestation was recovered for the 32 cores.** Preserve the candidate distinction
until an original build receipt or matching complete source/configuration is
obtained. Sources: [observations](evidence/engine-source-license-audit-2026-10-21.json),
[historical binary-version evidence](evidence/build479-core-version-candidates.json).

Mupen64Plus HD integration in 488 and Beetle PSX HW integration in 489 did not
rebuild those cores; their receipts explicitly record `coreRebuilt: false`.
Their source-candidate status is unchanged. The shared MoltenVK framework also
has its own provenance boundary: the pinned
[RetroArch container](https://github.com/libretro/RetroArch/tree/df16ef193cbe385b87e8a1cf27b66da35bf3c0e0/pkg/apple/Frameworks/MoltenVK.xcframework)
identifies framework bytes, not its exact upstream MoltenVK source. It must not
be equated with RPCS3's independently pinned MoltenVK 1.4.2. Evidence:
[488](evidence/hdtex488-delivery.json), [489](evidence/hdtex489-delivery.json),
[original package identity](evidence/build479-libretro-source-identity.json).

## MeloNX source-built test runtime (22 October 2026)

The replacement embedded runtime is documented in [Build 506](melonx-embedded-build506.md).
The original eleven upstream binary paths below are an historical inventory,
not the dependencies redistributed by this build. Private MoltenVK, SDL and
FFmpeg are rebuilt from pinned sources; BreakpointJIT is replaced by the
RewindBox assembly helper. Device/gameplay validation remains outstanding.

### Historical staged inventory

The existing source recipes preserve upstream and reconstructed LibHac source
archives and an adapted-source ZIP. Their scope needs to remain explicit:
`git archive HEAD` contains tracked upstream files, while
`embedded-adapted-source.zip` lists adapted C# and host files. The complete
build script also changes `global.json` and `nuget.config`; the fragment ZIP
alone does not describe the entire final tree. Retain all configuration
changes, resolved .NET/workload/package identities and reconstruction inputs
with the final adapted sources. See [build_core.sh](../build-utils/melonx/build_core.sh),
[prepare_embedded.py](../build-utils/melonx/prepare_embedded.py) and
[build_libhac.py](../build-utils/melonx/build_libhac.py).

The [native dependency inventory](evidence/melonx-native-dependencies-2026-10-20.json)
contains **11 binary paths, nine unique hashes and zero identified matching
build sources**. Container hashes are useful evidence but do not identify the
corresponding sources of MoltenVK, BreakpointJIT, SDL3 or the FFmpeg libraries.
LibHac's reconstruction is not claimed byte-identical to the unavailable
original NuGet package. The upstream MIT/GPL statement conflict and the
controller's separate licensing also remain recorded in the
[staged notice manifest](../assets/legal/melonx/license-sources.json).

## Notice corrections and next source collection

This review adds **19 exact upstream files for 11 components** under
[assets/legal/engines](../assets/legal/engines/license-sources.json):
librashader's MPL/GPL texts, Dolphin's four referenced `LICENSES` texts,
RPCS3's LLVM notice, FFmpeg 8.1.1 root license texts, MoltenVK 1.4.2 and selected
exact external dependency notices, plus StikJIT's attribution/scope README.
Every copied file is verified against its Git blob and recorded SHA-256.
These additions correct concrete notice gaps while retaining the unresolved
Rust FFI and Libretro MoltenVK source identities. They are not a complete
per-object license inventory for every engine dependency.

The next source collection should retain the already verified Nestopia and
Azahar downloads; materialize RPCS3, Dolphin and ARMSX2 at their recorded pins
with patches and recursive dependencies; capture actual Cargo/.NET/native
resolutions; and obtain matching evidence for precompiled inputs. Store those
collections durably with a manifest tying source bytes, patch bytes, recipes
and final binary identities together. An expiring Actions artifact or a
host-only archive cannot serve as the complete collection. These are concrete
collection requirements, not authorization to rebuild or publish.

Existing legal questions remain separately tracked in the
[future-release license review](RELEASE_NEXT_LICENSE_REVIEW.md), including
funding restrictions, combined-work license compatibility and unresolved
rights. The historical Build 479 identities and the public 0.0.8 release are
preserved unchanged in [embedded runtime provenance](EMBEDDED_RUNTIME_PROVENANCE.md).
