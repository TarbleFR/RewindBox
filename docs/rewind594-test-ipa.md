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

**The application Release build and CI validation completed successfully on
attempt 1.** [Run 40848076659](https://github.com/TarbleFR/RewindBox/actions/runs/40848076659)
built source `97365ce57f17499101e88d50019b6c63be554b83`. Job `123360403474`
ran on 29 October 2026 from 09:14:29 to 09:28:29 UTC, for 14 minutes.
The recorded product tree is `1d43bbac26b3146d5d24afff0553d0c18d5bc20e`.
One application build reused the two authenticated engine artifacts.

| Produced IPA | Verified value |
| --- | --- |
| File | `RewindBox-Build594.ipa` |
| Version | `0.0.8 (594)` for the application and all seven extensions |
| Size | 188,316,921 bytes |
| SHA256 | `714021770922547c532e1439466d5725b4f8eb17c18ca629fe996d985124fe63` |
| Signature checks in CI | 88 ad hoc signature records verified |
| Signing preservation | Code/data sections and ABI metadata unchanged by signing across 85 Mach-O payloads |
| Xcode build | 320.895 seconds |
| Signing and export | 52.616 seconds |

The CI checks bind both signed engine payloads to their original artifacts and
validate the application structure and version numbers. The decrypted IPA has
the size and SHA256 shown above. Independent post-download verification passed
on this actual IPA: both full embedded receipts and both signed engine payloads
match the authenticated original archives. Cryptographic signature validation
is the Apple runner's check; the offline check verifies signature structure and
payload identity. The verified file is ready for download in the conversation.
Persistent private-file saving remains pending explicit maintainer authorization.
SideStore re-signing is required; no device installation has been tested.

Receipts: [delivery record](evidence/rewind594-delivery.json) and
[retained build and validation evidence](evidence/rewind594/).
The complete French inventory is in [the 594 changelog](rewind594-changelog-fr.md).

No public release or tag is created. Physical iPhone gameplay, launch-time,
FPS and whole-process memory improvements remain to be measured on the device.
