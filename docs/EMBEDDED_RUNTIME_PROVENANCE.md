# Embedded runtime provenance

This record distinguishes an upstream license snapshot, the identity of a
precompiled binary and the source revision actually attested for that binary.
It is not a claim of complete Corresponding Source or license compatibility.
The current development summary below was reviewed on 21 October 2026 at
`dc46d73c6a42c5662ad3a863071edac0aa4081ad` on `Claude`. The published release
remains [0.0.8, with its own source manifest](RELEASE_0.0.8_SOURCE_MANIFEST.md);
its binary is not changed by this documentation. See the
[next-release license review](RELEASE_NEXT_LICENSE_REVIEW.md) for the latest
notice additions and remaining findings.

## Current development changes since public 0.0.8

The delivery workflow currently pins **35 Libretro cores** in the package
produced from NeoStation source `ab9361c29f7c9ab769c4263dd8b7427fc4f4c036`,
run `39455712245`. The [Build 497 receipt](evidence/psprelaunch497-delivery.json)
records one rebuilt PPSSPP core and 34 unchanged other cores. Build 499 changes
RPCS3 only; [Build 500 reuses that exact Core](evidence/ps1rpcs3500-delivery.json).
The workflow's host commits identify NeoStation's build/integration sources,
not the independent upstream commits listed below.

| Component / milestone | Source or artifact actually established | Integration and provenance boundary |
| --- | --- | --- |
| ARMSX2 / PCSX2, Build 485 | Upstream `9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe` (`iOSv2.6.0`); NeoStation Core source `1343906f05e33b40f10f7026a1a6e2327c338d0e`, run `39178893158`, ABI 8 | Source-built with NeoStation's patches and adapter for PS2 texture replacement, following the Build 482 blending additions. [Source pin](../build-utils/armsx2/source.json), [delivery receipt](evidence/hdtex485-delivery.json). |
| Mupen64Plus-Next, Build 488 | Existing buildbot core; binary-version candidate `12edd2c74a517ff86dfa8cfc71ad75e4c10486d5` remains a candidate | N64 HD-texture support was added in the host/catalogue adapter. The [receipt](evidence/hdtex488-delivery.json) records `coreRebuilt: false` and unchanged compiled sections for all 34 then-existing cores. This was not a source rebuild or a new source-build attestation for Mupen64Plus. |
| Beetle PSX HW, Build 489 | Existing buildbot core; binary-version candidate `10e4b0c6ceae20daa65ddf436a4445dddd0982d2` remains a candidate | The host enabled the core's existing Vulkan renderer through the already-bundled MoltenVK and added texture-pack integration. The [receipt](evidence/hdtex489-delivery.json) records `coreRebuilt: false`; [implementation and limits](build489-hd-catalogue-ps1-vulkan.md). The runtime adapter does not establish the binary's complete build inputs. |
| Mesen, Build 495 | Official iOS ARM64 buildbot binary, SHA-256 `547b840f3911dfe52bc1ce3b44f6bd4a137c869f21cb25e280434818ef06d2b6`; added by package source `4c2186204ce06b50b989689a9c2322068f523a58`, run `39366986940` | Added unchanged as the 35th core; [packaging code](../build-utils/libretro/add_cores.py) compiles nothing and checks preservation of the prior 34 cores. [Integration evidence](hd-textures-nes-mesen.md). `0102910c39ad1a62bc3f784466f3f67ca9eae335` is the **license-reference revision**, explicitly not an attested binary source in [license-sources.json](../assets/legal/libretro/license-sources.json). |
| PPSSPP Libretro, Build 497 | Upstream `1bd28b0d634d4ec31acb7092563f3e1e247d1e9c`; NeoStation patch SHA-256 `c273728f2a30ed8d3cddcc83e2731db5877d15f71030632c09dbf8967f40cb75`; compiled core SHA-256 `a7d058581b657714e055dc9713e9a1252ad4acf6315b30610fcb2b1c81130b6f` | Source-built to correct PSP session memory ownership. [Source and patch identity](../native/ppsspp/source.json), [build and delivery receipt](evidence/psprelaunch497-delivery.json). This replaces the old PPSSPP buildbot artifact and its unattested-source status for subsequent deliveries using this package; it does not change the historical Build 479 binary below. |
| RPCS3 / XITRIX, Build 499, reused in 500 | Upstream `22f1152783cef1f7e04af7b1c895173e28fd5b03`; NeoStation Core source `0b18a23460b0a9840406fda2e3d6da4c5cdb7273`, run `39472233521`; canonical patch SHA-256 `6a88c3f5046bbbbd52113ba691cc2f9074e4ebc260f195c1e73776a8c9f876e1` | [Core receipt](evidence/rpcs3audit499-core.json) records ABI 30 and compiled SHA-256 `87bd77794232fc44b61d421e55d71bae3b2829a58b87ee36b2a176730d78004f`; final signed Core SHA-256 is `49033f06bcbe5bfb635a956783f87e35934f21d9be5fd3d84b4d902adb190a63`. [Build 500 continuity](evidence/ps1rpcs3500-delivery.json) confirms the same compiled sections. Imported public RPCS3/ARMSX3-related changes and credits are documented in the [audit](build499-armsx3-rpcs3-audit.md); the supplied ARMSX3 IPA was not incorporated. |
| MeloNX / Ryujinx, staged work only | MeloNX `13700519f3abc4e6d7ed8a065b118b2cc59bcd67`; reconstructed LibHac source `23e402ebb6dedc517e34a98a033078dc0f6fd478`; Melo-Controller reference `c049ce88a5635bddcd88e1965c42aa8fc92fe961` | [Source pins](../build-utils/melonx/source.json), [integration audit](melonx-embedded-integration-2026-10-20.md) and [session milestone](melonx-native-session-2026-10-20.md). The engine/session foundation has been compiled separately, but no playable MeloNX runtime is packaged or registered in NeoStation. LibHac's reconstructed source is not asserted byte-identical to its unavailable original NuGet package; the native dependency inventory does not establish every binary's matching build source. |

