# RewindBox — private test IPA597

Build **597**, version **0.0.8**, compiled, independently verified and privately delivered.

## Actual build

- Source: `6ce5097737701afb4dc371013889bacdcef15140`; tree `0b8afa0d8614e1ceae519f6d2489fa49b9cbf368`.
- [Successful Apple run 40985625413](https://github.com/TarbleFR/RewindBox/actions/runs/40985625413), job 123835845426, attempt 1.
- Baseline: delivered 596, source `d5c5f107f7b514980033d1b95218aa9d2f640609`.
- One application compilation; neither native engine nor unchanged native suites rebuilt.
- Apple job: 1069  seconds; Xcode: 467.726 seconds; signing/export: 50.046 seconds.

The only host product delta is the reviewed `native/neoswap-storage/Store.cpp`,
SHA256 `87df68227cf9e113af51ec2ea8968d8af88170834611d560ce711cf168f1ca46`.
The CocoaPods copy and sources entry were verified before compilation. All other
five application product roots remain identical to delivered 596.

## Embedded cores

RPCS3 is the actual artifact 12946200694 from successful run 40981514937,
source `88cdc5e3e115a0b8587711d77147467baf38128b`.
ABI 30, 88 exports, 319 canonical postimages and 191 current inputs are authenticated.
The producer's 24 affected Apple modes retain their real scope: 8 executed in the
final Core run, 16 reused from preserved attempts, plus 11 unchanged historical
modes. PPU/SPU codegen identities remain unchanged from delivered 596.

MeloNX Core 87 is retained exactly from artifact 12931177865,
source `07f350480ab53b15d50953fb854dd8e3fc4e8d6c`, run 40949501203.
The original identities and compiled payloads remain intact through packaging
and signing. The retained engine's tests are not replayed for this delivery.

## Delivered file and verification

`RewindBox-Build 597.ipa` — **188329029 bytes**, SHA256:

```
b9e97907210458dfafe76fe471a3cde58fa18564488324e9adfd04dc7a7bb57d
```

The encrypted artifact was authenticated against GitHub's exact digest before
decryption. Verification of the actual downloaded IPA passes: 5350 ZIP entries,
CRC, both engine payloads, 88 Mach-O images, 85 thin-image preservation fingerprints,
three mono-ARM64 fat containers, and eight app/extension versions 0.0.8 (597).
Apple CI verified 88 ad hoc signing targets. The three fat-container hashes are
post-signing observations bound by the whole-IPA digest; no unavailable
before/after comparison is claimed for those containers. Independent Linux
verification does not claim to repeat Apple's cryptographic signature check.

Install on iOS 18 ARM64 by re-signing with SideStore. Physical-device gameplay
and FPS were not measured in this compilation task. The private file was saved
and its ephemeral recipient key deleted. No public release or tag was created.
Build 597 is consumed and must not be reused for a later delivery.

Detailed evidence: [rewind597-delivery.json](evidence/rewind597-delivery.json).
