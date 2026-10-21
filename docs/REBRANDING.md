# RewindBox — project identity and compatibility

Effective 21 October 2026, the independently maintained iOS/iPadOS fork is named **RewindBox**. Its repository is https://github.com/TarbleFR/RewindBox. Support for this fork belongs in its own issue tracker, not the upstream project's support server. The upstream [NeoStation project](https://github.com/misobadev/neostation-frontend), Miguel Soto / misobadev and all contributors remain credited. This rename does not imply endorsement or change licenses.

## Current source

The app title, onboarding/help translations, in-game return labels, JIT permission descriptions, iOS display name, website-installer defaults and public repository presentation use RewindBox. The update endpoint points to this fork. Both main and Claude receive branding-only changes on their own existing source snapshots; unreleased development work is not merged into main. No new version, tag, release, IPA, game-engine feature or on-device validation is implied.

## Deliberately retained legacy identities

The bundle identifier, Dart package name/imports, URL schemes, method channels, preferences, keychain/access-group identifiers, databases, internal storage roots, native ABI names and staging filenames remain stable. Changing them without a migration could lose access to existing data or break JIT/native integration. NeoSwap and NeoPlay remain feature names. Original third-party license files and upstream asset names are not relabeled as RewindBox-owned work. Historical source archives, signed binaries, evidence receipts, immutable tags and old screenshots are not rewritten. The exact permitted display-only changes in locked baseline files are reversed before their original hash checks.

## Existing releases 0.0.1–0.0.8

Release presentation and downloadable filenames are renamed; original binary/source/license bytes and their SHA-256 digests are preserved. Consequently those installed binaries still show their original name and Files folder. Only a newly compiled version will display RewindBox on the device. Original checksum records remain available with an Original-SHA256SUMS suffix; new checksum lists refer to the renamed downloads. Old manifests describe the original filenames and remain historical evidence, not newly rebuilt sources. See release notes for the filename map.

## Scope

The GitHub repository and source are updated. This task does not redeploy the external Vercel installer or alter its environment overrides, rename external community accounts, or redesign the app icon. The startup/onboarding/default-display wordmark is now rendered as RewindBox text; original upstream artwork remains in its credited assets. Those surfaces must not be represented as already deployed or visually redesigned.
