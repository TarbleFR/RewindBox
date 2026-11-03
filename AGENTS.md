# RewindBox — project guide

Read this guide before work. It contains current project state and permanent
rules; detailed investigations and build receipts belong in `docs/`.
Last reconciled: **3 November 2026**, after private Build **629**.

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
| Application | **RewindBox 0.0.8 (629)**, private IPA; iOS 18+, SideStore re-signing (628 was not delivered) |
| Delivery source | `6aae16b9ca0683eb64aa4881dc6855b05b363763`; frozen manifest [`build-utils/delivery/629.json`](build-utils/delivery/629.json) (freeze commit `79d866ef`, effective product digest `140e5707…`, replayed from the delivered 626 effective tree `b8403d43…`) |
| Delivery run / jobs | `41622115556`, attempt 1, standard recipe: preflight, flutter and native (both fresh), republish and application, all successful (about 21 min) |
| Downloaded IPA | `RewindBox-629.ipa`, 194618465 bytes; SHA-256 `952b2641a1151746e43dc81b500371911a668e5736131acf8de75542d0f2bfe6` |
| Product baseline | Delivered 626 plus MeloNX Core 628 (reviewed `e34dccf9`, `1ce1cd14`, `2620d011`) and RPCS3 Core 627 of session 012mUASm (reviewed `40c6502a`..`8e68bdee`, `2abb1ac2`, pin `021a15e4`; maintainer request) |
| MeloNX Core | **Core 628** (replaced): Core run `41614833262`, source `1ce1cd14`, packaged fingerprint `dfd9061e…`, iPhone library `1699cf38…` ([pin](build-utils/melonx/dma-core-pin.json)); replaces Core 626 `18fbb04c…` |
| RPCS3 Core | **Core 627** (replaced): Core and Apple host run `41610162888`, source `6891f9a0`, payload `eccf8535…` ([pin](build-utils/rpcs3/core-pin.json)); replaces Core 624 `e906fbd5…` |
| Dolphin Core | Retained from 608 (payload `640e4389…`) through the archive republished by run `41504526945` |
| ARMSX2 Core | Retained from 608 (payload `fab55193…`, ABI 9) through the archive republished by run `41504526945` |
| libretro / MeloNX dependencies | Retained through the archives republished by run `41504526945` (republished again by runs `41516165812`, `41527072487`, `41555079757`, `41562838932`, `41569913763`, `41574628897`, `41591090457`, `41598013782` and `41622115556`) |
| Delivery proof | [delivery receipt](docs/evidence/rewind629/delivery.json), [signed payload identity](docs/evidence/rewind629/signed-payload-identity.json) (90 images), [downloaded-file checks](docs/evidence/rewind629/download629-verification.json); 626: [receipt](docs/evidence/rewind626/delivery.json) |

629 is delivered, not a pending candidate. Do not reuse its number; 628 was not delivered. It carries RPCS3 Core 627
(the maintainer's request; no iPhone result yet, see [the Core 627 record](docs/rpcs3-core627-2026-11-03.md)).
MeloNX Core 628 (Hogwarts Legacy: the read-back into a buffer also runs over other textures, which get a write signal without a write, buffers exempt, as a guest write there would
give them; build 626 never copied into buffers, 352 and 742 copies declined as occupied; on MoltenVK, a texture's
write-to-read barrier inside a render pass it is not an attachment of is deferred to the next begin of that pass,
since MoltenVK restarts the Metal render pass for each in-pass image barrier; the GPU's busy time is measured from the
Metal command buffers, MoltenVK's own figure including the queue wait) has no iPhone result yet
([624 to 626 journals, and the 628 change](docs/melonx-624-measurement-2026-11-03.md)); no FPS claim.
`libretro_internal_bridge` changed from 626 although its effective sources did not (reported as an undeclared image
change, not blocking). Attempt 1 (run `41618683768`) failed at the RPCS3 Core install check: the fixed marker list asked
for the canary file of Cores 587-624, which Core 627 renames on purpose; the recipe fix `79d866ef` accepts the canary
named after its Core.
The private 629 recipient key was deleted after the verified delivery.

Earlier delivery explanations (626 and older), negative results and outstanding
device checks are preserved in [the historical notes](docs/history/agents-delivery-notes-2026-11-03.md).
Read only the build implicated by the current task; the table above is the
current delivered reference. For focused diagnostics, use
[the evidence index](docs/AI_EVIDENCE_INDEX.md).

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
