# Switch library corrections and personal MeloNX migration

Scope: `Claude`, requested 23 October 2026. No release, tag, main change or IPA delivery is part of this task. This change requires a newly compiled MeloNX engine with **library ABI 2**; the frozen 506/507 engine must not be substituted for it. Runtime/session/input ABI 1 remains unchanged.

## Storage and ownership

The existing engine root remains `Documents/MeloNX`. Imported games use `roms/switch`; discovery also accepts games directly in `roms`, the root, `games`, existing registered Switch folders, and explicitly bookmarked game folders. Discovery reads actual native game metadata and rejects update-only/DLC NSPs. It never copies games. Unchanged files reuse cached metadata/fingerprints; matching hashes relocate existing rows while preserving their filename identity, scraped metadata, favourites and play time. A legacy row without a fingerprint may move only when its native base title ID is unique and the old location is demonstrably missing. Ambiguous/inaccessible old entries are retained.

Game deletion uses the existing repository, native file access and confirmation. Long press and the Import menu provide multi-selection. Only game images and the existing repository's scraped media are affected. Keys, firmware, save data and profiles are preserved. A shared native/Dart mutation lease prevents deletion, imports and migration during an active or pending Switch launch. Failures retain the unsuccessful row; successful deletions update counts and selection.

The Switch Import button shares the media-pill import component with Libretro. The game and system Emulator tabs use the existing localized embedded-engine identity tile for MeloNX.

## Imports and transfer

* Both key types can be selected together, in either order. Validation precedes replacement; duplicate types and invalid files are reported individually. Single-file updates preserve the other key. Production keys are required for encrypted games; title keys are optional. No key material is logged.
* Firmware ZIP detection and installation use the same NCA filename normalizer, accepting arbitrary parent folders/case and ignoring Finder metadata. Verification uses bounded disk streams and streaming content hashes. Extracted firmware is validated before the journaled directory swap. The engine must recognize the installed version before commit. Progress and cancellation come from actual engine phases.
* Save exports are associated with their title/profile when identifiable, otherwise the user selects them. **LibHac itself** resolves/creates the save ID under `bis/user/save`. Both committed `0` and working `1` trees are replaced together while retaining the native association metadata. Existing saves have recovery copies. The engine resolves the mapping again before the transaction commits.
* The migration assistant accepts a folder or a personal ZIP export, recognizes an additional parent folder, lists destinations/conflicts/space and unsupported settings, then asks for confirmation. It copies compatible recognized data into the existing engine tree, adapts update/DLC paths, and preserves source data. The optional linked-games mode keeps base games in the bookmarked source folder and copies the engine data. Games already present at the destination are compared before copying. Complete NAND/profile replacement requires reopening RewindBox so the engine reloads its indexes.
* ZIP inflation is incremental, validates names, duplicate/case-colliding members, encryption, actual output size and CRC, and refuses symlinks/traversal. File transfers use bounded copying plus content verification. Directory swaps have a durable journal and recovery copies; interrupted staging is cleaned on the next library visit.

The standalone source's real `config.json` and `config/<title>_config.json` files are used. Supported graphics, audio, language/region and other compatible options are applied. Unsupported host/JIT/window/network options are listed rather than enabled. Preferences that the standalone app keeps only in its inaccessible iOS UserDefaults are not present in a Files export and cannot be recovered from that folder. The assistant does not claim to migrate data it cannot read.

## Launch entitlements

The installed process's signed entitlements are read before initialization/JIT and rechecked at the native launch boundary. Increased Memory Limit (`com.apple.developer.kernel.increased-memory-limit`, usually “Get More RAM”) is required. Extended Virtual Addressing is required only when the upstream device address-space test requires it. The capacity test reserves no physical memory and releases its mapping; its result is retained to avoid re-testing against an already prepared JIT arena. Entitlements themselves are read from the running signature, never from a preference or an IPA template. Unknown verification states block launch.

The translated blocking message explains that the user must use a compatible signing tool/provisioning profile, enable the supported rights, re-sign and reinstall RewindBox. An in-app switch cannot grant signed entitlements. RewindBox's general library remains accessible.

## Validation and limits

Added executable coverage includes filesystem replacement/cancellation/interruption/recovery, key import and rollback, native save mapping and both data trees, folder/ZIP discovery, relocated-game deduplication and metadata preservation, conditional entitlement checks, theme-aware import controls, and complete twelve-language catalogs (including Traditional Chinese). Native tests exercise the production firmware archive normalizer and rollback integration, compile the save calls against the exact previously validated LibHac package, and exercise the production personal-options reader.

The targeted CI lanes compile the full changed MeloNX engine and Swift/Objective-C++ host and initialize that exact rebuilt NativeAOT engine in an ARM64 iOS simulator. Unchanged Libretro engines/skins/shaders and unchanged firmware-store/header tests reuse their verified inputs; unrelated emulator cores are not rebuilt. Results and exact source/run identities are recorded after CI completion.

No proprietary keys, firmware, commercial games or personal save export were supplied for these checks. Physical Switch gameplay, firmware decryption with a user's keys and successful in-game save loading remain device validation; unit tests or simulator bootstrap do not establish those outcomes. Whole-installation migration is a confirmed replacement with recovery copies, not an unsupported merge of two unrelated NAND indexes.
