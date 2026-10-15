# Private Build 460 — pressable libretro skins

The maintainer requested an IPA for device testing on 15 October 2026.
Work stays on `Claude`, above Build 459 and the completed skin correction.
Output version: **0.0.7 (460)** through the delivery build-number override.

- Product source: `d6cb962d5597f7ecd7c81bb17b633e559c95d8d6`;
  documentation follow-up: `d50e3eab5797b18dcdc9493057f9cdf7bb963fef`.
- Existing evidence: libretro-checks run `38661616452`, successful native,
  Dart and skin-press jobs; nine simulated sessions, 270 checks. The report
  and limitations are in `libretro-skin-press.md`.
- Delivery: `retroarch-delivery.yml`, scope `full`, benchmark disabled.
  Public recipient `build-utils/delivery-460-recipient.pem`, SHA-256
  `bd4dc70b3879992497f54222d85a3deda8612533ec81144852a3fe6a99360f37`;
  private key stays on the maintainer's PC, outside Git.
- Native cores remain pinned: 34 libretro cores from run `38638115521`,
  source `fdeaef56f1acdeb3afa4fd0ef42e94114bc4a258`. Dolphin, RPCS3,
  ARMSX2 and the other native donor identities remain unchanged.
- Delivery inventory pins all skin correction inputs to the tested source.
  Native libretro checks may reuse the successful run only after the entire
  source/dependency tree, modes, recipe, Xcode and iPhone SDK match. An added,
  missing, changed or symlinked input prevents reuse. A failed, skipped or
  different CI result also prevents reuse; the original checks then run.
- The full delivery's other checks and the actual Release device build,
  final IPA validators, executable sealing and payload identity run normally.

First attempt `2f7a0960`, run `38707150124`, produced no IPA: native checks,
Flutter analysis and all Dart suites passed, then the Python delivery contract
`test_external_display_host_plist_test` rejected the newly distinct codec
reuse condition. Its replacement checks mandatory external-display compilation,
verified codec reuse and the fallback test execution separately. Passed Dart
phases may be reused only with identical source/dependency bytes, runner,
Flutter setup and test commands; the later failed Python contract is recorded
as failed and is executed again. This never labels the failed job successful.

## Verified delivery

- Candidate: `b92ff6e984d9086bd7da2d7361fe477804ce86aa` on `Claude`.
- [Delivery run 38708722521](https://github.com/TarbleFR/neostation-ios/actions/runs/38708722521):
  `checks`, `native` and the cold Release iPhone build passed. The warm build
  was intentionally skipped (benchmark disabled).
- Encrypted artifact `11960198085`, 215,456,157 bytes, expires 29 October 2026.
  Archive digest: `c1ea1e22ea031b62c5d8c4188609ecb2e894195e1fc8c54be01785cdc01503f7`.
- Sealed, decrypted IPA: **215,173,379 bytes**, SHA-256
  `a4734d95ff7c833d6fe17caadf732048bf545e7c42620323193a9315e48085fd`.
  It matches `SHA256SUMS` and `signed-payload-identity.json`.
- Copied to the maintainer's Downloads folder as
  `NeoStation-Build460-b92ff6e.ipa`, with the destination hash checked.
- Independent verification on the PC checked ZIP integrity, actual packaged
  source/build identity, **0.0.7 (460)** in the app and five extensions,
  34 libretro cores, device ARM64/code-signature metadata and all 76 sealed
  image code/data/ABI fingerprints. The libretro bridge contains
  `applyPressToLayers:down:`, `preparePaintedItems` and `setDPadDirections:`.
- Native libretro evidence is reused from `d6cb962d` / run `38661616452` only
  after successful CI and an exact comparison of 2,551 source/dependency
  files, Xcode 26.3 and iPhone SDK 26.2. Passed Dart phases retain their real
  `2f7a0960` / run `38707150124` identity and the later failed contract is
  explicitly recorded; changed pipeline guards pass in the final run.
- Product sources under `lib/`, `packages/`, `native/`, `assets/` and both
  pubspec files remain identical to the tested skin source `d6cb962d`.

This is a private test IPA for SideStore re-signing, with no public release.
No physical iPhone test or hardware controller validation is claimed from CI.
