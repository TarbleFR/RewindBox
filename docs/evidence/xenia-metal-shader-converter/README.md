# Apple Metal Shader Converter: legal dossier for the XeniOS runtime

Received from the maintainer on 12 November 2026 (Europe/Paris); read in full by main.

- `Mentions_Apple_Metal_Shader_Converter_2026-11-12.txt`: 42,354 bytes, SHA-256
  `0a02971e76bbbbf6648d31c37a1a4bed80d8e11f00c755a445b4a970ea9b2236`.
- Contents:
  - the text of « SOFTWARE LICENSE AGREEMENT FOR METAL SHADER CONVERTER », EA1844, 5/31/2023, extracted from
    `LICENSE.metal-shaderconverter.rtf` (77,453 bytes, SHA-256
    `20108dfe30663a2c6c717d9c5ca92486d9a4682c85c8ab344b20470feac8d0c3`);
  - Apple's Acknowledgements (`ACKNOWLEDGEMENTS.metal-shaderconverter.rtf`, 11,348 bytes, SHA-256
    `01ed5de80de6e1ca7c074ef602d867ef0bdbf0be3abc97adb7199c1ad380c3ba`; byte-identical to
    `xenios-jp/metal-shader-converter@ios-4.0.3:include/Acknowledgements.rtf` according to the dossier);
  - the Apache-2.0 licence of the headers (Copyright © 2023-2025 Apple Inc.).
- Copy source: release `deps-metal-shaderconverter-4.0b3` of `metalsharp/VKD3D-Proton-MacOS` (Metal Shader Converter
  4.0 beta 3, published 27 Oct 2026).
- No installer was run and no agreement was accepted on the maintainer's behalf.
- The original RTFs are the reference documents. The text file is a Pandoc extraction.

## Reading of the agreement (main, 12 Nov 2026)

| Clause | What it says | Consequence for RewindBox |
|---|---|---|
| 2.A | Apple Software other than the dylibs: internal use and testing only | headers and docs: not redistributed beyond what Apache-2.0 allows |
| 2.B | dylibs: install, use, test and **distribute for the sole purpose of shader conversion** | XeniaCore may use `libmetalirconverter.dylib` only to convert Xbox 360 shaders; no other use |
| 2.C / 2.D | Apple-branded hardware only; no rent, lease, lending, hosting, sale or sublicensing; keep every copyright and proprietary notice on each copy | iOS only; free private builds; ship Apple's notices with the dylib; no service-bureau use |
| 2.E | no copying beyond the agreement, decompiling, reverse engineering, **modification** or derivative works | ship the dylib's bytes unchanged: no `install_name_tool`, `strip`, `lipo` or patching (to verify by digest against the pinned asset). iOS re-signing replaces the code signature: an open point, see below |
| 1.B | updates are governed by this agreement **unless an update comes with its own licence** | the applicability to the pinned `ios-4.0.3` runtime is not proven: open point |
| 13 | third-party notices are in the Acknowledgements file | ship the Acknowledgements (zlib/libpng, MIT, BSD-2-Clause, LLVM/NCSA: binary redistribution must reproduce their notices) |
| 4, 6–12 | analytics, indemnification, warranty, liability, export, governing law | no further action for a free private build |

## Still missing before redistribution is declared resolved

1. **Applicability to the pinned runtime** (clause 1.B).
   - The copy is published with 4.0 beta 3. The pinned runtime is the `ios-4.0.3` asset of a third-party mirror
     (`bd6b729d…`, 30,189,152 bytes; headers at 4.0.1).
   - What would close it: the licence shipped with the Apple 4.0.x package the iOS runtime comes from, or Apple's
     product page or package showing that EA1844 covers it.
2. **Provenance of the binary.**
   - `xenios-jp/metal-shader-converter` is not Apple, and Apple publishes no checksum.
   - The pin checks the mirror's digest and Apple's code signature (`codesign`).
   - Nothing yet ties these bytes to an Apple-distributed iOS runtime.
