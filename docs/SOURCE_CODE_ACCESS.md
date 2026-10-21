# Source code access and dependency provenance

**Next-release preparation · 21 October 2026 · Unpublished**

NeoStation's code, local changes, build recipes, dependency notices and source
references must be kept together when preparing a binary distribution. This
record provides access to the reviewed material and identifies what it does
and does not establish. It does not assign a release number, publish an IPA,
or claim that every component has complete corresponding-source coverage.

## 1. NeoStation's source and the changes since 0.0.8

The host repository is [TarbleFR/neostation-ios](https://github.com/TarbleFR/neostation-ios).
Future app bundles record their exact host commit in
`Legal/BUILD_SOURCE_IDENTITY.json` and in
`Legal/Sources/BUILD_SOURCE_EVIDENCE.json`. The latter contains the immutable
host source archive URL and a URL template for each reviewed repository file.
Use that commit when examining a particular IPA. A moving branch such as
`Claude` is convenient for development, but does not identify an older binary.

The [complete tracked-change inventory](evidence/modified-sources-since-0.0.8-2026-10-21.json)
compares public 0.0.8, commit
`bcca4e4a4dc89a96b1dde05d66436af54efd327e`, with the first preparation commit
`fab5ecf3b119b4d84636ad4f4d03218a96279871`. It identifies **1,036 paths**:
680 added, 212 modified and 144 removed. Each entry records its original and
current Git object, change type and immutable source link. The removed Ports
sources remain historical; this inventory does not restore them to the app.
This second audit's own scripts and records are available in the host commit
that contains this document.

The host archive includes tracked local patches and recipes. It does not
recursively include upstream submodules, pub.dev archives, downloaded SDKs or
the unavailable sources of an unidentified binary. Those inputs must be
retrieved from their component records below. An upstream license snapshot
does not identify the source used to compile a binary.

## 2. Packages, engines and native dependencies

| Collection | Source and license record | What is identified |
| --- | --- | --- |
| Dart/Flutter dependencies and local plugins | [Package sources](PACKAGE_SOURCES_AND_LICENSES.md) and [machine-readable inventory](evidence/package-sources-license-audit-2026-10-21.json) | Exact locked archives, their verified digests, repositories, copyright notices, local forks and native download boundaries |
| Embedded engines and JIT helpers | [Engine source inventory](ENGINE_CORRESPONDING_SOURCES.md) and [evidence](evidence/engine-source-license-audit-2026-10-21.json) | Public source pins, NeoStation patches/recipes, available source archives, binary receipts and remaining gaps |
| Rebuilt PPSSPP integration | [Detailed PSP source audit](PPSSPP_SOURCE_AND_LICENSE_AUDIT.md) and [evidence](evidence/ppsspp-source-license-audit-2026-10-21.json) | Exact parent/submodule sources, local changes, actual historical compile/link inputs, dependency notices and license metadata discrepancy |
| Native texture readers | [Notice/source manifest](../assets/legal/textures/license-sources.json) | libarchive, LZMA SDK, copied ARMSX2 reader headers and ps2ktxpak metadata |
| Shader compilers | [glslang source record](../packages/neo_shader_kit/ios/ThirdParty/glslang/SOURCE.txt) and [SPIRV-Cross source record](../packages/neo_shader_kit/ios/ThirdParty/SPIRV-Cross/SOURCE.txt) | Copied source files and exact upstream revisions, distinct from the PPSSPP versions |
| Downloaded artwork and cheat data | [HD creator supplement](HD_TEXTURE_SOURCES_AND_CREDITS.md), [overlay credits](OVERLAY_SOURCES_AND_CREDITS.md) and [cheat credits](CHEAT_CATALOG_SOURCES.md) | Original sources, creators, stated terms and unresolved permissions; these records do not relicense the content |

The 162 entries in `pubspec.lock` comprise 157 hosted packages and five SDK
packages. The lock is unchanged from the public 0.0.8 baseline; the audit also
examines the 19 local workspace packages separately. SDK packages come from
the matching Flutter/Dart SDK, not separate pub.dev archives. Local plugin
changes are in NeoStation's source tree and retain any upstream authorship.

Supplementary notices are collected under `Legal/Packages/`, `Legal/Engines/`
and `Legal/PPSSPP/` in future app bundles. Their manifests identify the exact
source of each retained notice and its SHA-256. The source-preparation archive
`ppsspp497-source-capsule.tar.gz` is 37,917,399 bytes, SHA-256
`b5a457f177951c9ed621d09358f64c2f4a82f4df42e6544a01cb4243163e003c`.
It contains the pinned PSP sources, initialized submodules, NeoStation patch,
ABI, build recipe, original compile log and a recreation script. The detailed
PSP audit records exclusions and the historical configuration that was not
retained. This archive has not been published as a release asset.

## 3. Retrieve the exact hosted package archives

From the reviewed NeoStation checkout:

```sh
python3 build-utils/fetch_locked_package_sources.py --list
python3 build-utils/fetch_locked_package_sources.py --output ../NeoStation-package-sources
```

The collector uses the exact public archive URLs in the inventory and checks
each archive against the SHA-256 recorded in the lock. It leaves the archives
compressed and writes a receipt identifying successes and failures. It does
not run `pub get`, execute package hooks, install an SDK or compile anything.
An existing matching archive is reused; a different existing output is left
untouched and reported as an error. `--package NAME` can be repeated to select
individual dependencies. A verified local archive cache can be supplied with
`--source-cache PATH` to avoid another download.

A Dart package archive may itself contain a compiled library or a hook that
downloads one. Recovering the package does not by itself recover that native
library's corresponding source. The package inventory records these cases
separately, including PDFium, SoLoud's codec libraries and the Google Cast SDK.
Their notices and distribution terms are not replaced by the Dart wrapper's
license. The collector's receipt deliberately does not certify native binary
source correspondence.

## 4. Preserve what the actual build resolved

The legal packager now writes `Legal/Sources/` in future app bundles. In
addition to the maintained source reports and their evidence, it preserves:

- `pubspec.yaml`, `pubspec.lock` and any `pubspec_overrides.yaml`;
- the generated Podfile, matching `Podfile.lock` and `Pods/Manifest.lock` when
  the CocoaPods build sandbox is present;
- the resolved local podspec JSON files and original CocoaPods dependency
  acknowledgements;
- a normalized Flutter plugin selection without runner cache/home paths;
- Flutter framework/engine/Dart version fields when the SDK version file is
  available, and the hashes of Flutter's runtime notice archives when present.

The CocoaPods acknowledgement file already copied by several delivery recipes
as `NeoPlay-Pods-acknowledgements.plist` remains intact. This adds a source
resolution record alongside it; absence from a repository-only checkout is
not evidence that a historical IPA omitted those acknowledgements.

The preflight rejects stale package inventories, altered dependency
declarations, mismatching CocoaPods lockfiles and missing/empty dependency
acknowledgements in an observed CocoaPods sandbox. Archive validation checks
the captured bytes and their relation to the reviewed repository inputs.
When collecting a built app, a recognized nonempty Flutter runtime notice
file is required; archive validation rejects an empty notice record as well.
Source-only tests explicitly record that CocoaPods resolution was not present;
they are not presented as tests of a production IPA.

This record captures the resolution used by a future build. It does not make
an unpinned native download deterministic, replace an absent build receipt,
or establish that an existing SDK binary was produced by a particular public
recipe. Those conclusions require the component-specific evidence.

## 5. Corresponding-source and distribution boundaries

For covered binaries, the GPL's corresponding-source requirements extend
beyond naming an upstream project: they include the applicable source and
scripts needed to build and install the work. Merely providing a different
revision or a general project URL does not establish correspondence. The
precise obligations depend on the applicable license and distribution method.
Primary texts: [GPLv2 section 3](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html#section3),
[GPLv3 sections 1 and 6](https://www.gnu.org/licenses/gpl-3.0.en.html), and the
[GNU source-distribution FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#SourceAndBinaryOnDifferentSites).

Known source and license boundaries remain explicit in the component audits:
unattested buildbot cores; prebuilt native dependencies whose exact build
inputs remain unproven; the RPCS3/host license-compatibility question; the
FFmpeg license label/configuration mismatch; and the unfinished MeloNX
integration's declarations and dependency inventory. Artwork, datasets and
commercial SDK terms retain their own restrictions. The presence of full
notices is not a permission grant for material whose terms remain unknown.

Before distributing a particular new IPA, use that IPA's actual commit,
dependency resolution and binary identities to settle the applicable open
items and provide durable access to its matching sources. Short-lived CI
artifacts and a source URL that has not been tied to the binary are not treated
here as completed source delivery. No release or build is produced by this
source-preparation work.
