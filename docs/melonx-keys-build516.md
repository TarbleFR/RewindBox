# Personal key import — candidate 516

The maintainer reports that personal prod.keys is still rejected and requests a corrected private test IPA. Work starts from Claude c34dc844ce28c5e46b972215122f01415fd88239, the evidence receipt for delivered 515. No release/tag/main change is authorized. The prior RPCS3 restore/freeze Core, Switch launching, playlist and other engines are preserved.

## Findings and correction

The exact source-built LibHac package used by the delivered engine (0.21.0-alpha.129, SHA-256 b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9) uses ExternalKeyReader.ReadMainKeys, which skips unknown entries. RewindBox's added EmbeddedKeyValidation instead rejects the entire file whenever any entry is absent from that schema. An export containing supported keys plus newer or unused entries is therefore refused before the engine can read the supported entries. The regression fixture reproduces this difference with synthetic bytes, not the maintainer's personal keys.

The validator now preserves unmatched entries, requires at least one supported key, checks recognized lengths and rejects malformed input or conflicting duplicate values. Identical duplicate values are accepted. The real LibHac reader must load the recognized fixture into its actual KeySet in the regression test; syntax acceptance alone is insufficient.

Candidate validation no longer reloads the old installed key set. The live reload occurs only after the file transaction, without coupling key import to an unrelated firmware-directory scan. Firmware discovery remains in its explicit operation and launch preflight. The existing transaction and recovery copies are preserved.

The file picker permits selection without relying on an iOS UTI for .keys. Known prod/title .keys.txt and numbered copy aliases are normalized to the canonical system filename. UTF-8/BOM, UTF-16 BOM, CRLF, comments and LibHac's comma separator are normalized in a private copy; original files are not changed. Arbitrary filenames, invalid syntax, unsupported-only dumps and conflicting files remain rejected.

Refusal reasons now distinguish text, key length, conflicting entries, no supported keys, unreadable source and engine failure in all twelve existing languages. Extra entries are reported as retained but unused, not advertised as new firmware support. Logs contain fixed error codes only; no personal key values, firmware or games are requested or bundled.

## Verification plan and limits

- Reproduce the delivered validator failure and prove the corrected validator and real pinned reader accept supported + unknown synthetic entries.
- Exercise actual Dart file import, canonical destinations, encodings, aliases, duplicates, native errors and rollback.
- Compile the modified NativeAOT engine for iPhone and ARM64 simulator; exercise the actual key import export, reload and failure codes in the simulator app.
- Reuse unchanged Darwin, homebrew parser, storage/session, dependency and other-engine evidence only after exact input checks. Rebuild the final app with the new Dart and engine inputs.
- Independently verify the final IPA identity, contents, signatures and source closure before delivery.

At this source stage, no IPA is claimed. The user's exact export is unavailable; the reproducible rejection paths above are established from source and synthetic fixtures, not yet confirmed on their iPhone. Accepting an export does not prove that its keys can decrypt every game or firmware.
