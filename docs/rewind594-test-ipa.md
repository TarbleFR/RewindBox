# Private RewindBox Build 594 — RPCS3 Core and MeloNX engine 82

The maintainer explicitly requested an IPA combining the newly compiled RPCS3
Core and the latest MeloNX fixes on 29 October 2026. This delivery uses `Claude`,
application version `0.0.8` and new build number `594`.

## Exact inputs

The baseline is the successfully delivered private IPA593, source
`b13dc1155e5f4971ba9e32ea4a267f6e447ea1bf`, product tree
`bb3c99e15e52ac109d5eaf827c80cb8e5c7759c6`, run `40818195216`.
The recipe starts from that recorded index, retains its file modes and adds
only the reviewed changes since that delivery. Its 193 source/evidence delta
files come from five immutable commits. The application interface, packages,
assets and dependency locks stay at the delivered baseline. The only native
product source change is `native/melonx/EmbeddedLaunchPreflight.cs`, bound to
the compiled engine82 adaptation map.

| Component | Compiled source | Artifact | Validation |
| --- | --- | --- | --- |
| RPCS3 Core | `fe587e27fcefadaa36315a3ddc7dc1edba17b825` | `12883027017` | Apple run `40839976736`, all 24 pending modes and the iPhone ARM64 Core passed |
| MeloNX engine82 | `ebcee3529645a781311429a869434005e76d6275` | `12883480724` | NativeAOT compiled in `40837997888`; corrected runtime validation `40841402428` passed |

The RPCS3 dylib SHA256 is
`13b4c505434a7a0291abad47fa157ce0c9e20741e297f24dc2575e760e0e691b`.
Its original ABI30 identity, 88 exports, 190 build/test inputs and PPU/SPU cache
identities are preserved. The cumulative 13-change inventory is in
`docs/rpcs3-core-followup-2026-10-29.md`.

MeloNX's validated archive SHA256 is
`be55d705ea93ae27c1756c29c3ec7a16ec51c60b9ace10556dcc751a00f5af45`.
The genuine `ios-arm64` binary is 37,585,008 bytes with SHA256
`f7efba4e5025be2147f8a47fe4de9b2eba2df63537aaa2c496e74b57413af2e5`.
The recipe selects that binary and its original ABI2/47-export identity. It retains the
original compilation provenance and its failed first smoke alongside the
successful corrected smoke: two distinct guest executions, two clean closes
and released backing memory. It binds 74 preparation inputs, four recipe
inputs and the two Swift bridge files plus corrected smoke. No engine or
unchanged native test suite is rebuilt for this packaging.

## Assembly and delivery status

One application Release build is planned. Final checks bind both signed engine
payloads to the original authenticated artifacts, verify signatures and the
legal bundle, and check application and extension version numbers. A fresh
recipient protects the private downloadable IPA. Re-sign with SideStore for
installation. This preparation is not yet a successful IPA delivery.

No public release or tag is created. Physical iPhone gameplay, launch-time,
FPS and whole-process memory improvements remain to be measured on the device.
