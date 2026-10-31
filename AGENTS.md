# RewindBox — project guide

Read this guide before work. It contains current project state and permanent
rules; detailed investigations and build receipts belong in `docs/`.
Last reconciled: **31 October 2026**, after private Build **605**.

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
| Application | **RewindBox 0.0.8 (605)**, private IPA; iOS 18+, SideStore re-signing |
| Delivery source | `5de451091208c13926ccdb373a0a34f35ec2ee2d` |
| Delivery run / job | `41216465880` / `124584748706`, attempt 1, both successful |
| Product baseline | Delivered 604 plus 39 reviewed achievement-presentation product paths; other engines retained |
| MeloNX Core | `ada4058f5738465ac882934bb87224b637bcd0a1`; unchanged binaries validated by runtime source `510e683a149e811e68ea6ab5e766e85c44ab1057`, run `41121572662` |
| RPCS3 Core | `a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a`, successful run `41117115264` |
| Dolphin Core | Upstream `7cac54161659421ed95c2cd1c0b0746539a4cd38`, new presentation hook from producer `af5b18e67864e6555f54b7b4b6f1452ed82f6982`, successful run `41209480072` |
| Delivery proof | [Achievement translation / Build 605](docs/achievement-translation.md), [exact receipt](docs/evidence/achievement-translation-ipa/delivery.json), [downloaded-file checks](docs/evidence/achievement-translation-ipa/) |

605 is delivered, not a pending candidate. Do not reuse its number. Before
allocating another number, reconcile concurrent deliveries. A newer source
commit or Core-only artifact is not automatically a newer delivered IPA.
Old donor builds provide only their explicitly retained native resources;
they are never the application baseline. The public release and private IPA
are separate records; do not promote a private build through a README edit.

**Reserved, not delivered:** private Build **606**, Hogwarts performance and
console-organized diagnostics, is being prepared from delivered605. Its work
is tracked in [the device analysis](docs/hogwarts604-performance-2026-10-30.md).
Do not reuse this number or call the pending changes a shipped FPS improvement.

**Still unproven on iPhone:** Hogwarts crash recovery, removal of the intermittent
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
| MeloNX / Hogwarts / launch times | [Current crash and lot analysis](docs/melonx-build603-guard-crash-2026-10-30.md), [604 delivery](docs/rewind604-test-ipa.md), [MeloNX rules](docs/PROJECT_RULES.md#melonx) |
| RPCS3 / NeoSwap | [Latest compiled Core](docs/rpcs3-device601-core-2026-10-30.md), [open issues](docs/rpcs3-open-issues-2026-10-30.md), [RPCS3 rules](docs/PROJECT_RULES.md#rpcs3) |
| Achievement translation / app language | [Integration and validation](docs/achievement-translation.md), [exact tests](docs/evidence/achievement-translation-validation.json) |
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
