# Private Build 461 — directional skin refinement

The maintainer authorized further implementation and a new test IPA on
15 October 2026, on `Claude`. Target version: **0.0.7 (461)**.
This extends the verified directional renderer described in
`libretro-directional-pressure.md`; Build 460 does not contain these refinements.

## Common implementation

- The pressure renderer subtracts intersections with other artwork and opaque
  screen areas. Exclusive fragments animate; shared pixels stay in the original
  background. Touch margins are not artwork boundaries. Adjacent edges alone
  are not overlaps. Masks align to physical pixels, with the existing sampling
  apron preserving filtering at rest.
- A bounded alpha-silhouette analysis recognizes four-arm crosses with unequal
  arms, an off-centre stem and transparent padding. It derives independent arm
  rectangles from the real image. Ambiguous opaque, round or disconnected
  shapes retain the conservative directional partition. The centre and the
  other arms remain fixed; diagonals activate the two corresponding regions.
- Local inverse deformation tapers to zero near excluded pixels. It preserves
  the colour/alpha of the untouched image, without a glow or duplicate button.
  Authored pressed variants use the same exclusive masks. No new skin-format
  field or mandatory `_pressed` image is invented.
- Release uses a prepared 120 ms, eased keyframe sequence. The renderer selects
  12 states when its layout estimate permits it, otherwise the existing 8-state
  density, within the same 32 MiB prepared-image budget. A new press immediately
  cancels release. Pixel support and row/column weights are computed once during
  preparation; no image decoding or deformation is introduced at touch time.
- Input tracking, core mappings, controller implementation and persisted skin
  preferences remain unchanged. These changes belong to the common libretro
  renderer, including hidden consoles and future cores using that renderer.

## Atomic Pink: actual source, not a guessed format

Reference: **GBC-Atomic Pink**, identifier `com.anonymaus.gbc.atomicpink`,
credited to **Anonymaus#9917** by the catalogue.

- Repository: `delta-skins/delta-skins.github.io`, revision
  `61dad28f552051bc05f519f968e913bf243d22eb`.
- Path: `gbc/GBC-AtomicPink.deltaskin`; 4,692,343 bytes; SHA-256
  `d870e53c3728c6b84aeb163b489e03e8ab903ad0927f18ce27dd3235ddcfec84`.
- The archive contains `info.json` and four PDF composites: standard and
  edge-to-edge iPhone, portrait and landscape. There are no independent button
  assets or `_pressed` images. Landscape A+B is a drawn button, not an invisible
  alias. The adapter must preserve both its artwork and its two input bits.
- CI downloads this pinned archive only for reference tests. Its artwork is not
  added to the repository or the IPA. iPad tests exercise the existing iPhone
  layout fallback; the archive has no native iPad variant.

## Validation plan and boundaries

The native suites exercise geometry, pixel isolation, 8/12-state preparation,
invalid inputs, default-console mappings and touch ownership. UIKit sessions
cover independent, opaque/textured composite, translucent, authored-state,
overlapping and asymmetric artwork. Four Atomic Pink representations are
checked explicitly, including A+B, plus portrait/landscape geometry at phone
and tablet sizes. A 440 x 956 layout is a geometry check, not an iPhone test.

Controller handoff tests connect an Apple virtual controller while a touch is
held, verify cancellation, disconnect it, and require a fresh touch to reach
the core. The virtual controller does not validate Bluetooth or physical pads.
DeSmuME and PCE run homebrew with their real cores; GBC, NES, PSX and N64 input
profiles use the deterministic NeoTest core. This does not claim real gameplay
validation of those latter cores.

The 34-core artifact and other native engine identities remain unchanged.
The delivery uses a session public recipient; its private key stays outside
Git. No public release is requested.

## Executed skin checks

