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

This is a private test delivery. The requested destination is the maintainer's
Downloads folder. Record the exact candidate, run, artifact, sealed IPA hash,
byte count and final destination after validation. No physical iPhone test or
hardware controller validation is claimed from CI.
