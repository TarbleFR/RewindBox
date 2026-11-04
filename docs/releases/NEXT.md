# RewindBox — next public release checklist

Updated 4 November 2026 (05:00 UTC). Owner: the main integration/release session
`012mUAShv9k6pSCnpW7oAF63`. This editorial inventory follows the release-note
rule in [AI_TASK_BOARD.md](../AI_TASK_BOARD.md); implementation tasks remain there.

## Baselines and publication state

- Last verified public release: [0.0.10, Build 559](https://github.com/TarbleFR/RewindBox/releases/tag/0.0.10),
  published 26 October 2026. It already announced embedded MeloNX, PS3 ISO launch,
  Liquid Glass and the asynchronous-submit option; do not present them as new.
- Latest verified private delivery: IPA 643, source
  `f19ed8cd26caa3b346108d3107e06bcf219a1de7`, RPCS3 Core 641 / MeloNX Core 642, on 640.
  See [delivery receipt](../evidence/rewind643/delivery.json) (640: [receipt](../evidence/rewind640/delivery.json)).
  Private delivery does not mean public publication.
- Next public tag/build/date: not assigned here. The final manifest determines
  inclusion. All rows below remain **not yet included in the next public announcement**.
- Seed inventory: the public559-to-private640 comparison has 745 commits.
  The items below are supported by current component documentation and the three
  active sessions; the release owner must reconcile the full final range before
  publishing, including reversions, dependencies and approved items beyond this
  initial editorial pass. Do not silently drop deferred items.

## Changes to carry into the next announcement

| Category | User-facing change | Evidence and current state |
| --- | --- | --- |
| New interface option | RewindBox Glacier style, reversible preset and bundled offline System Art; margin, clipped-title, glyph and carousel refinements. | Delivered-source baseline640; `fe37a2da`, `97d8a38f`; [Glacier record](../rewindbox-glacier-2026-11-02.md). Preserve explicit player choices. |
| Library improvements | Improved physical proportions and sides/spines of 3D game cases, editable backs and nondestructive image correction; ROM-ID GameTDB matching, scraping and French-manual lookup. | Baseline640; `cdba0321`, `6e636e9d`, `ef1ddfee`, `cf87abdc`, `1745b3e6`, `400d1f34`; [case/media documentation](../game-box-3d.md). Artwork/manual availability depends on sources. Existing 3D cases are improved, not newly introduced. |
| Cheats & Enhancements | Unified per-game page for available FPS/aspect-ratio/graphics/performance patches, compatibility information, toggles and restoration of original settings. | Baseline640; `23a847d6`; [enhancements](../ENHANCEMENTS.md). HD textures link to the existing feature; patches depend on title/version and may download from original sources. No universal FPS claim. |
| RetroAchievements account | Consistent account/sign-in state, shared Hardcore policy, session notifications and legacy-account migration across supported engines. | Delivered605/608, retained640; `d7992b1f`, `5912d1cd`, `c1d857c2`, `45d19d76`, `c00bdca6`; [608 delivery](../build608-ra-session-delivery.md). Do not imply every emulator/title has achievement sets. |
| RetroAchievements language and recognition | Achievement text follows the selected app language, including supported native overlays/external-display views; improved CHD/CSO identification, shared hashing, online lookup and clearer title-only matches. | `15c833c1`, `92f139fc`, `b06888a9`; [translation](../achievement-translation.md), [identification](../ra-game-identification-2026-11-01.md). Apple machine translation depends on runtime/language-model availability; recognition does not make unsupported dumps/sets supported. |
| Skins and orientation | Pocket skins for GameCube/Wii and PS2 Pocket black-matte skin; portrait/landscape choices, selected-layout orientation lock, controls and Menu routing. | Privately delivered640 via squash`705e90c7`; orientation/input host and simulator receipts in board. Preserve known limits: changes apply next launch; no blanket claim of physical-device validation. |
| PS2 playlist fix | Access the PS2 skin manager directly from the playlist menu. | Follow-up source`7dbb704`, [PR152 discussion](https://github.com/TarbleFR/RewindBox/pull/152), reviewed and integrated by main as `b8794226` (two product files, linear integration). True widget/selection/persistence tests4/4 and negative witness passed; board evidence reconciled separately. Packaged and verified in private IPA 643; iPhone path not yet observed. Closed PR's old head metadata is not the new handoff identity. |
| RPCS3 stability/performance work | Delivered synchronization/report-wait, shader/SPIR-V cache and PPU preparation corrections; additional AC audio/BO2 stutter investigation. | Cores630/634/636/638 in640; [636](../rpcs3-core636-2026-11-03.md), [638](../rpcs3-core638-2026-11-03.md). Core 641 (source `556648e7`, run `41766094450`) pinned `ff91455f` and verified offline: the Core's existing audio counters now reach the device logs ([641](../rpcs3-core641-2026-11-04.md)). Packaged in private IPA 643. Instrumentation is not itself an audio fix. No controlled FPS claim. |
| MeloNX optimization | Shader warm-up key parity and memory-pressure handling, with work on remaining stutters and unnecessary fallback costs. | PR153 shipped as Core639 in640. [Optimization map](../melonx-optimization-map-2026-11-03.md). Distinguish completed source changes from pending device comparisons. |
| MeloNX visual correctness | Fix rendering-order defects associated with stale/flickering frames in Hogwarts Legacy and investigate/correct the distinct SSBU path. | [PR154](https://github.com/TarbleFR/RewindBox/pull/154) lot integrated linearly (`f5a95ef4`) as MeloNX Core 642, frozen `8cd2e93c` (18 host gates passed, including the barrier-compaction rerun); Core CI run `41770120368` passed and pinned (fingerprint `281aa3a4…`); packaged in private IPA 643. Under MoltenVK 1.4.1+ an in-pass image barrier of a non-attachment now ends the render pass (every title), the Hogwarts in-pass read barrier is recorded again, and SSBU's descriptor template fallbacks are removed by the binding-sized scratch for every title. Not verified visually on iPhone yet; do not claim the flicker is fixed before a device recording. |

| Skins (new choices) | Two new bundled choices, GameCube Pocket — Original and Wii Pocket — Original, reproduce the approved Pocket designs in portrait and landscape alongside the existing packs; the Dolphin session's floating menu and performance buttons no longer cover skin controls. | [PR155](https://github.com/TarbleFR/RewindBox/pull/155), integrated `5ab7273d`, legal overlay `33bb2a22`, packaged in private IPA 643. Known limits: sharpness bounded by the approved boards (about 0.9 px/pt source); in the opposite landscape rotation the sensor housing covers part of GameCube X and the C-stick (closed, measured list); 375×667 iPhones letterboxed (36.3 pt targets); ARMSX2 floating menu over PS2 L1 in landscape reported only. Not observed on an iPhone. |

## Publication handoff checklist

- [ ] Reconcile every relevant change since actual public tag0.0.10 with the final shipped source and manifest.
- [ ] Confirm each announced feature/fix is present in the downloaded, verified release IPA.
- [ ] Mark retained, removed, deferred and already-announced items explicitly; carry deferrals forward.
- [ ] Preserve real test/compilation/device distinctions and document known limits; no estimated FPS gains.
- [ ] Produce the final ready-to-post English changelog with actual tag/build and download identity.
- [ ] After authorized publication, archive the exact notes under `docs/releases/<actual-tag>.md`, link the release, and start a fresh `NEXT.md` carrying all unannounced/unshipped items.
- [ ] After private delivery only, update packaged/test states while keeping the public baseline unchanged.

## English preview — development snapshot, not final release notes

A new RewindBox update is in the works! Here’s a preview of the planned improvements:

• Nintendo Switch / MeloNX: rendering fixes targeting flickering in Hogwarts Legacy and Super Smash Bros. Ultimate, alongside improvements to shader warm-up, memory handling and stability.

• PlayStation 3 / RPCS3: further stability, cache and synchronization improvements, with continued work on Black Ops II stutters and Assassin’s Creed audio issues.

• Skins and controls: Pocket skins for PS2, GameCube and Wii, plus new GameCube Pocket — Original and Wii Pocket — Original designs, portrait and landscape options, and orientation locking that follows your selected layout. PS2 players can open the skin manager directly from their playlist, and Dolphin's floating session buttons no longer cover skin controls.

• RetroAchievements: more consistent sign-in across supported emulators, shared Hardcore settings, improved game recognition, and achievement text that follows your app language through Apple’s translation features where available.

• Cheats & Enhancements: a unified place to manage compatible game patches, including graphics, aspect-ratio and performance options. Availability depends on the game and version.

• Library and artwork: more realistic 3D game cases, improved spines and backs, editable back covers, and better artwork and manual lookup.

• Interface: the RewindBox Glacier style, bundled offline system artwork, and refinements to menus, spacing and navigation.

Work and testing are still ongoing. The final changelog will confirm exactly what ships. Thank you for the reports, videos and logs—they help shape every update!
