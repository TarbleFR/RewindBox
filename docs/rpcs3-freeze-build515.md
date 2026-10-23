# RewindBox Build 515 — private RPCS3 restore/freeze delivery

The maintainer approved the push and a private IPA on 23 October 2026. Frozen application source: `3bfbc91634227599c9d7746271482a55e41517b2`, run `39987867807`, job `120531806095`. Checks, native source closure and the Release iPhone build succeeded. Build 515 is frozen and must not be reused for another source.

The IPA includes the corrected compressed-TAR reader, preservation of unsatisfied RSX acquire dependencies, bounded long waits, complete freeze snapshots, and TAR/VM restore milestones. The RPCS3 Core is the exact validated source `a69860297d7b26dbb688df0daf16a31b42046462`, Core run `39982269326`. It reuses the verified Build 514 frontend, MeloNX engine and other emulator sources. The only product-source difference from the delivered 514 app is the RPCS3 host logging bridge; that bridge was compiled into this application. Unchanged Flutter and unrelated engine tests were not replayed.

The downloaded private artifact was authenticated, decrypted, and independently inspected. IPA `RewindBox-Build515.ipa`: **186,159,247 bytes**, SHA-256 `5cefa91667db20f1ea67a9619f076e24ee2d0fa1c1a2c377641a36fc41d88a8c`. Its identity agrees with SHA256SUMS, the signing receipt and the IPA's embedded source identity. All 7 application/extension bundles report 0.0.8 (515). All 86 Mach-O images are for iPhone ARM64, with 116 CodeDirectories and 132,664 code-page hashes verified; none is encrypted. The packaged Core's compiled payload equals the original Core artifact, and the new Core and host diagnostic markers are present. Existing PPU/SPU cache identities and save-state formats are retained.

The complete IPA passed the packaged RPCS3, MeloNX, Switch deletion, motion, navigation, artwork and catalogue gates. Signing is ad hoc for subsequent SideStore/AltStore Apple provisioning; installation and final device entitlements are not attested. No release or tag was published and main was not changed.

The exact user's save-state payload has not been tested. The source regression and its negative control are proven, with 20 compressed boundary cases passing under sanitizers and 34 real iPhone SDK syntax units passing in the Core campaign. The missing guest producer causing the retained God of War III RSX stall is still unidentified. This delivery does not establish recovery of that save, elimination of the physical-device freeze, or a measured FPS gain.

Machine-readable receipt: `docs/evidence/rpcs3-freeze515-delivery.json`. Prior investigation: `docs/rpcs3-freeze-restore-2026-10-23.md`.
