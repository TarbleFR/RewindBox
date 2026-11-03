# RewindBox — project guide

Read this guide before work. It contains current project state and permanent
rules; detailed investigations and build receipts belong in `docs/`.
Last reconciled: **3 November 2026**, after private Build **621**.

## Start here

1. Inspect the actual branch, HEAD and working diff. Preserve concurrent work;
   a handoff or historical note does not override the checked-out sources.
2. Identify the user's current task and existing authorization. A historical
   “source only”, “no IPA” or approval for one build applies to that task, not
   automatically to every subsequent task. Do not ask again for authorization
   already given in the active session.
3. Read the relevant section of [component rules](docs/PROJECT_RULES.md) and
   the source/evidence documents linked below before changing that component.
4. Work from the latest verified delivered product plus the reviewed delta.
   Cross-check earlier attempts and rejected approaches before proposing a fix.

## Current delivered reference

| Item | Verified reference |
| --- | --- |
| Application | **RewindBox 0.0.8 (621)**, private IPA; iOS 18+, SideStore re-signing |
| Delivery source | `6140e070af75e914b0d3298d838f8a279899c671`; frozen manifest [`build-utils/delivery/621.json`](build-utils/delivery/621.json) (freeze commit `7d88bfe0`, effective product digest `cdfed832…`, replayed from the delivered 620 effective tree `bf6ee0b0…`) |
| Delivery run / jobs | `41555079757`, attempt 1, standard recipe: preflight, flutter and native (both fresh), republish and application, all successful (about 20 min) |
| Downloaded IPA | `RewindBox-621.ipa`, 194334617 bytes; SHA-256 `1521e25b5118d60fc5a2509e6a001bd310b6fadc32c4d6af1df7dc1c73ba65b4` |
| Product baseline | Delivered 620 plus 9 reviewed commits: MeloNX GPU region copies, precise DMA reads, thread QoS and the 1 GiB pipeline cache budget (`816930fe`, refrozen after the independent review in `4ad8814e`), the 64 MiB gen0 GC budget (`4295b522`), `frame_report.py --passes` (`403dc3c5`), and the game box and French manuals of another session (`ef1ddfee`, `05b5a5df`, `cf87abdc`, `400d1f34`, `09eeb75b`). 16 RPCS3 Core 621 commits of another session are **source-only** for 622; the 69 inherited deferred paths of `b06888a9` stay deferred |
| MeloNX Core | **Core 621** (replaced): Core run `41552490728`, source `4ad8814e`, packaged fingerprint `07e9d695…` ([pin](build-utils/melonx/dma-core-pin.json)); replaces the 620 GPU source-copy Core `c5627b99…` |
| RPCS3 Core | **Core 619** kept (`unchangedFromBase`, payload `44fc928e…`, the delivered pin bytes restored by `2212d1dc`) |
| Dolphin Core | Retained from 608 (payload `640e4389…`) through the archive republished by run `41504526945` |
| ARMSX2 Core | Retained from 608 (payload `fab55193…`, ABI 9) through the archive republished by run `41504526945` |
| libretro / MeloNX dependencies | Retained through the archives republished by run `41504526945` (republished again by runs `41516165812`, `41527072487` and `41555079757`) |
| Delivery proof | [delivery receipt](docs/evidence/rewind621/delivery.json), [signed payload identity](docs/evidence/rewind621/signed-payload-identity.json) (90 images), [downloaded-file checks](docs/evidence/rewind621/download621-verification.json); 620: [receipt](docs/evidence/rewind620/delivery.json) |

620 is delivered, not a pending candidate. Do not reuse its number. The Hogwarts
GPU source copy (a DMA copy whose linear source is held by a GPU-modified texture is copied
on the GPU instead of reading the texture back; title `0100f7e00c70e000` only), the
presentation-gap journal (`gaps=`, `long=`) and the attribution of the remaining slow source
reads have no iPhone result yet ([cause, change and what the next run reads](docs/melonx-hogwarts-618-measurement-2026-11-02.md));
no FPS claim. `Frameworks/armsx2_internal_bridge` and `dolphin_internal_bridge` changed
from 619 although their sources did not (reported as undeclared image changes, not
blocking). The private 620 recipient key was deleted after the verified delivery.