3. **Re-signing for the IPA (clause 2.E).**
   - Embedding the dylib requires replacing its signature with RewindBox's. Whether that counts as a modification is
     a reading to record, as XeniOS itself does.
   - Every other byte must stay identical. The delivery must check that, from the asset digest excluding
     `LC_CODE_SIGNATURE`.

## Maintainer decision (11 Nov 2026)

The maintainer allows `libmetalirconverter.dylib` in the IPA and asks for the XeniOS engine in the next common IPA.
The three open points above are recorded as accepted by the maintainer for the next private common IPA, not as resolved.
The technical controls stay:
- the dylib's bytes are unchanged except `LC_CODE_SIGNATURE` (digest checked at delivery);
- the RTFs are pinned by digest in the legal chain;
- the dylib is used only for shader conversion by XeniaCore.

## Complement of 12 Nov 2026 (`Complement_Mentions_XeniOS_2026-11-12.txt`, 19,391 B, SHA-256 `f2cfd2ae…43cd`)

Research requested by the maintainer; read in full by main. No licence was accepted.

Gaps it shows, with sources and texts in the file:
1. **Missing DXBC notices.** The « DXBC checksum (AMD) » entry of XeniOS's `Acknowledgements.json` (cf7c7ee45) has an
   empty text, yet the linked `third_party/dxbc/DXBCChecksum.cpp` carries the RSA Data Security MD5 notice (lines
   50–72). Its primary source, GPUOpen-Archive/common-src-ShaderUtils@545195d7, has an AMD MIT `LICENSE` (1,116 B, SHA-256
   `f7367ebb…ef86`). Both texts must ship, as a pinned complement next to the unchanged upstream JSON.
2. **The signer check is too weak.** `build_core.sh` checks `grep -q "Authority=Apple"`, which a third-party chain
   ending at Apple Root CA also passes. Use a signing requirement (`codesign --verify --strict -R '=anchor apple'`),
   record the identity actually observed, and never relax the check if it fails.
3. **The source-evidence review is out of date.** It still covers the playlist without an engine
   (`engine_binaries_bundled=[]`). The delivery that ships XeniaCore needs its own review: real binaries, plus the
   sources, configuration and relinking means of the statically linked FFmpeg and libmspack (LGPL-2.1 §6). Their
   licence texts are already there.
4. **Boost.Context provenance.** The BSL-1.0 text exists; only the provenance reference needs to be more precise.

Still without proof (not resolved by this research):
- which Apple package and contract govern the `ios-4.0.3` hash;
- a direct link between the mirror's bytes and an Apple package;
- re-signing under clause 2.E.
The maintainer's delivery decision is not an authorisation from the rights holder.

## Direct check of 12 Nov 2026 (`Verification_Directe_XeniOS_2026-11-12.txt`, 15,618 B, SHA-256 `fdf4bc5c…322c`)

Check requested by the maintainer and run by Codex on the real mirror file. No binary was modified and no agreement was
accepted. Main archived the report; it did not re-run these commands.

Measured on the downloaded `ios-4.0.3` asset:
- the SHA-256 is exactly `bd6b729d…37aa` (30,189,152 B), and the file is an arm64 iPhoneOS library (min iOS 13.0, SDK 26.4);
- all 7,309 of 7,309 CodeDirectory page hashes match, and the CodeDirectory identifier is `libmetalirconverter`;
- `build-utils/xenia/validate_shader_converter.py` at `028a0fdf2` exits 0 on this file (`--require-pinned-digest`), and
  the signature-free digest matches the pin (`b5263652…fa1e`);
- the CMS signature verifies mathematically, and its chain (Software Signing → Apple Code Signing Certification
  Authority → Apple Root CA) leads to the root downloaded separately from Apple's official PKI site (same SHA-256).

**New limit:** the Software Signing leaf and the intermediate both expire on 2026-10-24 17:39:41 UTC, and the CMS
carries no signing time or timestamp. OpenSSL with its time check fails (certificate has expired); without the time
check it passes. That second run is a diagnostic only, not a delivery check:
- no time-check bypass goes into the delivery;
- the strict `codesign` check stays as it is;
- its real macOS result must be recorded;
- the report does not conclude that `codesign` will fail, since Apple's policy was not run on Linux.

