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

Before delivery, record exact source, run IDs, actual results, output IPA hash,
version and packaged core count here. The 34-core artifact and other native
engine identities remain unchanged. The delivery uses a session public
recipient; its private key stays outside Git. No public release is requested.

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
