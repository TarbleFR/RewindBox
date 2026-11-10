# Private RewindBox IPA598 — 30 October 2026

The requested IPA integrates the already compiled MeloNX occlusion core into
the delivered IPA597 application baseline. Version remains **0.0.8 (598)**.

- Source: `1c30df6870e4c45bbc4b405e7bc8e1ba5dd5d2e4`; tree `c5e117c273394987ae430ec6559a3a95e7e1faee`.
- [Successful Apple run 41010479756](https://github.com/TarbleFR/RewindBox/actions/runs/41010479756), job 123914984519, attempt 1.
- One application compilation; neither engine nor unchanged native suites rebuilt.
- Job 784 seconds; Xcode 335.121 seconds; signing/export 52.734 seconds.

MeloNX comes from source `e7143e566462bf6e3d9c143ce24532c1ad7aeb10`,
run 40998920652, artifact 12953505421. Its original identity, 108 preparation
inputs, 148 adapted members, ABI2 and 47 required exports are authenticated.
Producer evidence retains two fresh Apple gates, 30 authenticated historical
results and two simulator homebrew sessions with backing release. These tests
were not replayed for packaging. Optional GPU experiments remain OFF by default.

RPCS3 remains source `88cdc5e3e115a0b8587711d77147467baf38128b`,
run 40981514937, artifact 12946200694. Its final signed dylib SHA256 is exactly
identical to delivered597. The latest NeoSwap Store is retained. The only native
product-source delta since597 is `native/melonx/EmbeddedGraphicsSettings.cs`;
the five other application product roots are identical to597. The older527 IPA
is only the established native resource donor used by the assembly recipe.

`RewindBox-Build598.ipa` is **188340669 bytes**, SHA256:

```
27cc3ce633a3378949d88448792b48691f99e313e6be723063f7be958272325b
```

The downloaded encrypted archive matches GitHub's exact SHA256. Independent
verification of the actual decrypted IPA passes: 5350 ZIP entries and CRC,
both core identities and compiled payloads, all 88 ARM64 iOS Mach-O images,
85 thin-image preservation fingerprints, three mono-ARM64 fat containers and
eight application/extension versions 0.0.8 (598). Apple CI verified all 88 ad hoc
signing targets and the actual final exported ZIP. Independent Linux checks do
not claim cryptographic codesign verification. Fat-container hashes are final
observations bound by the whole-IPA digest, without a before/after claim.

The private file was saved and its ephemeral recipient private key deleted.
Install by re-signing with SideStore; minimum iOS18. No public release or tag,
physical-device gameplay or FPS result is claimed. Build598 is consumed;
documentary receipts require no further build.

Detailed evidence: [rewind598-delivery.json](evidence/rewind598-delivery.json).
