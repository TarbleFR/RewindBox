# Targeted research on the three open points: Apple Metal Shader Converter iOS runtime (12 Nov 2026)

Research requested by the maintainer and relayed to main.
- No third party was contacted, no Apple agreement was accepted, and no binary was replaced.
- Main could not re-check the GitHub API facts below from its session: the network proxy refuses `xenios-jp/*` (HTTP 403).
- Status: **none of the three points is closed.** The new facts improve traceability only. They are neither an Apple
  authorisation nor a certain identification of the package.

## 1. Declared origin of the exact binary (open point 2: provenance)

Release `ios-4.0.3` of `xenios-jp/metal-shader-converter`, primary API:
https://api.github.com/repos/xenios-jp/metal-shader-converter/releases/tags/ios-4.0.3

| Field | Value |
|---|---|
| Asset | id 705945125 |
| Uploaded | 2026-11-03 14:44:05Z |
| Size | 30,189,152 B |
| SHA-256 | `bd6b729dcbde133a511d95130eb4d287a1e18b4170453f8b350e78a20bfc37aa` (the pinned bytes) |
| Uploader's description | iPhoneOS arm64 library 4.0.3, taken from Apple's Metal Developer Tools |
| Tag commit | `eb320d8a6d65fc15ef2c226da7a405f39cb0d697`, December 2025 |

What the release does not give:
- the exact installer name, Apple source URL, package digest or build number;
- a licence for the runtime library. The Apache-2.0 notice of the release refers to the headers' `LICENSE.txt` and
  says nothing about the rights to the proprietary runtime. This contradiction is kept on record.

The tag's tree dates from December 2025, so it cannot be an inventory of the 4.0.3 package of November.

## 2. Leads examined, and the false matches to avoid

| Lead | What it holds | Matches `bd6b729d…`? |
|---|---|---|
| Branch `ios-support-4.0`, commit [`7dbc33bd`](https://github.com/xenios-jp/metal-shader-converter/commit/7dbc33bd3d52f64f774a19fff0326774ed582afe), 12 Jun 2026 | iOS library 4.0.0, 30,147,296 B | no |
| XeniOS workflow, commit [`3f983eb1`](https://github.com/xenios-jp/XeniOS/commit/3f983eb19a3b044f91a294b2c691f00e796220b8) | downloads the mirror's dylib and checks its hash and signature; no Apple extraction | n/a |
| [Madeira `fetch-converter.sh`](https://github.com/willfaust/Madeira/blob/401a92719c4b9165df432144b12fbd60aa6d17b5/build/madeira-d3d12/fetch-converter.sh) | `Metal Shader Converter 4.0 beta 2.pkg` (`1acc33c8…5734`) → iOS dylib `073f903b…68c2` | no |
| [Iridium `deps-metal-shader-converter-4.0-beta2`](https://github.com/intraducine/iridium/releases/tag/deps-metal-shader-converter-4.0-beta2) | the same `073f903b…` dylib, with a different installer digest | no |

The Acknowledgements are shared across versions, so their byte equality does not prove the origin either.

## 3. Apple: established and not established

Established (official sources):
- The `libmetalirconverter` library supports Windows, macOS and iOS; the executable's platform list differs
  ([Game Porting Toolkit docs](https://github.com/apple/game-porting-toolkit/blob/main/docs/metal-shader-converter/compiling-shaders.md)).
- iOS support arrived with version 3.1 ([product page](https://developer.apple.com/metal/shader-converter/)).
- This refutes a "macOS-only library" argument.

Not established:
- No explicit Metal Shader Converter exception to clause 2.E, and no Apple answer about re-signing, was found in Apple
  sources or forums.
- That absence is neither a demonstrated prohibition nor a permission.
- The signature-free digest proves a technical property, not a contractual permission.

## 4. What would close points 1 and 2

- The official download, behind an Apple Developer login:
  https://developer.apple.com/download/all/?q=metal+shader+converter. Checked: login required, no account signed in,
  no agreement accepted.
- A third-party tracking page ([johnhaney.com/apple-betas](https://johnhaney.com/apple-betas/)) lists 4.0 beta 3 on
  20 Oct 2026, with a candidate link that redirects to an access-denied page:
  `https://download.developer.apple.com/Developer_Tools/Metal_Shader_Converter_3.1_beta_1/Metal_Shader_Converter_4.0_beta_3.pkg`.
  The `3.1_beta_1` folder is as published. The link is not proof that this package contains `ios-4.0.3`.

Procedure, in an environment authorised to download it:
1. Record the original Apple installer: provenance, Apple signature, SHA-256 and metadata.
2. Extract it without installing. Take the iOS payload and `Resources/English.lproj/License.rtf`.
3. Compare the raw digest of the extracted dylib with `bd6b729d…37aa`, and keep the exact contract with its digests.
   - **Same digest:** it confirms the package–bytes link (points 1 and 2).
   - **Different digest:** the points stay open. **Do not switch libraries just to make the check pass.**

Point 3 (re-signing, clause 2.E) needs the applicable text that actually addresses the case, or a written
clarification from Apple. Technical signing guides are not that proof.

## Status after this research

| Point | Status |
|---|---|
| 1. Contract applicable to the `ios-4.0.3` runtime | open: no package or contract tied to the hash |
| 2. Provenance of the mirror's bytes | open: uploader's statement only; Apple installer and digest unknown |
| 3. Re-signing under clause 2.E | open: no explicit text or Apple statement found |

The maintainer's delivery decision is unchanged. It does not settle these points legally.