621 is delivered, not a pending candidate. Do not reuse its number. It is the MeloNX and
game-box build on the delivered 620 (maintainer, 3 November 2026: "deviens le build 621 rpcs3
n'est pas pret de finir"); its draft and recipient key replaced the RPCS3 session's first 621
draft. The MeloNX Core 621 changes have no iPhone result yet
([620 journals and the 621 changes](docs/melonx-620-measurement-2026-11-02.md)); no FPS
claim. The Hogwarts GPU region copy only goes into block-linear surfaces; a linear
destination (read-back) stays on the guest path and is counted as `linearDestination`.
`armsx2_internal_bridge`, `dolphin_internal_bridge` and `rpcs3_internal_bridge` changed from
620 although their effective sources did not (reported as undeclared image changes, not
blocking). The private 621 recipient key was deleted after the verified delivery. 622 is the
RPCS3 session's Core 621 build, on the recorded 621.

619 is delivered, not a pending candidate. Do not reuse its number. RPCS3 Core 619
(Assassin's Creed `BLES00158`/`BLUS30089`: ZCULL reports written when the guest reads
them, RSX label accesses off the 16 KiB page shared with reports 0-703; Black Ops II
`BLES01717`: pinned-draw affine clipping and asynchronous MoltenVK submits in Automatic)
has no iPhone result yet ([what the next run reads](docs/rpcs3-core619-2026-11-02.md));
no FPS claim. `Frameworks/armsx2_internal_bridge`, `dolphin_internal_bridge` and
`melonx_internal_bridge` changed from 618 although their sources did not (reported as
undeclared image changes, not blocking). The private 619 recipient key was deleted after
the verified delivery.

618 is delivered, not a pending candidate. Do not reuse its number. The Hogwarts
region upload (a partial DMA copy from linear memory into a GPU texture updates that
texture region, guest memory patched untracked; title `0100f7e00c70e000` only) has no
iPhone result yet ([what the next run reads](docs/melonx-hogwarts-617-measurement-2026-11-02.md));
no FPS claim. `Frameworks/armsx2_internal_bridge` and `Frameworks/melonx_internal_bridge`
changed from 617 although their sources did not (reported as undeclared image changes, not
blocking). The private 618 recipient key was deleted after the verified delivery. 619 is
reserved by the RPCS3 session (Core 619 on the delivered 618).

617 is delivered, not a pending candidate. Do not reuse its number. The
Hogwarts DMA-copy Core (float DMA copies on the GPU for title
`0100f7e00c70e000` only, logged bindless delta passes) has no iPhone result yet
([what the next run reads](docs/melonx-hogwarts-614-measurement-2026-11-02.md));
no FPS claim. `Frameworks/armsx2_internal_bridge` changed from 616 although its
sources did not (reported as an undeclared image change, not blocking). The
private 617 recipient key was deleted after the verified delivery.

616 is delivered, not a pending candidate. Do not reuse its number. Its three
RPCS3 changes (Assassin's Creed ZCULL polls without GPU waits; Black Ops II
pinned-depth order and SPU object read-ahead) have no iPhone result yet
([protocol](docs/rpcs3-core616-2026-11-02.md), section 6); no FPS claim.
`Frameworks/dolphin_internal_bridge` changed from 615 although its sources did
not (reported as an undeclared image change, not blocking). The private 616
recipient key was deleted after the verified delivery.

615 is delivered, not a pending candidate. Do not reuse its number. The Glacier
menu and the RetroAchievements Keychain fix have no iPhone result yet; the
Glacier composition was checked by real Flutter rendering against the approved
mock-up ([captures](docs/design/rewindbox-glacier/verification/renders/)).
`Frameworks/rpcs3_internal_bridge` changed from 614 although its sources did not
(reported as an undeclared image change, not blocking, as in 614). The private
615 recipient key was deleted after the verified delivery.

614 is delivered, not a pending candidate. Do not reuse its number. Its MeloNX
Core has no iPhone result yet ([protocol](docs/melonx-bindless-deltas-2026-11-02.md),
section 6); no FPS claim. `Frameworks/rpcs3_internal_bridge` changed from 613
although its sources did not (reported as an undeclared image change, not
blocking; not reproducible-build checked). The private 614 recipient key was
deleted after the verified delivery.

613 is delivered, not a pending candidate. Do not reuse its number. The Assassin's Creed
ZCULL default comes from the maintainer's iPhone result on BLES00158; the
Black Ops II SPU change and the ZCULL probe have no iPhone result yet
([protocol](docs/rpcs3-core613-2026-11-02.md)). The private 613 recipient key
was deleted after the verified delivery. The RPCS3 Core route depends on the
MoltenVK dependency run `41239096061`, whose artifacts expire on 14 November
2026 at 20:30 UTC.

612 is delivered, not a pending candidate. Do not reuse its number. It is the
first build on a standard-recipe base: the recipe now replays from the base's
delivered effective tree and supports an unchanged pinned Core
([recipe note](docs/standard-delivery-recipe.md)). Its accuracy test page changes
no default; no iPhone result yet. The private 612 recipient key was deleted
after the verified delivery. The RPCS3 Core route depends on the MoltenVK
dependency run `41239096061`, whose artifacts expire on 14 November 2026 at
20:30 UTC.

611 is delivered, not a pending candidate. Do not reuse its number. Its earlier
attempts (runs `41373565877`, `41374661558`, `41377459800`) failed in the recipe
or in load-sensitive tests and delivered nothing; each retry changed only the
recipe or a reviewed test. The private 611 recipient key was deleted after the
verified delivery.

610 is delivered, not a pending candidate. Do not reuse its number. Its first
delivery run `41341797604` failed in the retained MeloNX packaging check
(concurrent source-only MeloNX inputs); its successful test jobs were reused by
the delivered run. 609 (delivered 608 with the liveness MeloNX Core) remains
recorded in its own report.

**Build 611 delivered** (2 November 2026) on top of delivered 610 with the
standard recipe: its manifest was reviewed by an independent review agent (the
RPCS3 session, moved to 612 by the maintainer, did not review it); the earlier
609-based 611 recipe (`462620d`, `rewind611_*`, run `41340417135` cancelled) is
superseded. 612 (RPCS3 session) is delivered on top of it.

**Delivered 609:** delivered 608 with only the MeloNX Core replaced. The new
Core corrects LightningJit liveness metadata that lost guest NZCV/vector state
(FMOV marked as writing flags, 41 entries missing a destination read, 16-bit
by-element `Vm` width). It also logs the GC memory-load inputs behind gen2
activity. The downloaded IPA, eight bundles and all 90 images passed
verification. 86 images keep their 608 fingerprints; `Runner`
(version string) and two bridges rebuilt from identical sources differ, with
the bridge cause not identified. 608's RetroAchievements session and
translation features, the other engines and the `0279198` test evidence are
retained. These liveness defects are demonstrated by executable
reproductions, but they are **not proven** to cause the Hogwarts guard crash.
**609 does not contain** the RetroAchievements credentials fix (`45d19d7`,
[report](docs/ra-credentials-status-2026-11-01.md)) that landed on `Claude`
after the 609 source `3d92f19`. 609 therefore keeps the 608 RA sign-in
regression. The next IPA needs that fix with fresh Flutter/native tests and a
full application build. PS3 RetroAchievements through RPCS3
([report](docs/ra-ps3-rpcs3-2026-11-01.md)) is source only: its Core hooks are
staged outside the canonical delta (folding them requires an authorized Core
build); with the current Core, PS3 reports "not available for this core".
Existing unrelated compiler warnings are retained (see the 609 log review).
Device FPS and loading-time gains are still unmeasured; see
[the device analysis](docs/hogwarts604-performance-2026-10-30.md).

**Still unproven on iPhone:** whether the 609 liveness fix affects the
Hogwarts crash, what the new GC fields show, removal of the intermittent
minute-long GPU wait, Unreal CVar consumption, black-texture recovery and FPS
gains. The MeloNX presentation animation was removed; its old measured cost
was 0.510–0.513 s, not a measured new-device speedup. The 604 receipt does not
establish resolution of BO2/GOW3 freezes or Assassin's Creed flickering.
Apple model download/consent, real achievement translation and in-game unlock
presentation still require physical-device validation; see the [605 report](docs/achievement-translation.md).

## Identity, scope and coordination

- Use **RewindBox** in new user-facing text and output names. Preserve upstream
  NeoStation credits, licenses and compatibility identifiers: bundle IDs,
  storage paths, preferences, method channels and native ABI symbols.
  See [rebranding rules](docs/REBRANDING.md).
- Work on **`Claude`**. Do not modify `main`, `backup`, baseline refs, tags or
  releases, or create replacement AI branches, without explicit authorization.
  Inspect the actual workflow triggers; old `experimental`-branch notes are history.
- Respect the manual [AI coordination policy](docs/AI_ORCHESTRATION.md): Claude
  Code is the principal coder/integrator, Codex coordinates/reviews and Cursor
  provides scoped assistance, subject to the maintainer's explicit task.
  One writer per checkout; never discard another session's edits or force a ref.
- For a handoff, consult [the task board](docs/AI_TASK_BOARD.md) and
  [handoff](docs/AI_HANDOFF.md), then verify Git. Do not invent progress or
  trigger another assistant, paid API use, extra credits or automatic top-ups.
- Push, CI/IPA production and publication follow the authorization for the
  current task; documentation cleanup alone does not request a new IPA.
- **Retired:** Mario Kart Pad/KartPad, Dusklight, the Ports playlist and MeloNX's
  external StikDebug/Shortcut launch fallback. Do not compile, download, package
  or restore their runtime code. Preserve player files and historical evidence.

## Protect the product and player data

- Preserve the delivered library behavior and reviewed baseline exceptions.
  No speculative migration, duplicate hiding, reset or parallel library.
- Never clear saves, games, firmware, keys, caches, mods or pairing to hide a
  lifecycle defect. Backups and explicit replacement rules stay intact.
- Keep source corrections canonical and reviewable. Do not stack historical
  CI patches that silently create code different from the reviewed sources.
- Do not change unrelated engines, helpers, debug scripts or emulation settings.
  An available route is not proof of native readiness or a running game.
- Preserve session ownership, generation checks, cancellation, late-callback
  handling and the real technical error. Verify first launch and relaunch,
  cross-engine transitions, failure recovery and safe teardown when affected.

## Validation and delivery

- Reuse successful evidence only with the tested source, run, tools, dependencies
  and identical tested inputs, including transitive inputs. Label it **reused**.
  Rerun affected checks after a change or relevant new failure; do not replay
  unchanged suites or rebuild unchanged cores for documentary receipts.
- Each fix needs appropriate behavioral verification. Do not weaken assertions,
  suppress failures or call a failed original run successful. A scoped recovery
  or separate runtime validation retains its own provenance.
- Start each delivery from the last verified delivered IPA and add only reviewed
  changes. Check the new components, unchanged component identities, licenses
  and actual signed IPA; do not recursively re-prove every historical delivery.
- **Same recipe for every build (maintainer rule, 1 November 2026).** Every
  private IPA is built by the same standard delivery recipe, which adds only what
  changed since the last verified delivered IPA. Changed components are rebuilt
  by their own producer route and replaced; unchanged components keep their
  authenticated identity; a test group reruns only when one of its inputs changed
  (otherwise its pinned evidence is reused and labelled), and the delivery
  contract always reruns. Do not copy a new per-build recipe
  (`rewindNNN_*.py`, `rewindNNN-*.yml`): declare the build's changes in its
  manifest and extend the standard recipe only for a new kind of change. A
  failed delivery is retried by changing only the recipe, reusing its successful
  test jobs. See [standard delivery recipe](docs/standard-delivery-recipe.md).
- Compute shared source contracts once per job with
  `build-utils/delivery_contract_memo.py`; preserve file modes and invalidate on
  changed inputs. Report observed durations and bottlenecks; target under
  40 minutes end to end. See [delivery speed](docs/delivery-speed.md).
- A Core swap is permitted only when the application source and base payload
  match its contract. Any host/application source change needs the full application
  build. See [Core swap delivery](docs/core-swap-delivery.md).
- Keep exact source, build, artifact ID, size and SHA-256 bindings. Never reuse
  an artifact name to disguise another revision. Preserve Release, ABI, legal,
  version, payload-preservation and signing checks.
- For an authorized IPA, verify the actual downloaded file before providing a
  direct usable download link. Encrypted transport is not the deliverable.
  Keep recipient private keys out of Git; delete them after verified delivery.
  Ad hoc preparation does not replace SideStore's Apple signing/provisioning.

## Diagnostics, language and claims

- Use existing app journals, source evidence and executable reproductions.
  **Never request `.ips`, Jetsam or watchdog reports** or block work on them.
- Separate confirmed source defects, hypotheses, fresh tests, reused evidence,
  skipped checks and physical-device observations. Compilation, simulator
  success and host benchmarks do not prove an iPhone fix or FPS improvement.
- Separate processes/builds, cold and warm launches, duplicated/rotated logs,
  and game modes. Preserve negative measurements and disproven approaches.
- Every changed UI label, help/error message and accessibility string needs
  all 12 locales: `en`, `es`, `ru`, `zh`, `zh_Hant`, `pt`, `fr`, `de`, `it`,
  `id`, `ja`, `ko`. Use project catalogs; verify keys, placeholders and
  Traditional Chinese selection. Keep raw diagnostics separate from translated
  explanations. English fallback is not a missing translation's replacement.
- GitHub release notes and announcements are English only unless the maintainer
  requests otherwise. Preserve credits and third-party distribution terms.

## Where to continue

| Task | Read before changing it |
| --- | --- |
| Architecture or handoff | [Architecture](ARCHITECTURE.md), [Claude entry point](CLAUDE.md), [manual workflow](docs/AI_WORKFLOW_CURSOR_CLAUDE.md) |
| MeloNX / Hogwarts / launch times | [609 liveness and GC diagnostics](docs/hogwarts609-liveness-2026-11-01.md), [crash and lot analysis](docs/melonx-build603-guard-crash-2026-10-30.md), [604 delivery](docs/rewind604-test-ipa.md), [MeloNX rules](docs/PROJECT_RULES.md#melonx) |
| RPCS3 / NeoSwap | [Retained 607 Core identity and recovery contract](.github/diagnostics/rpcs3runtime607_core.py), [Verified 608 preservation](docs/build608-ra-session-delivery.md), [RPCS3 rules](docs/PROJECT_RULES.md#rpcs3) |
| RetroAchievements session / translation / app language | [Central session and 608 delivery](docs/build608-ra-session-delivery.md), [credentials regression and in-game status (source fix after 608)](docs/ra-credentials-status-2026-11-01.md), [PS3 through RPCS3 (staged Core hooks, host client)](docs/ra-ps3-rpcs3-2026-11-01.md), [game identification: .chd/.cso, library hash = in-game hash, online lookup (612)](docs/ra-game-identification-2026-11-01.md), [existing translation](docs/achievement-translation.md), [original translation tests](docs/evidence/achievement-translation-validation.json) |
| Library, UI, native routing | [Library and lifecycle rules](docs/PROJECT_RULES.md#library-and-lifecycle), [Liquid Glass](docs/liquid-glass-ui.md) |
| Shaders, cheats, HD textures | [Catalog and content rules](docs/PROJECT_RULES.md#catalogs-shaders-and-content), [enhancements](docs/ENHANCEMENTS.md), [licenses](docs/LEGAL_AND_CREDITS.md) |
| Previous decisions or rejected attempts | [Historical guide and exact snapshot](docs/history/README.md); search only the relevant component/build |

## Keep this guide small

Update the current-state table after a verified delivery instead of prepending
another build diary. Put detailed work in a focused `docs/<topic>.md` and
machine-readable evidence under `docs/evidence/`; link it here when current.
Keep pending work, verified source changes, compiled components and delivered
IPAs distinct. Move superseded narrative to history without deleting receipts,
failed attempts, restrictions or rejected experiments. Update permanent rules
only when their meaning changes; do not duplicate them in every build record.
