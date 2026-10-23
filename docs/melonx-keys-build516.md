# Personal key import — Build 516 delivered

The maintainer reports that personal prod.keys is still rejected and requests a corrected private test IPA. Work starts from Claude c34dc844ce28c5e46b972215122f01415fd88239, the evidence receipt for delivered 515. No release/tag/main change is authorized. The prior RPCS3 restore/freeze Core, Switch launching, playlist and other engines are preserved.

## Findings and correction

The exact source-built LibHac package used by the delivered engine (0.21.0-alpha.129, SHA-256 b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9) uses ExternalKeyReader.ReadMainKeys, which skips unknown entries. RewindBox's added EmbeddedKeyValidation instead rejects the entire file whenever any entry is absent from that schema. An export containing supported keys plus newer or unused entries is therefore refused before the engine can read the supported entries. The regression fixture reproduces this difference with synthetic bytes, not the maintainer's personal keys.

The validator now preserves unmatched entries, requires at least one supported key, checks recognized lengths and rejects malformed input or conflicting duplicate values. Identical duplicate values are accepted. The real LibHac reader must load the recognized fixture into its actual KeySet in the regression test; syntax acceptance alone is insufficient.

Candidate validation no longer reloads the old installed key set. The live reload occurs only after the file transaction, without coupling key import to an unrelated firmware-directory scan. Firmware discovery remains in its explicit operation and launch preflight. The existing transaction and recovery copies are preserved.

The file picker permits selection without relying on an iOS UTI for .keys. Known prod/title .keys.txt and numbered copy aliases are normalized to the canonical system filename. UTF-8/BOM, UTF-16 BOM, CRLF, comments and LibHac's comma separator are normalized in a private copy; original files are not changed. Arbitrary filenames, invalid syntax, unsupported-only dumps and conflicting files remain rejected.

Refusal reasons now distinguish text, key length, conflicting entries, no supported keys, unreadable source and engine failure in all twelve existing languages. Extra entries are reported as retained but unused, not advertised as new firmware support. Logs contain fixed error codes only; no personal key values, firmware or games are requested or bundled.

## Verified delivery

Private IPA **0.0.8 (516)**, source `5d805f48eba97307dad94c66c51fb534355a70f8`, workflow run [40019951810](https://github.com/TarbleFR/RewindBox/actions/runs/40019951810) — successful checks, native source closure and Release device build.

- File: `RewindBox-Build516.ipa`, **186,166,377 bytes**.
- IPA SHA-256: `6e3cd68315f269c43717e18728e42de6ba4464577771dabe378aa84b55918a00`.
- New MeloNX engine source `5a917d154a886481fb00d424b9cfc8fe149ece37`, successful run `40017275406`; original iPhone dylib SHA-256 `f45534df91a35692b1f55e5049885ef2106117d3cb2503a0c7166f523d50baf3`. All 28 adaptation inputs independently verified; only EmbeddedContent and EmbeddedKeyValidation differ from the delivered engine.
- Dart lane `40017275462`: analysis and **15 targeted tests** passed, including the actual import transaction, UTF-16, provider aliases, duplicate types, refusal codes, rollback and twelve languages.
- Native lane: **39 key/real-reader/preview assertions**, **14 personal configuration/API cases** and **13 launch-preflight assertions** passed. The old validator's rejection is reproduced before the corrected reader succeeds.
- Actual ARM64 iOS simulator runtime: new import export, supported + ignored entries, reload and key-size refusal passed. Two original non-graphical homebrew sessions also completed. These are simulator checks, not physical iPhone or commercial-game proof.
- Independently downloaded Core and IPA archives matched their GitHub digests. The final IPA has **7 version-aligned app/extension bundles**, **86 ARM64 images**, **116 CodeDirectories** and **132,664 verified code-page hashes**, with no encrypted executables. The packaged MeloNX code/data/ABI matches the compiled artifact, allowing only the declared framework install-name rewrite and signing.
- RPCS3 source `a69860297d7b26dbb688df0daf16a31b42046462`, its restore/freeze fixes and cache identities are preserved. Existing prebuilt engine/dependency payloads match the delivered 515 app. No release, tag or main change.

A pre-delivery marker assertion in run `40017610140` failed after compilation/signing because it assumed fully padded UTF-16 in NativeAOT's serialized string table. The verifier was corrected against the actual compiled image, with four positive/new and negative/old marker checks. The final assembly reuses the same successful engine and Dart tests; no runtime change was made for that verifier correction. The original failed run remains recorded. The historical Navigation 512 scope-only failure is also retained separately in the evidence.

Install through SideStore/AltStore, then import the same personal prod.keys through the Switch playlist. The maintainer's exact export was not supplied or examined, and physical iPhone import remains to be confirmed. Accepting the file validates its supported entries and format; it does not establish decryption compatibility for every game or firmware. No personal key, firmware or game is bundled. **516 is frozen; use a new number for a later delivery.**

Machine-readable receipt: `docs/evidence/melonx-keys516-delivery.json`.