- UIKit source: `7c05e44f89cb5f5095e9c1f4c4c745e36e2bde0e`;
  [run 38731165154](https://github.com/TarbleFR/neostation-ios/actions/runs/38731165154),
  successful `skin-press` job `116409014310`.
- **23 sessions, 1,380 successful checks**: 12 iPhone and 11 iPad Simulator
  sessions, including the actual Atomic Pink archive, transparent asymmetric
  crosses, overlapping areas and previously passing skin fixtures.
- **152 directional pixel comparisons**, zero changed pixels outside the
  permitted regions. Released states match their prepared resting states.
  Prepared rest versus the unsplit original has at most **1/255** channel
  difference on the translucent asymmetric fixture, and zero on the other
  measured skins. No pixel exceeds two levels in the rest comparison.
- Atomic Pink's four phone representations, landscape A+B input, iPad fallback,
  touch-to-controller handoff and the first fresh touch after disconnection
  pass. Both devices also pass authored-state reload after cache eviction.
- All measured layouts use 12 release states. Maximum reserved pressure-image
  storage is **26,716,272 bytes (25.48 MiB)**, under the 32 MiB limit. The native
  pixel tests separately exercise both the 8-state and 12-state preparation.
- Isolated direction-state updates measure **2.10–14.12 microseconds average**
  per measured session on these CI machines. This excludes display presentation,
  physical touch, frame pacing and the pixel-comparison harness; it is not a
  device latency claim.
- Evidence archive `11971488387`: 52,655,402 bytes, SHA-256
  `b49dbc2dd5efa924d1cdecd3c94122e983dd34508cd5b2046b07153303fb54af`.

The same run's portable step initially failed to compile because the test
helper `Rect` collided with Apple's macOS `Rect` typedef. Renaming that helper
to `BoxTestRect` changes no product behaviour or assertion. The fixed portable
suite subsequently passes in delivery run `38732938115` at `fa201417`.
The original failed step remains a failure; its rendering and iPhone compile
results have separate provenance. Delivery checks **2,554 identical UIKit
source/dependency files** and the exact successful rendering job before the
Release build. No renderer, fixture, simulator probe or skin-test recipe is
excluded from that comparison.

At candidate `fa2014171e23771d1abd1a5d80c243813af771c2`, delivery run
`38732938115` also actually executes and passes all **16 native frontend
executables**, including **998 pressure-pixel checks** and **6,025 touch-tracker
checks**. The default-control sweep covers 1,848 buttons, 352 D-pads, 32 sticks
and 16 touch screens. All **71 bridge sources compile and link for iPhone**;
this phase is executed again because the closed comparison includes a changed
delivery test. It is not reported as reused. Flutter analysis reports no
issues; the configured Dart suites and pipeline contracts pass, including
the 19 delivery-gate tests and 17 external-display host tests.

The additional product changes are in `LibretroSkinPressure.h`,
`LibretroSkinPressure.m` and `LibretroSkinRenderer.m` under
`packages/libretro_internal_bridge/ios/Classes/`. Regression coverage changes
`test/libretro_host/frontend/skin_pressure_test.m`,
`test/libretro_simulator/skin_press_probe.h` and
`test/libretro_skin_press_probe.py`. The two workflows and delivery/reuse
guards bind these results to the candidate; no other emulator engine changes.

## Verified delivery

- Candidate: `fa2014171e23771d1abd1a5d80c243813af771c2`, branch `Claude`.
- [Delivery run 38732938115](https://github.com/TarbleFR/neostation-ios/actions/runs/38732938115):
  `checks`, `native` and the cold Release device build all succeeded. The warm
  benchmark build was intentionally skipped. The Release build starts only
  after successful verification of the exact UIKit session evidence.
- Encrypted artifact `11974260046`, 215,785,373 bytes, expires 29 October 2026;
  archive SHA-256
  `027329f1b21b0ec4afb53d50f75630f182f40a3524b3f19e8da7921441ea3efd`.
  Public recipient: `build-utils/delivery-461-recipient.pem`.
- Downloaded, decrypted IPA: **NeoStation-Build461-fa201417.ipa**,
  **215,189,456 bytes**, SHA-256
  `f799f5512ee558bbd3a10e98cbf35cba11bfe93a109cff839616de702ed541ab`.
  The downloaded bytes match both `SHA256SUMS` and the sealed payload identity.
- Independent checks of those bytes confirm **0.0.7 (461)** in the application
  and all five extensions, the packaged source identity, all **34 libretro
  cores**, and the code/data/ABI fingerprints of all **76 sealed images**.
  The iOS ARM64 bridge contains the new shared-exclusion selector and the
  pressure-region/deformation functions. CI verifies the final ZIP's signatures
  with `codesign --verify --deep --strict` after export.
- This private IPA requires the usual Apple re-signing with SideStore.
  Installation, gameplay, touch latency, ProMotion pacing and physical
  controllers have **not** been tested on a real iPhone in this cycle.

The maintainer's PC was offline; the IPA and the captured-state evidence are
provided as downloadable files. The build number 461 must not be reused.

## Required manual iPhone validation

| Check | Procedure and expected result |
| --- | --- |
| Atomic Pink | Import the reference GBC archive; test all available phone orientations. A, B and the landscape A+B drawing depress and return without ghost images. |
| D-pad | Hold each direction, sweep around all diagonals without lifting, then reverse. Only active arms move, with no centre movement or seams. |
| Multiple fingers | Hold a diagonal plus A/B and a shoulder key on a suitable console. Lift fingers individually; remaining inputs stay active. |
| Interruptions | While holding controls, open the menu, change skin in game, rotate, background and return. No input remains latched. |
| Physical controller | Connect/disconnect a Bluetooth or USB controller while a touch is held; test simultaneous controller/touch use under the configured policy. |
| Responsiveness | Observe immediate contact response, long holds, rapid alternating taps and smooth release at the device refresh rate. Measure frame pacing and memory with Instruments if available. |
| Fidelity | Compare the resting skin to the original, especially translucent edges, shared regions, unusual D-pad shapes and screen cutouts. |

Automatic tests cannot establish physical touch latency, real-device frame
pacing, thermal behaviour or Bluetooth reliability. Fully shared or ambiguous
artwork may keep some pixels static rather than deform a neighbouring control.
Arbitrary rotated or decorative shapes are not claimed universally recognized.
