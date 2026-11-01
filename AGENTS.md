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
| Application | **RewindBox 0.0.8 (609)**, private IPA; iOS 18+, SideStore re-signing |
| Delivery source | `3d92f19ee9c1e37d0813bc4a44a775923ccc2f5a`, tree `5b8090c5cc3a7410c3bdece0888c6470acd4da20` |
| Delivery run / jobs | `41325785563`, attempt 1: preflight `124905314379`, application `124905435858`, all successful |
| Downloaded IPA | `RewindBox-609.ipa`, 189813193 bytes; SHA-256 `7908d1283f722e6b8ed7999c374aab073736740a4cb9f0ce588468bf95620f97` |
| Product baseline | Delivered 608, source `90a9e8fcaa9bf68e2f5a2270cab6b636d62fff07` (IPA `575321ba…`); application sources byte-identical, only the MeloNX Core replaced |
| MeloNX Core | Liveness Core from `1f12796c6b8c3d509bc203e52c561e0d345e7bfc`: run `41323968050`, job `124899905807`, artifact `13090479414` (`83827a94…`), iPhone dylib `34fb7a5c…`, packaged fingerprint `c43a80bf…`; the delivered `ae78b4b` engine plus the A57 register/NZCV liveness fix and GC memory-load diagnostics ([contract](build-utils/melonx/liveness-core-contract.json)) |
| RPCS3 Core | Recovered 607 Core `a4ae86d085c231e3c5c93f7f72d2eced0f38ec24`, ABI 30, payload `7289ce4e…`, preserved and verified in 608 and 609; original producer `41243687649` failed after linking, separately recovered/verified for 607 |
| Dolphin Core | Upstream `7cac54161659421ed95c2cd1c0b0746539a4cd38`; producer on `0279198b1c33d869550cae3cf35f155b9d3a4f79`, job `124810929735` **SUCCESS** within whole run `41293321826` **FAILURE**; payload `640e4389…` retained from 608 and verified |
| ARMSX2 Core | Pinned iOSv2.6.0, ABI 9; producer on `0279198b1c33d869550cae3cf35f155b9d3a4f79`, job `124810929747` **SUCCESS** within whole run `41293321826` **FAILURE**; payload `fab55193…` retained from 608 and verified |
| Delivery proof | [Build 609 Hogwarts liveness delivery](docs/hogwarts609-liveness-2026-11-01.md), [delivery receipt](docs/evidence/rewind609/delivery.json), [downloaded-file checks](docs/evidence/rewind609/download609-verification.json); 608: [session delivery](docs/build608-ra-session-delivery.md), [receipt](docs/evidence/rewind608/delivery.json) |

609 is delivered, not a pending candidate. Do not reuse its number.
**Build 610 is allocated** (1 November 2026) to the private IPA that adds the RA
credentials fix `45d19d7` and the RPCS3 Core 610 lot (`core610_20261101`, patch
`a63b9643`, Core route `.github/workflows/rpcs3-core610.yml`) to delivered 609;
it retains the 609 liveness MeloNX Core. The concurrent MeloNX diagnostics
commit `2e0793ac` is source-only in 610 (not compiled into its MeloNX Core);
the next MeloNX Core increment must use **611 or later**. See
[the Core 610 report](docs/rpcs3-core610-2026-11-01.md). Before
allocating another number, reconcile concurrent deliveries. A newer source
commit or Core-only artifact is not automatically a newer delivered IPA.
Old donor builds provide only their explicitly retained native resources;
they are never the application baseline. The public release and private IPA
are separate records; do not promote a private build through a README edit.

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