The preserved 34-core record below, the Mesen addition and the PPSSPP
replacement together establish **three current cores with exact upstream
source-revision evidence: Nestopia, Azahar and PPSSPP**. The other **32 of 35**
still lack that source-build attestation in the reviewed records. This is a
count of documented evidence, not a claim of complete Corresponding Source for
the three identified cores. No unchanged core's candidate revision is promoted
to an attestation by this review.

Dusklight and KartPad were removed after public 0.0.8; their rows below describe
historical payloads. Retaining attribution does not reintroduce their engines
or resources. The funding restrictions, combined-work compatibility questions
and other findings in the [next-release review](RELEASE_NEXT_LICENSE_REVIEW.md)
remain separate from source identification.

## Historical inspection — private Build 479

Everything in the following sections concerns the inspected Build 479 and its
34-core payload, unless explicitly marked as a later removal. These hashes and
findings are retained as historical evidence. The older public 0.0.7 / Build 455
also has its [separate historical review](RELEASE_0.0.7_LICENSE_REVIEW.md).

Inspected IPA: `a1c44f59c80fa98f4d5a0fa7a59885e2b8269fc3666f40b23a805a0528f1b742`, source `ff28cf2a63695400ad09d1c61538059d96992cc1`. The actual [Libretro identity](evidence/build479-libretro-source-identity.json) is preserved verbatim; its SHA-256 is `0bdf81b605c550ef7f5c47c49abaecdc46dbeabeb1602a124b41d6a0537d93b5`. The separate [runtime record](evidence/build479-runtime-source-identity.json) is extracted from `Legal/BUILD_SOURCE_IDENTITY.json`. StikJIT additionally has a precise framework-local source identity.

### Historical main runtimes and support component

