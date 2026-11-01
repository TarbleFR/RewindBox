# RewindBox — project guide

Read this guide before work. It contains current project state and permanent
rules; detailed investigations and build receipts belong in `docs/`.
Last reconciled: **1 November 2026**, after private Build **609**.

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
| Application | **RewindBox 0.0.8 (610)**, private IPA; iOS 18+, SideStore re-signing |
| Delivery source | `df337fe7fcb52f512dc1c76195120e077b175f9b`, tree `ae37cc70ad0fcb0f54b04585130859ec560d34b5` |
| Delivery run / jobs | `41344399524`, attempt 1: preflight `124961014608`, application `124961131649`, both successful (11.5 min end to end); Flutter `124953301162` and Xcode16.4 native `124953301200` test jobs **reused** from run `41341797604` on identical product sources (only the recipe changed; the delivery contract was re-run fresh) |
| Downloaded IPA | `RewindBox-610.ipa`, 189880489 bytes; SHA-256 `6e92f25108d6e189858fdfa1df8758c35eeaf5ebad737f197816b6be150fb426` |
| Product baseline | Delivered 609 (`3d92f19e`, IPA `7908d128…`) plus the RA credentials fix `45d19d7`, the RPCS3 Dart profile changes (AC, DW6, GameDB keys) and the NeoSwap guest-relay boot preparation |
| MeloNX Core | Liveness Core retained from 609 (`1f12796c`, run `41323968050`, packaged fingerprint `c43a80bf…`); the later fragmented-read MeloNX inputs are source-only in 610 and recorded as such |
| RPCS3 Core | **Core 610** from `fefad81dbfc6890294def9b529f6e0d915fcfcbe`: run `41333351872`, artifact `13094491719`, dylib `e5e494ae…`, payload `9af73ca8…`; ABI 30, 88 exports, PPU/SPU cache identities unchanged ([report](docs/rpcs3-core610-2026-11-01.md)) |
| Dolphin Core | Upstream `7cac54161659421ed95c2cd1c0b0746539a4cd38`; producer on `0279198b1c33d869550cae3cf35f155b9d3a4f79`, job `124810929735` **SUCCESS** within whole run `41293321826` **FAILURE**; payload `640e4389…` retained from 608 and verified |
| ARMSX2 Core | Pinned iOSv2.6.0, ABI 9; producer on `0279198b1c33d869550cae3cf35f155b9d3a4f79`, job `124810929747` **SUCCESS** within whole run `41293321826` **FAILURE**; payload `fab55193…` retained from 608 and verified |
| Delivery proof | [Core 610 and IPA 610 report](docs/rpcs3-core610-2026-11-01.md), [delivery receipt](docs/evidence/rewind610/delivery.json), [downloaded-file checks](docs/evidence/rewind610/download610-verification.json); 609: [liveness delivery](docs/hogwarts609-liveness-2026-11-01.md), [receipt](docs/evidence/rewind609/delivery.json) |

610 is delivered, not a pending candidate. Do not reuse its number. Its first
delivery run `41341797604` failed in the retained MeloNX packaging check
(concurrent source-only MeloNX inputs); its successful test jobs were reused by
the delivered run. 609 (delivered 608 with the liveness MeloNX Core) remains
recorded in its own report.

**Build 611 is allocated** (1 November 2026) to the private IPA built on top of
delivered 610 with the standard recipe (below): the fragmented-read MeloNX Core
(source `a8d22fe`, run `41339055246`, artifact `13096647082`; see
[the fragmented-read report](docs/melonx-fragmented-reads-2026-11-01.md)), an
RPCS3 Core 611 carrying the RetroAchievements PS3 Core patch (built on the
RPCS3 Core route by the RPCS3 session), and the RetroAchievements commits held
until 610 was delivered. The MeloNX session triggers the single 611 delivery
after the RPCS3 session reviews its manifest. The 609-based 611 recipe
(`462620d`, `rewind611_*`, run `41340417135` cancelled) is superseded.
The libretro cores retained since 608 (artifact `12280822192`) expire on
3 November 2026 and the MeloNX native dependencies (`12458409441`) on
5 November; a later build needs fresh producers.

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
full application build.
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
| RetroAchievements session / translation / app language | [Central session and 608 delivery](docs/build608-ra-session-delivery.md), [credentials regression and in-game status (source fix after 608)](docs/ra-credentials-status-2026-11-01.md), [existing translation](docs/achievement-translation.md), [original translation tests](docs/evidence/achievement-translation-validation.json) |
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
