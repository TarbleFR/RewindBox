# Private RewindBox Build 593 — latest RPCS3 and MeloNX fixes

The maintainer explicitly requested a new IPA with both engines on 29 October
2026. This authorizes a private delivery on `Claude`, without a public release
or tag. Application version remains `0.0.8`; its new build number is `593`.

## Exact delivery inputs

The application baseline is delivered IPA588, source
`4a20e8e9a036314134df2605a6d33cd168c50098`, product tree
`81db3172b5ffb79e724c5ff6f944a61898fb7252`, successful run `40803513166`.
The new recipe records that tree directly and adds only the two new engine
cycles, their source proofs, and this delivery's recipe. Earlier delivery
helpers and native test suites are not replayed.

| Component | Source | Successful run | Artifact | Raw iPhone binary SHA-256 |
| --- | --- | --- | --- | --- |
| RPCS3 runtime source candidate | `c143be63f95751616f98d7bf9f1f34f297862df2` | `40814736023` | `12872058719` | `0966c03dcd264fdbcf813f9a7af320434c5dac0f555c1460c917358394b1f0ac` |
| MeloNX engine | `2f535c379ae385b68f0b33731d18efaf9e568047` | `40811657940` | `12870529413` | `f771e466746ebd67636653abbc979b0c15c9c933b4f45220d8ae7c70275259f4` |

The RPCS3 artifact keeps its original source-candidate identity, ABI30 and 88
exports. Its identity schema does not contain all fields of the historical
Core592 schema. A new delivery adapter authenticates the original bytes and
the 161 compiled/test inputs, checks the host/Core ABI and exact NeoSwap
boundary headers, and reuses the existing IPA structural validator with that
specific identity callback. It does not manufacture missing receipt fields.
PPU/SPU generated-code cache identities are unchanged.

MeloNX uses the archive's `ios-arm64/Ryujinx.Library.dylib` and its matching
identity, ABI2 and 47 exports. The archive's root convenience copies are not
authoritative. Its 62 adaptation inputs and actual successful build results
are authenticated without recompiling or replaying their tests.

RPCS3 contains the eligible texture-prehash check, exact bounded completed
shader lookup, retention of declared Vulkan dynamic state, and VM occupied
interval skipping with its dense-range fallback. MeloNX contains the second
cycle of JIT dataflow, cold upload-array lifetime, reused texture/conversion
storage, fenced texture staging and pipeline retirement changes. Details and
limits remain in their respective runtime follow-up documents.

## Assembly and verification

The recipe reuses the other authenticated engines and dependencies from the
delivered baseline. It performs one application Release build, packages the
new engines, verifies the signed code/data payloads against the original
artifacts, validates the legal bundle and all application/extension versions,
and encrypts the private IPA with a fresh delivery recipient. The resulting
IPA requires re-signing for installation, for example with SideStore.

This document initially records the authorized recipe. Build completion,
final IPA digest, delivery time and download verification will be added after
the run succeeds. No physical iPhone gameplay, FPS improvement or whole-app
memory reduction is claimed by this assembly.
