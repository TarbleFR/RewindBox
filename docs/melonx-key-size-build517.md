# Mixed-length personal key import — Build 517 delivered

The maintainer still sees `keySize` on import and `keysMissing` on launch in Build 516. The screenshots establish that import never installed a usable prod.keys; they do not establish which local copy the iOS picker returned. No personal key value or title rights identifier is committed, logged, or sent to CI.

## Reproduction

The exact delivered LibHac package is `Ryujinx.LibHac.0.21.0-alpha.129`, SHA-256 `b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9`. Probe source `7257cfb35b9db2991ec02509e39ee5ae0642d8f3`, run `40025328376`, executes the Build 516 validator with synthetic values of the reported names and lengths on .NET 10 / macOS ARM64. The original shape is refused with `keySize`; the proposed filtered shape is accepted with 190 recognized and eight unknown entries. The original has 33 mismatches: 34 hexadecimal characters rather than 32, beginning at line 96. This proves schema behavior, not personal decryption or the selected iPhone file.

The exact file_picker 12.0.0-beta.3 archive matches the lockfile SHA-256 `51093fc49e4d58935998fb112593c23eda571d14b488388bd41d5d2ba332b26a`. Its `copyToTemporaryDirectory` removes an existing destination before copying and returns nil on failure. A stale plugin cache is not established and is not treated as the cause.

## Correction

LibHac `ReadMainKeys` ignores a recognized entry of incorrect length without writing the destination key. RewindBox's added validator instead rejected the entire mixed export. The validator now matches this reader behavior for prod/dev/console files, counts wrong-sized entries separately, and still requires at least one recognized correctly sized entry. Title key validation, malformed hex/syntax, file/line limits and conflicting duplicate refusal remain strict. No value is truncated, padded, inferred or replaced; the selected source is unchanged.

The preview API reports `invalidSizeKeys`. The import summary shows a translated warning in all twelve languages while importing valid entries through the existing rollback transaction. Internal logs contain only the canonical type, source byte count, and recognized/unknown/wrong-size counts, never values or arbitrary native diagnostics. The original and filtered copy can thus both be imported when they contain usable entries, without manually editing keys.

## Verified private delivery

Private IPA **0.0.8 (517)**, source `05f04b9bbc9cb95137c8bc5df42a53606b358201`, successful delivery [run 40025909494](https://github.com/TarbleFR/RewindBox/actions/runs/40025909494). File `RewindBox-Build517.ipa`, **186,164,583 bytes**; SHA-256 `7ab16fade93bbb81aa24a077835b02644beacb97a2e15e960ed1a1f76b7a8fb9`.

- Engine `e0a1196d70469a28f04cc8a3628f43d484015581`, successful run `40025760206`; original iPhone Core SHA-256 `589b3cdbf62833d8e2e325ba5253540ce4aeceba71b2f8543f7daff3aa8f8d27`. All 28 source inputs verified independently; only EmbeddedKeyValidation and EmbeddedContent differ from delivered 516.
- **48 native key/real-LibHac/preview assertions**, **14 configuration/API cases** and **13 preflight/journal assertions** passed. The full reported file shape uses synthetic values; it reproduces old Build 516 refusal, imports 190 valid entries and reports 33 wrong-sized and eight unknown entries under the new validator. The real reader leaves malformed destinations untouched and loads the valid header key. All-invalid, syntax, conflict and title-key rejection controls remain enforced.
- **16 targeted Dart tests** and analysis passed (run `40025760340`), including mixed-size warning propagation, original-value preservation, aliases, encodings, twelve languages and transaction rollback.
- The rebuilt **actual ARM64 iOS NativeAOT runtime** accepted and reloaded a supported entry beside an unknown entry and a wrong-sized seed. It reported `invalidSizeKeys`, rejected an all-invalid candidate without changing installed content, and completed two original non-graphical homebrew sessions. No personal values were sent to CI. This is simulator evidence, not physical iPhone or commercial-game proof.
- Independently downloaded Core and delivery archives matched their recorded digests. Two full-archive connector transfers timed out; transfer-only source `5d569ea3335bdd0c20750cbe2781a0dfd8d44894`, run `40029737541`, split the same encrypted delivery into four bounded pieces. Each piece and the reconstructed original archive were independently hash-verified before decryption; the IPA was never rebuilt or changed by this transport step. The final IPA has 7 aligned app/extension bundles, 86 ARM64 images, 116 CodeDirectories and 132,668 verified code-page hashes. The packaged MeloNX code/data/ABI matches the built artifact, allowing only its declared framework install-name rewrite and signing. No personal key, firmware or game is bundled.
- RPCS3 source `a69860297d7b26dbb688df0daf16a31b42046462`, its restore/freeze fixes and cache identities are preserved; all other prebuilt engine/dependency payloads match the delivered 516 app. No release, tag or main change.

Install through SideStore/AltStore and import the original personal `prod.keys` file. A mixed export reports imported keys and a warning for ignored wrong-sized entries. The eight unsupported entries remain a separate notice. Values are never shortened or fabricated. The exact selected iPhone file and commercial-game decryption remain unverified; successful import does not by itself establish firmware/game compatibility. **517 is frozen: a later IPA needs a new number.**

Machine-readable receipt: `docs/evidence/melonx-keys517-delivery.json`.
