# RewindBox — next public release checklist

Updated 10 November 2026. Owner: main integration/release session
`012mUAShv9k6pSCnpW7oAF63`. Implementation tasks and their current evidence remain
in [AI_TASK_BOARD.md](../AI_TASK_BOARD.md).

## Published baseline

**[RewindBox 0.0.11](https://github.com/TarbleFR/RewindBox/releases/tag/0.0.11) ·
Build 721**, published 10 November 2026 at 20:41:55 Europe/Paris.
RPCS3 Core 919 / MeloNX Core 719.
[Exact published notes](0.0.11.md) · [Public file verification](../evidence/release-0.0.11-public-download.json).

Items announced in 0.0.11 are now archived in its release notes and must not be
presented as new again. The complete earlier editorial inventory remains in
[its immutable pre-publication version](https://github.com/TarbleFR/RewindBox/blob/541d9789b0b56217ac4a9a660bee0b54c3f87dfd/docs/releases/NEXT.md).

## Changes after Build 721 to carry forward

- RPCS3 Core 920 pinned on 10 November 2026 ([record](../rpcs3-core920-lever-comparison.md); run `42838028676`, dylib
  `79d70a4d…`, pin `f9f2b478…`), delivered in the private IPA 722: the emulator no longer switches two of its settings off and on
  again by itself during the first minutes of every game to compare them (up to three minutes with one of them off);
  that comparison now runs only when asked for with the new setting "Lever comparison between report windows". The
  performance report also tells, for Black Ops II, how old the occlusion result is that each wait is for and what
  sending it early costs. Host tests only; no FPS claim.

- RPCS3 Core 921 pinned on 10 November 2026 ([record](../rpcs3-core921-stale-texture-release.md); run `42872597093`, dylib
  `5aee7478…`, pin `d4864cab…`), delivered in the private IPA 723: in Call of Duty: Black Ops II the memory kept growing during
  play (several gigabytes after a few minutes) because textures the game had replaced in its own memory were never
  released; once per frame the emulator now checks a few megabytes of unused textures against the game's memory and
  releases those the game has overwritten (setting "Stale texture release", on for every game). Textures still in the
  game's memory are kept. Host model only (113 MiB kept before, 24.7 MiB after on a Black Ops II-shaped stream); the
  iPhone memory gain is not measured yet.

| Category | User-facing change | Evidence and current state |
| --- | --- | --- |
| MeloNX memory | Hogwarts Legacy and other Switch games no longer keep a second copy of their saved shader cache in memory for the whole session: the cache is read from its file in place (Hogwarts' cache is about 790 MiB). | MeloNX session, lot 9 for IPA 722: MeloNX Core 721 = Core 719 + the main pipeline cache referenced in its mapped file (contract `29e58115`, 77 gates), with MoltenVK v1.4.2 rebuilt with the third part of the RewindBox patch (`394e6aef`, binary `6f65b2a6…`, run `42822060210`); built by main (run `42839257625`), pinned (`784fcc5d…`) and packaged in private IPA 722. macOS bench: +77.8 MiB copied against +32.4 MiB referenced at load for a 44 MB cache; the iPhone gain is extrapolated (about -0.75 GiB for Hogwarts), not measured. |
| MeloNX diagnostics | When the per-second journal of a Switch game is held up 300 ms or more, the journal now records what every thread is doing then (at most six times per session), to explain the long pauses still seen in Hogwarts Legacy. | MeloNX session, lot 9 (`8fd23a71`), reviewed by main (the watch suspends no thread itself and holds no lock while reading); packaged in private IPA 722. Measurement only. |
| Skins fix | In the RewindBox Pocket skins the game's picture now has the game's own shape (4:3, Switch 16:9) inside the skin's window, with no band and no stretching; where the drawn window did not have that shape, its frame is redrawn around the picture from the skin's own pixels. Buttons, sticks and touch areas do not move. | [PR169](https://github.com/TarbleFR/RewindBox/pull/169) (`a96f2ac7`), integrated by main (merge `c3e99f67`, declarations chained `a32101e9`): the seven archives rebuilt byte-identically, verifier 22 checks, skin simulator steps green (run `42843268978`); packaged in private IPA 722. The windows are smaller where the drawn opening was not the game's ratio (up to 31 pt per side on home-button iPhones, 33 pt above and below on Switch Pocket upright). Not observed on an iPhone. |

## Integrated source awaiting a later delivery

- **MeloNX Core 723 candidate:** integrated by main as `790664da` from
  `253cafd3`; frozen contract `091195da`, 81 local gates recorded by the owner.
  Includes GC keep-alive dormant-state/pause reporting, separate-array dirty
  tracking and texture-array barrier epochs, plus the host memory-breakdown
  work. It is not in public IPA721. Confirm the final Core/IPA receipts before
  announcing delivery, memory savings or playability.
- **Pocket pressed-state refinements, PR170:** integrated by main as
  `e864ee0`; legal revision chain `4934c5e8`. More precise pressed states,
  particularly Switch L/R, ZL/ZR and L3/R3. It is not in public IPA721.
  Preserve the owner’s executed tests and actual delivery state in the board;
  no physical-device validation is implied.

## Latest private deliveries

- **IPA723:** run `42878187148`, [receipt](../evidence/rewind723/delivery.json).
  RPCS3 Core 921; the rest of IPA722 retained.
- **IPA722:** run `42852972508`, [receipt](../evidence/rewind722/delivery.json).
  RPCS3 Core 920, MeloNX Core 721 with the three-part MoltenVK patch,
  skin framing PR169.
- Neither private package replaces the public 0.0.11 baseline.

## Carry-forward limits

- Residual Black Ops II performance, long Hogwarts Legacy pauses and device
  memory behavior still require the owner’s evidence and iPhone measurements.
  Preserve 1× image quality and correct game speed; no estimated FPS promise.
- Retain the documented Pocket touch-target, sensor-housing and orientation
  limits until a verified correction supersedes them.
- The closed Metal binary-archive prototype and the separate Switch 2
  experiment remain outside ordinary production delivery.

## Before the next public announcement

- [ ] Compare the final downloaded IPA and manifest against public Build721.
- [ ] Confirm which rows are delivered, source-only, deferred or superseded.
- [ ] Preserve host/simulator/iPhone distinctions and known limits.
- [ ] Publish a concise English changelog with exact build, link, bytes and SHA-256.
- [ ] Archive the published notes and refresh this list, keeping every unannounced item.
