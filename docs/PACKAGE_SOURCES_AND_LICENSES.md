# Package sources and licenses — release preparation, 21 October 2026

## Scope and result

This register reviews the frontend dependency declarations at `fab5ecf3b119b4d84636ad4f4d03218a96279871` on `Claude`, compared with public 0.0.8 source `bcca4e4a4dc89a96b1dde05d66436af54efd327e`. It records exact public archives, licenses and provenance without building an IPA, changing runtime code, installing dependencies, publishing a release or assigning a new build number. Emulator engines and StikJIT have their own source records in [SOURCE_CODE_ACCESS.md](SOURCE_CODE_ACCESS.md); shared headers and native packages are covered here.

The **162 locked dependencies are unchanged from public 0.0.8: 157 hosted packages and five Flutter SDK packages**. All 157 exact pub.dev archives were downloaded read-only; their SHA-256 equals both `pubspec.lock` and the exact-version pub.dev response. Their total compressed size is 153,358,112 bytes. The app also has **19 local workspace packages**, which require their own source attribution. The machine-readable evidence is [package-sources-license-audit-2026-10-21.json](evidence/package-sources-license-audit-2026-10-21.json), including every archive URL, digest, original license path, repository/homepage, source declaration and local modification comparison.

The actual public 0.0.8 IPA contains **all 157 hosted root-license texts** in Flutter `NOTICES.Z` and/or CocoaPods acknowledgements. This was established by comparing the exact extracted texts, normalizing whitespace only. Those existing notices must continue to be packaged. This review adds **38 complementary files** (408,476 bytes) under `assets/legal/packages`, chiefly notices that Flutter's root-file collection cannot discover. It does not replace the generated notices or declare the next binary compliant without inspecting its actual dependencies and notices.

## What is preserved now

[license-sources.json](../assets/legal/packages/license-sources.json) contains the SHA-256, source URL or archive path and copying method for every added file. Whole license files are copied byte for byte. Source-comment collections retain exact complete comments with explicit filenames; they do not rewrite upstream permissions.

| Component | Files | Retained notices |
|---|---:|---|
| Google Cast SDK 4.8.6: embedded open-source components | 2 | `GoogleCast-4.8.6-OpenSourceLicenses.txt`, `GoogleCast-4.8.6-OpenSourceLicenses-index.plist` |
| PDFium chromium/7811 original iOS distribution and dependencies | 16 | `PDFium-7811-builder-LICENSE.txt`, `PDFium-7811-abseil.txt`, `PDFium-7811-agg23.txt`, `PDFium-7811-fast_float.txt`, `PDFium-7811-freetype.txt`, `PDFium-7811-icu.txt`, `PDFium-7811-lcms.txt`, `PDFium-7811-libjpeg_turbo.ijg`, `PDFium-7811-libjpeg_turbo.md`, `PDFium-7811-libopenjpeg.txt`, `PDFium-7811-libpng.txt`, `PDFium-7811-libtiff.txt`, `PDFium-7811-llvm-libc.txt`, `PDFium-7811-pdfium.txt`, `PDFium-7811-simdutf.txt`, `PDFium-7811-zlib.txt` |
| flutter_soloud 4.0.12: SoLoud engine and native source notices | 5 | `SoLoud-Zlib-LICENSE.txt`, `Signalsmith-Stretch-MIT-LICENSE.txt`, `Signalsmith-Linear-MIT-LICENSE.txt`, `PFFFT-FFTPACK-Notices.txt`, `SoLoud-Embedded-Source-Notices.txt` |
| Xiph libraries supplied by flutter_soloud 4.0.12 | 4 | `Xiph-ogg-COPYING.txt`, `Xiph-vorbis-COPYING.txt`, `Xiph-opus-COPYING.txt`, `Xiph-flac-COPYING.Xiph.txt` |
| Local Flutter plugin forks: original authors and licenses | 3 | `gamepads_platform_interface-MIT-LICENSE.txt`, `gamepads-MIT-and-Modification-Notice.txt`, `flutter_7zip-LGPL-2.1.txt` |
| Khronos Vulkan Headers: complete MIT option | 2 | `Vulkan-Headers-MIT.txt`, `Vulkan-Headers-Copyright-Notices.txt` |
| rcheevos 12.5.0: nested MD5 and tiny-AES notices | 2 | `rcheevos-MD5-Notices.txt`, `tiny-AES-c-Unlicense.txt` |
| libretro public API headers | 1 | `libretro-API-Header-Notices.txt` |
| Quiver 3.2.2: Apache NOTICE supplement | 1 | `quiver-NOTICE.txt` |
| Anta Regular font | 1 | `Anta-OFL-1.1.txt` |
| SQLite 3.53.3 public-domain dedication | 1 | `SQLite-Public-Domain.txt` |

The full `hosted_packages` array intentionally identifies source archives separately from native binaries. An archive containing a prebuilt `.a` or a build hook that downloads a framework is not evidence that the corresponding native source is contained in that archive.

## Public baseline and Flutter collection

