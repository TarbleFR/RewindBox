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
