# Mixed-length personal key import — candidate 517

The maintainer still sees `keySize` on import and `keysMissing` on launch in Build 516. The screenshots establish that import never installed a usable prod.keys; they do not establish which local copy the iOS picker returned. No personal key value or title rights identifier is committed, logged, or sent to CI.

## Reproduction

The exact delivered LibHac package is `Ryujinx.LibHac.0.21.0-alpha.129`, SHA-256 `b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9`. Probe source `7257cfb35b9db2991ec02509e39ee5ae0642d8f3`, run `40025328376`, executes the Build 516 validator with synthetic values of the reported names and lengths on .NET 10 / macOS ARM64. The original shape is refused with `keySize`; the proposed filtered shape is accepted with 190 recognized and eight unknown entries. The original has 33 mismatches: 34 hexadecimal characters rather than 32, beginning at line 96. This proves schema behavior, not personal decryption or the selected iPhone file.

The exact file_picker 12.0.0-beta.3 archive matches the lockfile SHA-256 `51093fc49e4d58935998fb112593c23eda571d14b488388bd41d5d2ba332b26a`. Its `copyToTemporaryDirectory` removes an existing destination before copying and returns nil on failure. A stale plugin cache is not established and is not treated as the cause.

## Correction

LibHac `ReadMainKeys` ignores a recognized entry of incorrect length without writing the destination key. RewindBox's added validator instead rejected the entire mixed export. The validator now matches this reader behavior for prod/dev/console files, counts wrong-sized entries separately, and still requires at least one recognized correctly sized entry. Title key validation, malformed hex/syntax, file/line limits and conflicting duplicate refusal remain strict. No value is truncated, padded, inferred or replaced; the selected source is unchanged.

The preview API reports `invalidSizeKeys`. The import summary shows a translated warning in all twelve languages while importing valid entries through the existing rollback transaction. Internal logs contain only the canonical type, source byte count, and recognized/unknown/wrong-size counts, never values or arbitrary native diagnostics. The original and filtered copy can thus both be imported when they contain usable entries, without manually editing keys.

## Validation and delivery status

Pending: the extended real-LibHac regression including the entire non-secret original shape and the old Build 516 negative control, the affected configuration/preflight cases, targeted Dart import/rollback tests, and the rebuilt actual ARM64 iOS NativeAOT runtime. The runtime smoke must preview and reload a supported key beside an unknown entry and a wrong-sized seed, report its warning, and still reject an all-invalid candidate without modifying the installed file.

Build 516 is frozen. Build 517 will be a new private test IPA on Claude, preserving the delivered RPCS3 Core and all unrelated product inputs. No release, tag or main change. No physical iPhone success, commercial-game decryption or performance is claimed from these checks.