| Component | Attested upstream source | Local integration and remaining boundary |
| --- | --- | --- |
| Dolphin / DolphiniOS | `7cac54161659421ed95c2cd1c0b0746539a4cd38` — OatmealDome/dolphin-ios | GPL-2.0-or-later per-file; fork aggregate describes GPLv3 compatibility. Keep integration sources and dependency notices; [credits](LEGAL_AND_CREDITS.md). |
| RPCS3 / XITRIX | `22f1152783cef1f7e04af7b1c895173e28fd5b03` | GPL-2.0-only for most files. NeoStation changes and their hashes are in [canonical-source.json](../build-utils/rpcs3/canonical-source.json); packaging commits and this upstream base are different identities. GPLv3 host/combined-work compatibility remains unresolved. |
| ARMSX2 / PCSX2 | `9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe`, `iOSv2.6.0` | GPLv3 material and separately licensed dependencies, including librashader. [Source pin](../build-utils/armsx2/source.json). |
| Dusklight (earlier builds only; removed on 20 October 2026, [decision](ports-removal-2026-10-20.md)) | `40457c6adb381928e4b5fef6ed459ed291edd5e2`, v2.0.3 | Root CC0; Aurora, Borealis, SDL and other dependencies retain their own terms. Exact submodule pins in the last [source.json](https://github.com/TarbleFR/neostation-ios/blob/23f4ca24f5f38445fb771e66647e86e6748dd24b/build-utils/dusklight/source.json) before its removal. |
| KartPad / WiiCompiled (earlier builds only; removed in Build 491) | Compiled source `67c7e2f942c1226af149e6a9cc571f647528e25e`; iOS runtime `d0b8dec62a8c98dd45736a996ae18327ada8fe3f` | GPL-covered software and separate game-derived logic rights. Public translated/profile inputs are incomplete; the pin is not proof of full rebuildability. [Source limitation preserved at public 0.0.8](https://github.com/TarbleFR/neostation-ios/blob/bcca4e4a4dc89a96b1dde05d66436af54efd327e/build-utils/kartpad/source.json). |
| StikJIT, JIT support rather than an emulator | `32287268fa5824f9edce4cb359f5833ce0cf7b00`, 1.9.0 | MPL-2.0; exact [source record](../build-utils/stikjit/source.json) also present in its framework. |

### Every Libretro core embedded in Build 479

The hash column identifies the pre-signing core artifact recorded by the actual delivery. Signing may change executable bytes; it is not a source commit. All complete hashes, archive URLs/hashes and dependency names are retained in the JSON evidence above. “Not attested” must never be replaced with a guessed current HEAD or a license-reference revision.

| Core | Recorded license | Source revision evidence | Recorded pre-signing SHA-256 |
| --- | --- | --- | --- |
| [nestopia](https://github.com/libretro/nestopia/tree/135dfa6dfda5e7603d61e751b9ddd0cc42546bc3) | GPLv2 | `135dfa6dfda5e7603d61e751b9ddd0cc42546bc3` | `1a04f99e5ae2c10aa5b3c75b002e212e894c2e7934cc46232deb50da62c0e16d` |
| [snes9x](https://github.com/libretro/snes9x) | Non-commercial | Binary-version candidate: [`fae2fea08f74180759ef540ee94259213f503480`](https://github.com/libretro/snes9x/commit/fae2fea08f74180759ef540ee94259213f503480) | `aeab4b70a4d572492409150928bbdfe0eb4d2ec1c851f30d33949175ce249dad` |
| [gambatte](https://github.com/libretro/gambatte-libretro) | GPLv2 | Binary-version candidate: [`d9d6cd06382d1ced30de34d56d3609452323dab1`](https://github.com/libretro/gambatte-libretro/commit/d9d6cd06382d1ced30de34d56d3609452323dab1) | `d99a9b26e6d73b91249b1cc8abdb90d6782c82d12598cb033be12babdb1ca713` |
| [mgba](https://github.com/libretro/mgba) | MPLv2.0 | Binary-version candidate: [`7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6`](https://github.com/libretro/mgba/commit/7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6) | `c7026dc4d8a799be2d991faa3d4e2286011d97f9b11fb1e2ef6ba77ebca66218` |
| [genesis_plus_gx](https://github.com/libretro/Genesis-Plus-GX) | Non-commercial | Binary-version candidate: [`393f70cd64c7334564c19a424c383f53986c13f4`](https://github.com/libretro/Genesis-Plus-GX/commit/393f70cd64c7334564c19a424c383f53986c13f4) | `290bf5499b896cdd82b47dd3f2c8e8dae808859ded30aa1c17502a7c9129f988` |
| [genesis_plus_gx_wide](https://github.com/libretro/Genesis-Plus-GX-Wide) | Non-commercial | Binary-version candidate: [`b7ad005431f5f0b55e559f6d598d1ed2479bf13b`](https://github.com/libretro/Genesis-Plus-GX-Wide/commit/b7ad005431f5f0b55e559f6d598d1ed2479bf13b) | `198a26556fdb8c1ef9897a3db359f27793cc3e695f23f38acc1f8a29d40a876e` |
| [picodrive](https://github.com/libretro/picodrive) | MAME | Binary-version candidate: [`1890c2932234c9d30f4cd3851d02228baae8f09e`](https://github.com/libretro/picodrive/commit/1890c2932234c9d30f4cd3851d02228baae8f09e) | `3c5d6181904d4d644cad530008a202931237ab038ab6a064e4b4f68ecbc4592b` |
| [fbneo](https://github.com/libretro/FBNeo) | Non-commercial | **Not attested** (buildbot binary) | `737bd97038db59e17d2ede4e68249be238c49bb31e3e93eced03a6e10e486625` |
| [desmume](https://github.com/libretro/desmume) | GPLv2 | **Not attested** (buildbot binary) | `52c2c2bb92a8647a67afd6cfdb333420065f8bd77be6245f74c3fb8e7cf3005f` |
| [mupen64plus_next](https://github.com/libretro/mupen64plus-libretro-nx) | GPLv2 | Binary-version candidate: [`12edd2c74a517ff86dfa8cfc71ad75e4c10486d5`](https://github.com/libretro/mupen64plus-libretro-nx/commit/12edd2c74a517ff86dfa8cfc71ad75e4c10486d5) | `afdaff358796de530fa005eb037af68f3e05936442cf07f5f7dde86803f8f115` |
| [mednafen_psx_hw](https://github.com/libretro/beetle-psx-libretro) | GPLv2 | Binary-version candidate: [`10e4b0c6ceae20daa65ddf436a4445dddd0982d2`](https://github.com/libretro/beetle-psx-libretro/commit/10e4b0c6ceae20daa65ddf436a4445dddd0982d2) | `2bb7819a8f4fd790b8dd327599075152a460079e7cf72d5a86d19af07423c437` |
| [mednafen_psx](https://github.com/libretro/beetle-psx-libretro) | GPLv2 | Binary-version candidate: [`10e4b0c6ceae20daa65ddf436a4445dddd0982d2`](https://github.com/libretro/beetle-psx-libretro/commit/10e4b0c6ceae20daa65ddf436a4445dddd0982d2) | `19e263e0968b24b750b74d32ee8e88ded866e16f170012e1ecf2b42e4041bc87` |
| [ppsspp](https://github.com/hrydgard/ppsspp) | GPLv2 | **Not attested** (buildbot binary) | `40d3b6f81a726ff82a89f87df5332f20a5dcdecd9f6473fcae7cade60bcb0cf0` |
| [azahar](https://github.com/azahar-emu/azahar/tree/5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6) | GPLv3+ | `5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6` | `a646ee8f804327e2d33cbacf4d4f64b6725d25c7d7ece1ccc13698b16f3bf1d8` |
| [mednafen_pce_fast](https://github.com/libretro/beetle-pce-fast-libretro) | GPLv2 | **Not attested** (buildbot binary) | `97aed349a4b523b2c5ae3e55f75810f5c6de5403cea41fccae55368c6b89cb6d` |
| [mednafen_wswan](https://github.com/libretro/beetle-wswan-libretro) | GPLv2 | Binary-version candidate: [`4b01295838ea89e3f1355bbe4cb5cf98aa6108cd`](https://github.com/libretro/beetle-wswan-libretro/commit/4b01295838ea89e3f1355bbe4cb5cf98aa6108cd) | `0f3a7249303cbe3be71ac9e99f425a4cc05034abb7615baedfa95d17e8155117` |
| [mednafen_ngp](https://github.com/libretro/beetle-ngp-libretro) | GPLv2 | Binary-version candidate: [`a50d5ac288a81f2104ddf43195a4efdd15c72227`](https://github.com/libretro/beetle-ngp-libretro/commit/a50d5ac288a81f2104ddf43195a4efdd15c72227) | `0d9932e1ee9a198918a05386071dd6c58ff4aff78f6c85dcdc5098f8e976fa0b` |
| [handy](https://github.com/libretro/libretro-handy) | Zlib | Binary-version candidate: [`bc55d462f0b2d6b073ea93dc552ebd73cec60fd1`](https://github.com/libretro/libretro-handy/commit/bc55d462f0b2d6b073ea93dc552ebd73cec60fd1) | `b2d2c86e03fe3c6fd49ba9dac73a59dded85628077abd2e015659c7611604f06` |
| [mednafen_vb](https://github.com/libretro/beetle-vb-libretro) | GPLv2 | Binary-version candidate: [`d5ae54c8e23b573a3b34e888b2d48a588027e92c`](https://github.com/libretro/beetle-vb-libretro/commit/d5ae54c8e23b573a3b34e888b2d48a588027e92c) | `2ee0c2c8e4c77073045ac8e135886f628c5ae93b962256e2ffa8db39f8147bad` |
| [stella](https://github.com/stella-emu/stella) | GPLv2 | Binary-version candidate: [`b52ccb02eea5e117c142421a2b5ba289f2c7c2c5`](https://github.com/stella-emu/stella/commit/b52ccb02eea5e117c142421a2b5ba289f2c7c2c5) | `70efdf7e7c18f51396605a51a3f823d4c59392a60f875d83b01feff95a464934` |
| [prosystem](https://github.com/libretro/prosystem-libretro) | GPLv2 | **Not attested** (buildbot binary) | `69ff2105f2f94e28ffda83ca60a93c83b169fedcb32158faf69f17e165624601` |
| [a5200](https://github.com/libretro/a5200) | GPLv2 | Binary-version candidate: [`40c6f2f1ad4a3145b328d5baaf010fae6c7e752b`](https://github.com/libretro/a5200/commit/40c6f2f1ad4a3145b328d5baaf010fae6c7e752b) | `3c1661671225181d16ec39c4a663fd4bc4cfead9d0d48addccff921f8be51002` |
| [gearcoleco](https://github.com/drhelius/Gearcoleco) | GPLv3 | Binary-version candidate: [`d74e9b82f6bba36610ea7823b11e95202c1d8e29`](https://github.com/drhelius/Gearcoleco/commit/d74e9b82f6bba36610ea7823b11e95202c1d8e29) | `dbeaa8c4e934ec7bdf1b4f875ab8d75b3e714ced4d7a92b2b787e70bfe05fb66` |
| [pokemini](https://github.com/libretro/PokeMini) | GPLv3+ | **Not attested** (buildbot binary) | `ea44fd3e06a0fb0fa74c7c10b632934d1a5ad708068598ec5ad2a71bfe641757` |
| [gw](https://github.com/libretro/gw-libretro) | Zlib | **Not attested** (buildbot binary) | `cbf9a62ddb0b39057f30bf9e1b19589840c5c7f667dee5c679d1d967b2e068b8` |
| [sameduck](https://github.com/libretro/sameduck) | MIT | Binary-version candidate: [`040e19c379f00dae10afe0eb0c1b2b019b985bbe`](https://github.com/libretro/sameduck/commit/040e19c379f00dae10afe0eb0c1b2b019b985bbe) | `daa85d8d787bf32cf286901046ea0fd1bd495c6182d889de696ac192cb4f4b1c` |
| [potator](https://github.com/libretro/potator) | Unlicense (public domain) | Binary-version candidate: [`227c5f6f3ce74d32e9002ce24c1420288559a860`](https://github.com/libretro/potator/commit/227c5f6f3ce74d32e9002ce24c1420288559a860) | `9686d66a7bfec0fb4fc16e57ed87d0fd41e846862a3e0113eb5d3459bd616301` |
| [ardens](https://github.com/tiberiusbrown/Ardens) | MIT | **Not attested** (buildbot binary) | `afa1c8b621fe4273d3cd8c7652d3230ae83e7e077afd1d44b753dc6c39a780a1` |
| [wasm4](https://github.com/aduros/wasm4) | ISC | Binary-version candidate: [`9d6c962785cfe3719d0245fd279ecbe98a4dbb63`](https://github.com/aduros/wasm4/commit/9d6c962785cfe3719d0245fd279ecbe98a4dbb63) | `6bad181d5f14595e076a0a44fb8bbaf5d8c74b5381cc18262ef67735e7503aab` |
| [uzem](https://github.com/libretro/libretro-uzem) | MIT | **Not attested** (buildbot binary) | `a3721746f8f2556024a96b716258c6b851d2a47d7feff641b1325eb9ec6ee4ee` |
| [freechaf](https://github.com/libretro/FreeChaF) | GPLv3 | Binary-version candidate: [`76c7a84f1f7e80f3e6f2bba96fe100cb24e99124`](https://github.com/libretro/FreeChaF/commit/76c7a84f1f7e80f3e6f2bba96fe100cb24e99124) | `6e76af01f852f74600c843b65e716ab760d0519a0d36964c79bb9ad94510fc84` |
| [freeintv](https://github.com/libretro/FreeIntv) | GPLv2+ | Binary-version candidate: [`ef3e0fe322bec62a7f916c0bb0834c08c348d0b4`](https://github.com/libretro/FreeIntv/commit/ef3e0fe322bec62a7f916c0bb0834c08c348d0b4) | `9efbe6c1f5329eeaf5085e6c0eefa28952fe6d0480d73b60c55674dbea6aefff` |
| [o2em](https://github.com/libretro/libretro-o2em) | Artistic-2.0 | Binary-version candidate: [`679d6fec04963f6e70a7ec217e3d0ebb1fe472fc`](https://github.com/libretro/libretro-o2em/commit/679d6fec04963f6e70a7ec217e3d0ebb1fe472fc) | `6f18b3072bcca30c3d7251e20a8bd03d8f2819d3531d70d93064170991518afd` |
| [mednafen_pcfx](https://github.com/libretro/beetle-pcfx-libretro) | GPLv2 | Binary-version candidate: [`c1650bad5fbdcc3c3ccd45e29e3983e1ccf16cff`](https://github.com/libretro/beetle-pcfx-libretro/commit/c1650bad5fbdcc3c3ccd45e29e3983e1ccf16cff) | `8503b85fafd9f6b624501d5b1c1ff6da31f8630be5ead2e9000d9670c40b1a20` |

Nestopia also needs its recorded NeoStation patch (`53847d26b0f914e6fe7ae00415a91f93a5d9573a78453b4947b752b0f9e10d59`); Azahar is the official 2127.0-alpha1 artifact. Only these **two of 34 cores** have exact source revision evidence in this historical delivery. The remaining **32** lack a source-build attestation in that delivery manifest; **19** are labelled GPL/MPL. Further binary inspection recovered version strings for **23** of those cores and resolved each abbreviation to a full upstream commit, recorded as candidates in the table. The remaining **nine** have no such resolved candidate in the historical review. These candidates identify likely upstream bases; they do not establish the complete build inputs or absence of local modifications. To close that gap, obtain each artifact’s matching source and build inputs or replace it with a reproducibly built core from recorded sources. The later PPSSPP replacement is documented in the current-development section; these Build 479 findings and hashes remain unchanged.

The [45 preserved core notice files](../assets/legal/libretro/LIBRETRO_CORES.md) are present in the actual 479 IPA. Their [reference revisions](../assets/legal/libretro/license-sources.json) prove where the license texts were retrieved, not which source built an unrelated buildbot artifact.

**Funding remains a concrete open finding:** FBNeo’s notice prohibits donation solicitation for a project using its source, while the repository and app solicit Patreon support. [Preserved restriction](../assets/legal/libretro/fbneo-src-license.txt). Resolve the solicitation, obtain applicable permission or change the component; source credits do not resolve this condition. Other non-commercial core terms also remain applicable.

### Additional binary evidence recovered in the Build 479 follow-up

The [version-string evidence](evidence/build479-core-version-candidates.json) records the exact observed string and primary upstream commit lookup for each of the 23 candidates. This is an inference from strings embedded in the actual delivered binaries and resolved Git history, not a reproducible-build attestation. The artifact metadata above remains verbatim and is not rewritten to make it appear that these commits were known at build time.

**SameDuck correction:** its delivery manifest refers to LIJI32/SameBoy ancestry, but the observed `0.13.6 040e19c` resolves in [libretro/sameduck](https://github.com/libretro/sameduck/commit/040e19c379f00dae10afe0eb0c1b2b019b985bbe). The active inventory names the actual fork and still credits Lior Halphon/LIJI32. Do not treat the ancestral repository as proof of the delivered fork's full source.

The nine cores without a resolved binary-version candidate are `fbneo`, `desmume`, `ppsspp`, `mednafen_pce_fast`, `prosystem`, `pokemini`, `gw`, `ardens` and `uzem`. Numeric ROM identifiers and unrelated dependency hashes were not treated as source commits.