Also confirmed in the `028a0fdf2` source: the AMD MIT and RSA/MD5 notices, and the `=anchor apple` requirement plus the
identifier/CN check in `build_core.sh`. The report does not re-run the Dart tests. The LGPL source-evidence review for
the shipped binaries is still incomplete at that commit: the XeniOS block of `collect_build_source_evidence.py` still
declares `engine_binaries_bundled=[]`. CI run `43121527685` was still in progress when inspected.

Still open: points 1–3. A signature check gives neither the Apple package nor its contract, and does not settle
clause 2.E. The Apple download needs a login; Codex will ask the maintainer for that access to compare the package itself.

## Apple package check of 12 Nov 2026 (`Verification_Paquet_Apple_XeniOS_2026-11-12.txt`, 25,203 B, SHA-256 `cd5e43d0…b121`)

Run by Codex after the maintainer gave Apple Developer access. The package was extracted without installing it. No
script or binary was run or re-signed, no third party was contacted and no agreement was accepted. Main archived the
report; it did not re-run these commands.

**Official package:** `Metal Shader Converter 4.0 beta 3.pkg` (catalog entry 20 Oct 2026; link under
`Developer_Tools/Metal_Shader_Converter_3.1_beta_1/`, now seen in Apple's own catalog).
- 48,239,331 B, SHA-256 `449833211e4ef0d46bfaa94848e801acff49e226d3c348bba0673f13716be622`;
- `com.apple.metal` 1.0.1.1792438795, 30 payload files;
- XAR signature valid; chain Software Update → Apple Software Update CA → Apple Root CA (root fetched separately)
  verifies with OpenSSL's normal time check. This is not a macOS pkgutil/codesign result, and revocation (OCSP/CRL)
  was not checked. This signer is not the dylib's (Software Signing), so it says nothing about that leaf's expiry.

**Contract:** `Resources/English.lproj/License.rtf` from this signed package is 77,453 B, SHA-256 `20108dfe…d0c3`,
byte-identical to the EA1844 copy already on file. Its Apple origin and its presence in a package that ships an iOS
library are now established. No amendment and no explicit wording on re-signing was found in License.rtf,
Read Me.rtf, Welcome.html or Distribution.

**The package's iOS dylib is NOT the pinned mirror file:**

| | Apple package | Mirror `ios-4.0.3` (pinned) |
|---|---|---|
| SHA-256 | `3040a91e…5518` | `bd6b729d…37aa` |
| Size | 30,189,152 B | 30,189,152 B |
| LC_SOURCE_VERSION | 33.40 | 33.39 |
| LC_UUID | `d1744d8b…e81d` | `c9d2d4d5…b8f9` |
| Signature-free digest (project validator) | `e456a88e…40ac` | `b5263652…fa1e` |

- 430 bytes differ: 52 in LC_UUID, LC_SOURCE_VERSION and LC_RPATH (an internal build path), and 378 inside the
  signature.
- Every byte from offset 3128 up to 29,936,976 (code and data, up to the signature) is identical.
- `ir_version.h` says 4.0.3. That is the API version, not the build, so it does not identify the pinned build.

Status after this check:
1. **Package and contract of the pinned binary: partly answered.** We hold an authenticated official 4.0 beta 3
   package and its original contract, but it is not the exact installer of `bd6b…37aa`.
2. **Direct link between the mirror's bytes and an Apple package: open.** The code and data match, but the build
   identity does not. That is evidence that the two are related, not proof of where the mirror came from.
3. **Re-signing under clause 2.E: open.** The original contract adds no explicit clause on it.

Unchanged: the pin, the binary and every check. Do not swap the library or the pin to get a match, and do not weaken
the validator. The strict macOS codesign result and the LGPL source review of the actual delivery are still due. The
maintainer's delivery decision stands. It does not settle these points legally.
