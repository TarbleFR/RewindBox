# NeoStation iOS 0.0.8 — source and packaging

The public package preserves the compiled application and emulator code from
the maintainer-tested private Build 480. Only the marketing version in the
application and its five extensions, an additional release identity record,
and ad hoc signatures change. The compiled build number remains 480.

- Compiled host source: [`7493d9babe20be1b2939e21a1051a72da8fb5d01`](https://github.com/TarbleFR/neostation-ios/tree/7493d9babe20be1b2939e21a1051a72da8fb5d01).
- Original build: [39132356516](https://github.com/TarbleFR/neostation-ios/actions/runs/39132356516).
- Original IPA: 226,569,533 bytes, SHA-256 `a87c355491083f8e4c385f5c119f9a8e41ecd1738439747cd20dd38bdb2ba8f1`.
- Release packaging source: the `0.0.8` tag; its exact commit is recorded in
  `NeoStation-0.0.8-Packaging.json` and the packaged release identity.
- Final IPA identity: `NeoStation-0.0.8-SHA256SUMS.txt` and
  `NeoStation-0.0.8-Packaging.json` in the release assets.

The packaging workflow compares all 80 compiled images, including universal
Flutter AOT and dependency images, before and after signing. It rejects changes
to executable sections, ABI metadata and unrelated resources, verifies the
actual final ZIP and signatures, and checks all six bundle versions. Historical
build identities remain intact. Successful prior tests are reused; this
packaging step does not rerun commercial games or establish universal gameplay
compatibility. The maintainer reports that the scraping correction resolved the
reported iPhone 15 Pro Max crash.

The accompanying notice archive preserves the actual IPA notices and includes
the [cheat-source register](CHEAT_CATALOG_SOURCES.md),
[overlay credits](OVERLAY_SOURCES_AND_CREDITS.md) and
[embedded-runtime provenance](EMBEDDED_RUNTIME_PROVENANCE.md).
These records retain upstream licenses, restrictions and unresolved source
provenance questions; notices do not relicense third-party components.
Original author credits remain in the underlying files.

The 50 active cheat import profiles may share upstream collections and contain
overlapping contributions. Pokémon France remains withheld pending permission.
Cheats for known incompatible game revisions remain excluded, including the
uncovered Bladestorm BLES00113 version 1.01.

The original source stamp and native identities remain in the IPA. Apple
provisioning and signing must be applied by the user's sideloading tool.