The [public 0.0.8 IPA](https://github.com/TarbleFR/RewindBox/releases/download/0.0.8/NeoStation-0.0.8.ipa) has SHA-256 `2e9f1868e6dc98d3724740727286639909851cc9d2215380f68e7340ed39825c`, matching its [published checksum list](https://github.com/TarbleFR/RewindBox/releases/download/0.0.8/NeoStation-0.0.8-SHA256SUMS.txt). Its Flutter notice stream is `Payload/NeoStation.app/Frameworks/App.framework/flutter_assets/NOTICES.Z` (SHA-256 `3246363c6bd28038dc0e27fac39e816ac913913ec1ed78cb4280962bb4f0311e`); the CocoaPods acknowledgement plist is `Payload/NeoStation.app/NeoPlay-Pods-acknowledgements.plist` (SHA-256 `2d3e12557dec8cf045f8e180d835c3343013cd88ebe1bbd9cfff826227426ddf`). The separate public license ZIP does not contain those two files, but the IPA does. The baseline is build480, not build500 and not a future artifact.

The workflow declares Flutter **3.47.2**, tag commit `d3b14c876900e553bc736ca19295fc09e3853e8e`; its `engine.version` is `a804b261645ef8c13eb3d5c44a5c2fb0340c5539`. The [exact LicenseCollector source](https://github.com/flutter/flutter/blob/d3b14c876900e553bc736ca19295fc09e3853e8e/packages/flutter_tools/lib/src/license_collector.dart) reads root `NOTICES`, otherwise root `LICENSE`, plus explicitly configured `flutter.licenses`. It does not recursively collect native license files or singular `NOTICE`. None of the examined hosted declarations supplies additional `flutter.licenses`. The actual SDK/engine identity used by the future build still needs its build receipt.

The 157 root texts classify as **109 BSD-3-Clause, 36 MIT, 10 Apache-2.0 and two MPL-2.0**. These classifications concern the root license only; nested native components retain their own terms. The MPL packages `dbus` and `upower` occur in Linux platform alternatives. A package's presence in the lockfile does not prove that its code is linked in the iOS app. Following runtime dependency declarations, including the exact SDK pubspecs, reaches **136 hosted packages**; **21** occur only through build/dev declaration paths. The runtime declaration graph also includes platform alternatives and native build hooks, so it is not an iOS binary inventory.

## Local workspace packages and modifications

The source comparison uses tracked files and the public source baseline, not just package version strings. The actual modified paths are retained in the JSON. Newly added packages such as `neo_box_reader` and `neo_texture_catalog` are original wrappers with project license declarations; imported third-party sources are separately identified.

| Local package | Declared version | Since public 0.0.8 | License/provenance assessment |
|---|---|---|---|
| `armsx2_internal_bridge` | 0.1.0 | modified (24 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `dolphin_internal_bridge` | 0.1.0 | modified (10 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `external_display` | 0.1.0 | modified (3 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `external_folder_access` | 0.0.1 | unchanged (0 files) | Podspec declares MIT, but no standalone package LICENSE was found; owner clarification remains open |
| `flutter_7zip` | 0.0.1 | unchanged (0 files) | LGPL-2.1; LZMA SDK C subset public domain |
| `gamepads` | 0.1.8+2 | unchanged (0 files) | MIT; retained NeoGameLab modification notice |
| `gamepads_darwin` | 0.1.2+2 | unchanged (0 files) | MIT |
| `gamepads_platform_interface` | 0.1.2+1 | unchanged (0 files) | MIT; missing local license now preserved centrally |
| `libretro_internal_bridge` | 0.1.0 | modified (8 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `neo_box_reader` | 0.1.0 | added (7 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `neo_cheat_catalog` | 0.1.0 | unchanged (0 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `neo_shader_kit` | 0.1.0 | unchanged (0 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `neo_swap` | 0.1.0 | unchanged (0 files) | Mixed file-level declarations: project GPL-3.0-or-later plus MIT notices, including GuestPageRelay; see dedicated source register |
| `neo_texture_catalog` | 0.1.0 | added (132 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `neo_touch_layout` | 0.1.0 | added (19 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `neoplay_bridge` | 0.1.0 | modified (1 files) | Podspec explicitly declares GPL-3.0-or-later for the wrapper; Google Cast SDK retains its separate commercial terms |
| `rpcs3_internal_bridge` | 0.1.0 | modified (11 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `stikjit_bridge` | 0.0.2 | modified (3 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |
| `ui_refresh_rate` | 0.1.0 | unchanged (0 files) | Local wrapper with project GPL-3.0 declaration; GPL-3.0-or-later where explicitly marked in source; third-party file licenses remain authoritative |

### Original authors of local forks

**flutter_7zip** originates from [wgh136/flutter_7zip](https://github.com/wgh136/flutter_7zip/tree/5ecef8aa66e930f50b06bbc89987adc9ddc5332e). Against exact commit `5ecef8aa66e930f50b06bbc89987adc9ddc5332e`, 110 local files are identical, including 98 files under `src/` and one Dart binding file; `src/CMakeLists.txt` is the recorded source-tree difference; nine files differ. The archive digest and complete comparison are in the JSON. Differences concern package metadata, platform/build configuration, formatting and a comment in the iOS shim; the local `LICENSE` differs only by a trailing newline. The original import commit is not recorded locally, so this is a verified comparison reference, not a claim that git ancestry was reconstructed. The wrapper is **LGPL-2.1**. Its bundled **LZMA SDK 24.09 C subset** carries Igor Pavlov's public-domain dedication; that does not relicense the wrapper. Template `Your Company`/`example.com` podspec fields are not reliable upstream attribution. Original and modified corresponding sources must remain available under the applicable license conditions.

**gamepads**, **gamepads_darwin** and **gamepads_platform_interface** were compared with their exact [Flame/Blue Fire published packages](https://github.com/flame-engine/gamepads): `0.1.8+2`, `0.1.2+2` and `0.1.2+1`. The local `gamepads/LICENSE` retains Blue Fire's MIT notice and explicitly identifies NeoGameLab modifications for RewindBox. The local Darwin package adapts the original macOS package to iOS. The platform-interface package modifies the API and adds `gamepad_info.dart`; its missing local license is now preserved in the central notice collection from the exact upstream archive. No upstream work is attributed solely to RewindBox.

`external_folder_access` is different: its local podspec declares MIT and RewindBox author information, but there is no standalone package license text or verifiable external package source in its metadata. This audit preserves the declaration as evidence and leaves owner clarification open instead of inventing a grant. `neo_swap` contains mixed file-level MIT and project GPL declarations; the package is not relabeled as exclusively one license.

| Compared source | Byte comparison |
|---|---|
| `flutter_7zip` | 110 identical, 9 different |
| `gamepads` | 2 local_only, 6 different |
| `gamepads_darwin` | 5 local_only, 2 different |
| `gamepads_platform_interface` | 3 local_only, 6 different, 1 identical |
| `rcheevos` | 60 identical |
| `glslang` | 101 identical, 1 local_only |
| `SPIRV-Cross` | 19 identical |
| `Vulkan-Headers` | 17 identical |

## SoLoud and native audio dependencies

[`flutter_soloud` 4.0.12](https://pub.dev/api/archives/flutter_soloud-4.0.12.tar.gz) supplies its own MIT package license, SoLoud's Zlib license, Signalsmith MIT licenses, PFFFT/NCAR notices and source-embedded notices. Its iOS mirrored source copies were compared for the primary notice files. The package-root MIT license was present in the public IPA; it does not replace the native source notices. The new collection preserves complete source notices, including David Reid's dual public-domain/MIT-0 headers, Sean Barrett's stb_vorbis notice, minimp3, Ooura FFT, Freeverb, and the other license-bearing source headers present in the archive. Conditional sources are credited without claiming every backend is linked on iOS.

The same package carries five device static libraries. Their measured identities are:

| iOS device archive | Bytes | SHA-256 |
|---|---:|---|
| `libFLAC_iOS-device.a` | 385,336 | `28b41301e4e374d8f764617e1d8fce168af9522c2894454380df409a80df1c7c` |
| `libogg_iOS-device.a` | 28,848 | `84627eb1e4e509d14609fdccf0fb97ae65217e06ae477a604b8a7e68caeecb96` |
| `libopus_iOS-device.a` | 608,776 | `b994421c7e6ec5179233b8834535abb01fab0205ab91cae6a0677f537cb3e840` |
| `libvorbis_iOS-device.a` | 230,240 | `4836a59aab95d1684749314430826f76029a978795e3f63696d01815e7649e9c` |
| `libvorbisfile_iOS-device.a` | 28,672 | `240182a8f3f8e8e5d88ac6a0ce705c4cba181f4c87013793ca8ce7692ab8aece` |

The exact package recipe `xiph/build_iOS.sh` pins **Ogg `db5c7a49ce7ebda47b15b78471e78fb7f2483e22`**, **Vorbis `84c023699cdf023a32fa4ded32019f194afcdad0`**, **Opus `c79a9bd1dd2898cd57bb793e037d58c937555c2c`** and **FLAC `9547dbc2ddfca06a70ea937dbb605bbe78ea5f90`**. Their original notices were copied from those exact primary revisions. The recipe and these binary hashes establish identifiable inputs; **they do not establish that those prebuilt archives were reproducibly generated from those sources**. The original Xiph source trees are not bundled in the Dart archive. The default podspec links these libraries unless `NO_XIPH_LIBS` is enabled; no app override was found in the reviewed declarations. Opus's original notice includes its patent-license references, which remain intact.

## PDFium: recovering the notices of the matching original binary

The locked chain is `pdfrx 2.4.7` → `pdfrx_engine 0.4.6` → `pdfium_flutter 0.2.3` / `pdfium_dart 0.2.5`. The iOS podspec inside `pdfium_flutter` calls itself `0.1.5`; this internal pod version is distinct from the Dart package version. It downloads [this exact PDFium xcframework](https://github.com/espresso3389/pdfium-xcframework/releases/download/v144.0.7811.0-20260502-190206/PDFium-chromium-7811-20260502-190206.xcframework.zip) and verifies SHA-256 `948d9257f53f01cbed74b81bb8adc8758e52ac9390751772de7889026d32d5a1`. That ZIP contains no license files.

The [repackager release](https://github.com/espresso3389/pdfium-xcframework/releases/tag/v144.0.7811.0-20260502-190206) points to `bblanchon/pdfium-binaries` branch/build family `chromium/7811`. The [original iOS arm64 distribution](https://github.com/bblanchon/pdfium-binaries/releases/download/chromium/7811/pdfium-ios-device-arm64.tgz) has SHA-256 `36f5b10feed4c88452517844902b5ba1530eae46dbb0d48ddd0519f841bb4224`. All **15 non-zerofill Mach-O sections** in its dylib match the repackaged framework. The differing load commands are `LC_ID_DYLIB` and `LC_BUILD_VERSION`; command reordering was accounted for. The same section comparison with the public 0.0.8 PDFium binary is `True`. This evidence supports using the original distribution's accompanying notices for this binary family; it is not a source rebuild.

All **16 original license files** are now retained, including the builder's Benoit Blanchon MIT notice and PDFium, ICU, zlib, libjpeg-turbo/IJG, LLVM libc, lcms, libpng, AGG, OpenJPEG, FreeType, libtiff, fast_float, Abseil and simdutf notices. The full original license set is retained even where build arguments disable an optional feature; this avoids treating the wrapper's MIT notice as the entire dependency notice set.

There is a real version-label inconsistency: the repackager tag says **144.0.7811.0**, whereas the original distribution's `VERSION` says **MAJOR=149
MINOR=0
BUILD=7811
PATCH=0**. Both are retained in the evidence. The original published attestation names builder commit `f72e059ccf6dccec9fcf79f1fe4a33bf48133a58` and the exact original archive hash; its JSON payload was read, but its cryptographic signature was not independently verified. The exact PDFium/Chromium dependency source closure still requires the original builder's resolved sources. The sibling `pdfium_dart` hook's other-platform downloads are not treated as an iOS loader: the examined hook returns early for iOS.

## SQLite native asset

`sqlite3 3.5.0` uses a native build hook. For the reviewed default `sqlite3` source, its [iOS arm64 dylib](https://github.com/simolus3/sqlite3.dart/releases/download/sqlite3-3.5.0/libsqlite3.arm64.ios.dylib) has SHA-256 `14ddadc35d7e92e58e219a34dc4a9b66fd5b195c9e144dcfed06978a65dfaba9`, equal to the package's pinned asset hash. The package verifies that hash. The [exact builder source](https://github.com/simolus3/sqlite3.dart/tree/380d6fe397de00f2272a948312dc5420df215838) selects the [official SQLite 3.53.3 amalgamation](https://sqlite.org/2026/sqlite-amalgamation-3530300.zip). Its source identifier `2026-06-26 20:14:12 d4c0e51e4aeb96955b99185ab9cde75c339e2c29c3f3f12428d364a10d782c62` is also present in the downloaded binary. The public-domain dedication is retained from the original header. A matching source marker is useful provenance, not proof of a reproducible build. Optional SQLCipher, sqlite3mc and custom-amalgamation paths are not asserted to be selected by RewindBox.

## Google Cast and CocoaPods

`packages/neoplay_bridge/ios/neoplay_bridge.podspec` pins `google-cast-sdk` **4.8.6**. Its [exact CocoaPods specification](https://cdn.cocoapods.org/Specs/8/1/2/google-cast-sdk/4.8.6/google-cast-sdk.podspec.json) declares **Commercial**, refers to [Google API terms](https://developers.google.com/terms/) and [Cast terms](https://developers.google.com/cast/docs/terms/), and downloads the static SDK archive identified in the JSON. The archive's measured SHA-256 is `e1fe7fd6f2bf4b58e830d378fafc435d159bd755f7ee20fd3033aa1ce313cd6e`; the podspec itself does not declare that checksum.

The original `OpenSourceLicenses/oss_licenses.bin` is UTF-8 text outside the vendored xcframework directory. It is copied **byte for byte** as `GoogleCast-4.8.6-OpenSourceLicenses.txt`, together with the exact offset/size index plist. The index names 20 entries, including Abseil, Eigen, gRPC, Protocol Buffers, Google Toolbox for Mac, Kiss FFT, SimplePing, TCMalloc and the time-zone database. The public CocoaPods acknowledgement for Google Cast contains only a terms URL; it does not reproduce this complete file. These open-source notices apply to their named components and **do not authorize relicensing Google Cast SDK itself under RewindBox's GPL or another open-source license**.

The SDK podspec depends on **GTMSessionFetcher without a version constraint**. The repository generates `ios` in CI; no resolved `Podfile.lock` or Pods source tree was available in this checkout. The public acknowledgement plist proves existing notices, but not every resolved pod version. Future source evidence should preserve `ios/Podfile`, `ios/Podfile.lock`, `ios/Pods/Manifest.lock`, the resolved `Local Podspecs/*.podspec.json`, and the actual `Pods-Runner-acknowledgements` plist/Markdown. CocoaPods source URLs, selected subspecs and checksums must come from that actual resolution; no guessed lockfile is created here.

## Shared vendored headers and shader compilers

The reviewed `SOURCE.txt` files are included in the declaration-hash gate. Source comparisons found **60 rcheevos files** identical to v12.5.0 (`1433173220a7eaede6a9ed7a18e94117be1821e0`); nested Aladdin/L. Peter Deutsch MD5 notices and the [tiny-AES Unlicense](https://github.com/kokke/tiny-AES-c/blob/f06ac37fc31dfdaca2e0d9bec83f90d5663c319b/unlicense.txt) supplement its existing root MIT notice. The exact two [libretro public API headers](https://github.com/libretro/RetroArch/tree/df16ef193cbe385b87e8a1cf27b66da35bf3c0e0/libretro-common/include) retain their own MIT notices.

The selected Vulkan headers match [Khronos SDK 1.4.341.0](https://github.com/KhronosGroup/Vulkan-Headers/tree/b5c8f996196ba4aa6d8f97e52b5d3b6e70f7e4e2). Their SPDX choice is `Apache-2.0 OR MIT`; the previously bundled short `LICENSE.md` was a license index. The full MIT grant and the selected headers' copyright notices are now preserved. This does not relicense unrelated Vulkan SDK components.

The shader kit has **101 glslang files** identical to [commit 275822a…](https://github.com/KhronosGroup/glslang/tree/275822a6261ee689aadb1da5f09a0ec2f058685c), plus its expected generated `glslang/build_info.h`, and **19 SPIRV-Cross files** identical to [commit 1a61695…](https://github.com/KhronosGroup/SPIRV-Cross/tree/1a6169566c73d3da552748fc372fe2bbb856e46e). Their complete existing license collections remain in place. No shader source or build pin was changed.

## Anta and ancillary notices

The app calls `GoogleFonts.anta`. The exact font selected by `google_fonts 8.1.0` is [this 49,080-byte TTF](https://fonts.gstatic.com/s/a/3ae97fe71a58efbc643d4f14321f6647139063c17dc68ea5977866642b79765b.ttf), whose measured SHA-256 is the package's expected `3ae97fe71a58efbc643d4f14321f6647139063c17dc68ea5977866642b79765b`. Its font copyright record agrees with the [Google Fonts OFL file](https://raw.githubusercontent.com/google/fonts/d4c32fb590ca920dcaa125b98bda1f6a40cb6960/ofl/anta/OFL.txt): **Copyright 2019 The Anta Project Authors**. The primary metadata names designer **Sergej Lebedev** and source [Typedesigners/Anta-Regular](https://github.com/Typedesigners/Anta-Regular/tree/7ef14d1901946d317cb3bc136a895ff6c74c246c). The complete OFL 1.1 is now preserved; no font binary or runtime behavior is changed. No Anta-specific notice was found in the baseline Flutter notice text, and the app has no `LicenseRegistry.addLicense` call. Retaining it centrally does not make an unsupported claim that Flutter's LicensePage now displays it.

Quiver's exact singular `NOTICE` is also preserved. Package archives containing test/example-only license files (`csslib`, `html`, `ffigen`, Windows examples) are inventoried without calling those files iOS runtime components. PointyCastle's root MIT already credits the Legion of the Bouncy Castle and is present in the baseline; its old nested HTML license file contains stale comments, so this audit does not infer a new package-wide license from those comments.

## Remaining release evidence

1. Resolve the `external_folder_access` MIT declaration versus missing standalone license with the owner. No new legal grant is fabricated.
2. Retain the actual future CocoaPods resolution, Flutter/engine identity and final notice files. These declarations and the public baseline do not identify every future binary.
3. Keep native binary digests separate from corresponding sources. SoLoud's Xiph build pins and PDFium's binary-section correspondence are documented with their limits; neither is advertised as a reproducible build proof.
4. Keep Google Cast's commercial/API conditions distinct from its bundled open-source notices, and retain the PDFium version-label discrepancy until its source provenance is reconciled.
5. Verify that the future packaged app exposes the complete central legal collection together with Flutter and CocoaPods notices. No release or IPA was generated for this review.

The JSON binds its inventory to `pubspec.lock` SHA-256 `6ceb0c3787c1c35c844950338e99e408ff548dbc4aacfff0270c5b1ddd285a8e` and hashes **51 source/license declaration files**. These are the root pubspec/override/license, 19 workspace pubspecs, 21 local podspecs, five vendored source declarations and three local package license files. Runtime implementation files are not frozen by this gate. A later dependency declaration or license change requires refreshing this review rather than silently reusing the previous inventory.

## Complete hosted dependency register

Every row below is unchanged from the public lockfile. Exact archive SHA-256, repository/homepage metadata, all found notice paths, native binary hints and baseline coverage are in the companion JSON. “Runtime declaration graph” includes unused platform alternatives and hooks; it is not a statement that every listed dependency is embedded in iOS.

| Package | Exact locked version | Lock role | Root license | Declaration reachability | Primary source |
|---|---|---|---|---|---|
| `_fe_analyzer_shared` | `99.0.0` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/_fe_analyzer_shared-99.0.0.tar.gz) |
| `analyzer` | `12.1.0` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/analyzer-12.1.0.tar.gz) |
| `animated_toggle_switch` | `0.8.7` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/animated_toggle_switch-0.8.7.tar.gz) |
| `archive` | `4.0.9` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/archive-4.0.9.tar.gz) |
| `args` | `2.7.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/args-2.7.0.tar.gz) |
| `async` | `2.13.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/async-2.13.1.tar.gz) |
| `audio_metadata_reader` | `1.7.1` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/audio_metadata_reader-1.7.1.tar.gz) |
| `battery_plus` | `7.1.1` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/battery_plus-7.1.1.tar.gz) |
| `battery_plus_platform_interface` | `2.0.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/battery_plus_platform_interface-2.0.1.tar.gz) |
| `boolean_selector` | `2.1.2` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/boolean_selector-2.1.2.tar.gz) |
| `characters` | `1.4.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/characters-1.4.1.tar.gz) |
| `charset` | `2.0.1` | transitive | Apache-2.0 | runtime declaration graph | [exact archive](https://pub.dev/api/archives/charset-2.0.1.tar.gz) |
| `checked_yaml` | `2.0.4` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/checked_yaml-2.0.4.tar.gz) |
| `cli_util` | `0.4.2` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/cli_util-0.4.2.tar.gz) |
| `clock` | `1.1.2` | transitive | Apache-2.0 | runtime declaration graph | [exact archive](https://pub.dev/api/archives/clock-1.1.2.tar.gz) |
| `code_assets` | `1.0.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/code_assets-1.0.0.tar.gz) |
| `collection` | `1.19.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/collection-1.19.1.tar.gz) |
| `convert` | `3.1.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/convert-3.1.2.tar.gz) |
| `cross_file` | `0.3.5+2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/cross_file-0.3.5%2B2.tar.gz) |
| `crypto` | `3.0.7` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/crypto-3.0.7.tar.gz) |
| `csslib` | `1.0.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/csslib-1.0.2.tar.gz) |
| `dart_style` | `3.1.8` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/dart_style-3.1.8.tar.gz) |
| `dbus` | `0.7.12` | transitive | MPL-2.0 | runtime declaration graph | [exact archive](https://pub.dev/api/archives/dbus-0.7.12.tar.gz) |
| `device_info_plus` | `13.2.0` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/device_info_plus-13.2.0.tar.gz) |
| `device_info_plus_platform_interface` | `8.1.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/device_info_plus_platform_interface-8.1.0.tar.gz) |
| `fading_edge_scrollview` | `4.1.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/fading_edge_scrollview-4.1.1.tar.gz) |
| `fake_async` | `1.3.3` | transitive | Apache-2.0 | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/fake_async-1.3.3.tar.gz) |
| `ffi` | `2.2.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/ffi-2.2.0.tar.gz) |
| `ffi_leak_tracker` | `0.1.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/ffi_leak_tracker-0.1.2.tar.gz) |
| `ffigen` | `20.1.1` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/ffigen-20.1.1.tar.gz) |
| `file` | `7.0.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/file-7.0.1.tar.gz) |
| `file_picker` | `12.0.0-beta.3` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/file_picker-12.0.0-beta.3.tar.gz) |
| `fixnum` | `1.1.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/fixnum-1.1.1.tar.gz) |
| `flutter_launcher_icons` | `0.14.4` | direct dev | MIT | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/flutter_launcher_icons-0.14.4.tar.gz) |
| `flutter_lints` | `6.0.0` | direct dev | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/flutter_lints-6.0.0.tar.gz) |
| `flutter_localization` | `0.4.1` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/flutter_localization-0.4.1.tar.gz) |
| `flutter_plugin_android_lifecycle` | `2.0.34` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/flutter_plugin_android_lifecycle-2.0.34.tar.gz) |
| `flutter_screenutil` | `5.9.3` | direct main | Apache-2.0 | runtime declaration graph | [exact archive](https://pub.dev/api/archives/flutter_screenutil-5.9.3.tar.gz) |
| `flutter_secure_storage` | `10.3.1` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/flutter_secure_storage-10.3.1.tar.gz) |
| `flutter_secure_storage_darwin` | `0.3.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/flutter_secure_storage_darwin-0.3.2.tar.gz) |
| `flutter_secure_storage_linux` | `3.0.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/flutter_secure_storage_linux-3.0.1.tar.gz) |
| `flutter_secure_storage_platform_interface` | `2.0.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/flutter_secure_storage_platform_interface-2.0.1.tar.gz) |
| `flutter_secure_storage_web` | `2.1.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/flutter_secure_storage_web-2.1.1.tar.gz) |
| `flutter_secure_storage_windows` | `4.2.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/flutter_secure_storage_windows-4.2.2.tar.gz) |
| `flutter_soloud` | `4.0.12` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/flutter_soloud-4.0.12.tar.gz) |
| `fullscreen_window` | `1.2.1` | direct main | Apache-2.0 | runtime declaration graph | [exact archive](https://pub.dev/api/archives/fullscreen_window-1.2.1.tar.gz) |
| `glob` | `2.1.3` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/glob-2.1.3.tar.gz) |
| `google_fonts` | `8.1.0` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/google_fonts-8.1.0.tar.gz) |
| `hooks` | `1.0.3` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/hooks-1.0.3.tar.gz) |
| `html` | `0.15.6` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/html-0.15.6.tar.gz) |
| `http` | `1.6.0` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/http-1.6.0.tar.gz) |
| `http_parser` | `4.1.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/http_parser-4.1.2.tar.gz) |
| `image` | `4.8.0` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/image-4.8.0.tar.gz) |
| `intl` | `0.20.3` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/intl-0.20.3.tar.gz) |
| `jni` | `1.0.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/jni-1.0.0.tar.gz) |
| `jni_flutter` | `1.0.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/jni_flutter-1.0.1.tar.gz) |
| `json_annotation` | `4.12.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/json_annotation-4.12.0.tar.gz) |
| `leak_tracker` | `11.0.2` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/leak_tracker-11.0.2.tar.gz) |
| `leak_tracker_flutter_testing` | `3.0.10` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/leak_tracker_flutter_testing-3.0.10.tar.gz) |
| `leak_tracker_testing` | `3.0.2` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/leak_tracker_testing-3.0.2.tar.gz) |
| `lints` | `6.1.0` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/lints-6.1.0.tar.gz) |
| `logger` | `2.7.0` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/logger-2.7.0.tar.gz) |
| `logging` | `1.3.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/logging-1.3.0.tar.gz) |
| `marquee` | `2.3.0` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/marquee-2.3.0.tar.gz) |
| `matcher` | `0.12.20` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/matcher-0.12.20.tar.gz) |
| `material_color_utilities` | `0.13.0` | transitive | Apache-2.0 | runtime declaration graph | [exact archive](https://pub.dev/api/archives/material_color_utilities-0.13.0.tar.gz) |
| `material_symbols_icons` | `4.2960.0` | direct main | Apache-2.0 | runtime declaration graph | [exact archive](https://pub.dev/api/archives/material_symbols_icons-4.2960.0.tar.gz) |
| `meta` | `1.19.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/meta-1.19.0.tar.gz) |
| `mime` | `2.0.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/mime-2.0.0.tar.gz) |
| `native_toolchain_c` | `0.17.6` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/native_toolchain_c-0.17.6.tar.gz) |
| `nested` | `1.0.0` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/nested-1.0.0.tar.gz) |
| `objective_c` | `9.3.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/objective_c-9.3.0.tar.gz) |
| `package_config` | `2.2.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/package_config-2.2.0.tar.gz) |
| `package_info_plus` | `10.2.1` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/package_info_plus-10.2.1.tar.gz) |
| `package_info_plus_platform_interface` | `4.1.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/package_info_plus_platform_interface-4.1.0.tar.gz) |
| `path` | `1.9.1` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/path-1.9.1.tar.gz) |
| `path_provider` | `2.1.6` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/path_provider-2.1.6.tar.gz) |
| `path_provider_android` | `2.3.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/path_provider_android-2.3.1.tar.gz) |
| `path_provider_foundation` | `2.6.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/path_provider_foundation-2.6.0.tar.gz) |
| `path_provider_linux` | `2.2.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/path_provider_linux-2.2.1.tar.gz) |
| `path_provider_platform_interface` | `2.1.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/path_provider_platform_interface-2.1.2.tar.gz) |
| `path_provider_windows` | `2.3.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/path_provider_windows-2.3.0.tar.gz) |
| `pdfium_dart` | `0.2.5` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/pdfium_dart-0.2.5.tar.gz) |
| `pdfium_flutter` | `0.2.3` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/pdfium_flutter-0.2.3.tar.gz) |
| `pdfrx` | `2.4.7` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/pdfrx-2.4.7.tar.gz) |
| `pdfrx_engine` | `0.4.6` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/pdfrx_engine-0.4.6.tar.gz) |
| `permission_handler` | `12.0.3` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/permission_handler-12.0.3.tar.gz) |
| `permission_handler_android` | `13.0.1` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/permission_handler_android-13.0.1.tar.gz) |
| `permission_handler_apple` | `9.4.7` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/permission_handler_apple-9.4.7.tar.gz) |
| `permission_handler_html` | `0.1.3+5` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/permission_handler_html-0.1.3%2B5.tar.gz) |
| `permission_handler_platform_interface` | `4.3.0` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/permission_handler_platform_interface-4.3.0.tar.gz) |
| `permission_handler_windows` | `0.2.1` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/permission_handler_windows-0.2.1.tar.gz) |
| `petitparser` | `7.0.2` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/petitparser-7.0.2.tar.gz) |
| `platform` | `3.1.6` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/platform-3.1.6.tar.gz) |
| `plugin_platform_interface` | `2.1.8` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/plugin_platform_interface-2.1.8.tar.gz) |
| `pointycastle` | `4.0.0` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/pointycastle-4.0.0.tar.gz) |
| `posix` | `6.5.0` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/posix-6.5.0.tar.gz) |
| `provider` | `6.1.5+1` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/provider-6.1.5%2B1.tar.gz) |
| `pub_semver` | `2.2.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/pub_semver-2.2.0.tar.gz) |
| `quiver` | `3.2.2` | transitive | Apache-2.0 | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/quiver-3.2.2.tar.gz) |
| `record_use` | `0.6.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/record_use-0.6.0.tar.gz) |
| `rxdart` | `0.28.0` | transitive | Apache-2.0 | runtime declaration graph | [exact archive](https://pub.dev/api/archives/rxdart-0.28.0.tar.gz) |
| `screen_retriever` | `0.2.2` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/screen_retriever-0.2.2.tar.gz) |
| `screen_retriever_linux` | `0.2.2` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/screen_retriever_linux-0.2.2.tar.gz) |
| `screen_retriever_macos` | `0.2.2` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/screen_retriever_macos-0.2.2.tar.gz) |
| `screen_retriever_platform_interface` | `0.2.2` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/screen_retriever_platform_interface-0.2.2.tar.gz) |
| `screen_retriever_windows` | `0.2.2` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/screen_retriever_windows-0.2.2.tar.gz) |
| `share_plus` | `13.3.0` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/share_plus-13.3.0.tar.gz) |
| `share_plus_platform_interface` | `7.2.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/share_plus_platform_interface-7.2.0.tar.gz) |
| `shared_preferences` | `2.5.5` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/shared_preferences-2.5.5.tar.gz) |
| `shared_preferences_android` | `2.4.23` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/shared_preferences_android-2.4.23.tar.gz) |
| `shared_preferences_foundation` | `2.5.6` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/shared_preferences_foundation-2.5.6.tar.gz) |
| `shared_preferences_linux` | `2.4.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/shared_preferences_linux-2.4.1.tar.gz) |
| `shared_preferences_platform_interface` | `2.4.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/shared_preferences_platform_interface-2.4.2.tar.gz) |
| `shared_preferences_web` | `2.4.3` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/shared_preferences_web-2.4.3.tar.gz) |
| `shared_preferences_windows` | `2.4.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/shared_preferences_windows-2.4.1.tar.gz) |
| `source_span` | `1.10.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/source_span-1.10.2.tar.gz) |
| `sqlite3` | `3.5.0` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/sqlite3-3.5.0.tar.gz) |
| `stack_trace` | `1.12.1` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/stack_trace-1.12.1.tar.gz) |
| `stream_channel` | `2.1.4` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/stream_channel-2.1.4.tar.gz) |
| `string_scanner` | `1.4.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/string_scanner-1.4.1.tar.gz) |
| `sub_screen` | `0.1.9` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/sub_screen-0.1.9.tar.gz) |
| `synchronized` | `3.4.1+2` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/synchronized-3.4.1%2B2.tar.gz) |
| `term_glyph` | `1.2.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/term_glyph-1.2.2.tar.gz) |
| `test_api` | `0.7.12` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/test_api-0.7.12.tar.gz) |
| `typed_data` | `1.4.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/typed_data-1.4.0.tar.gz) |
| `universal_io` | `2.3.1` | transitive | Apache-2.0 | runtime declaration graph | [exact archive](https://pub.dev/api/archives/universal_io-2.3.1.tar.gz) |
| `upower` | `0.7.0` | transitive | MPL-2.0 | runtime declaration graph | [exact archive](https://pub.dev/api/archives/upower-0.7.0.tar.gz) |
| `url_launcher` | `6.3.2` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/url_launcher-6.3.2.tar.gz) |
| `url_launcher_android` | `6.3.30` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/url_launcher_android-6.3.30.tar.gz) |
| `url_launcher_ios` | `6.4.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/url_launcher_ios-6.4.1.tar.gz) |
| `url_launcher_linux` | `3.2.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/url_launcher_linux-3.2.2.tar.gz) |
| `url_launcher_macos` | `3.2.5` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/url_launcher_macos-3.2.5.tar.gz) |
| `url_launcher_platform_interface` | `2.3.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/url_launcher_platform_interface-2.3.2.tar.gz) |
| `url_launcher_web` | `2.4.3` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/url_launcher_web-2.4.3.tar.gz) |
| `url_launcher_windows` | `3.1.5` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/url_launcher_windows-3.1.5.tar.gz) |
| `uuid` | `4.6.0` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/uuid-4.6.0.tar.gz) |
| `vector_math` | `2.4.2` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/vector_math-2.4.2.tar.gz) |
| `video_player` | `2.13.0` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/video_player-2.13.0.tar.gz) |
| `video_player_android` | `2.12.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/video_player_android-2.12.0.tar.gz) |
| `video_player_avfoundation` | `2.11.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/video_player_avfoundation-2.11.0.tar.gz) |
| `video_player_platform_interface` | `6.9.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/video_player_platform_interface-6.9.0.tar.gz) |
| `video_player_web` | `2.4.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/video_player_web-2.4.0.tar.gz) |
| `vm_service` | `15.2.0` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/vm_service-15.2.0.tar.gz) |
| `wakelock_plus` | `1.7.0` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/wakelock_plus-1.7.0.tar.gz) |
| `wakelock_plus_platform_interface` | `1.6.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/wakelock_plus_platform_interface-1.6.0.tar.gz) |
| `watcher` | `1.2.1` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/watcher-1.2.1.tar.gz) |
| `web` | `1.1.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/web-1.1.1.tar.gz) |
| `web_socket` | `1.0.1` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/web_socket-1.0.1.tar.gz) |
| `web_socket_channel` | `3.0.3` | direct main | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/web_socket_channel-3.0.3.tar.gz) |
| `win32` | `6.3.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/win32-6.3.0.tar.gz) |
| `win32_registry` | `3.0.3` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/win32_registry-3.0.3.tar.gz) |
| `window_manager` | `0.5.2` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/window_manager-0.5.2.tar.gz) |
| `xdg_directories` | `1.1.0` | transitive | BSD-3-Clause | runtime declaration graph | [exact archive](https://pub.dev/api/archives/xdg_directories-1.1.0.tar.gz) |
| `xml` | `6.6.1` | direct main | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/xml-6.6.1.tar.gz) |
| `yaml` | `3.1.3` | transitive | MIT | runtime declaration graph | [exact archive](https://pub.dev/api/archives/yaml-3.1.3.tar.gz) |
| `yaml_edit` | `2.2.4` | transitive | BSD-3-Clause | build/dev declaration graph | [exact archive](https://pub.dev/api/archives/yaml_edit-2.2.4.tar.gz) |
