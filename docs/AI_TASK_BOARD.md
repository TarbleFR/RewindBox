# RewindBox — shared requirements and results

The single working contract for Claude Code, Codex and Cursor. Update this file
in place. Read the shared rules and only the task and evidence rows relevant to
the current request. Component reports retain detailed evidence, not parallel
task queues. Current working observations were reconciled on 3 November 2026
with Claude Code session `012mUAShv9k6pSCnpW7oAF63` and GitHub `de69400c`.
A later working diff can be ahead of that commit.

## Shared working rules

- The maintainer's current request and existing authorization determine scope.
  Historical build permissions or restrictions apply to their original task.
  Reconfirm only when a material new action requires permission.
- Claude Code owns substantive implementation and final integration. Codex
  coordinates and independently reviews, or makes focused changes delegated by
  the maintainer. Cursor assists with authorized, non-overlapping tasks.
- Work on `Claude`. Preserve `main`, `backup`, baseline refs, tags and releases
  unless specifically authorized. Inspect actual workflow triggers.
- Before editing, inspect branch, HEAD and working diff. One writer per checkout
  or explicitly owned section. Preserve concurrent work and local-only changes.
  Do not force-push, reset, clean or silently resolve another agent's changes.
- Each agent must update this shared contract after a meaningful result and
  before ending, compacting or handing off. Update permanent instructions when
  their meaning changes. Update only owned task rows and affected references.
  Record the date, input identity, evidence, result and next action. A resumed
  session verifies what changed instead of restarting the investigation.
- During handoff, record owner, dirty paths, local and remote commits, test
  results, unresolved failures and next action here. The next writer verifies
  Git. A quota limit does not transfer ownership or chat history automatically.
- Use one coding agent for routine work. Independent reviews must have separate
  scope. Do not launch paid external agents, poll quotas or switch subscriptions
  automatically. Claude, ChatGPT and Cursor have separate included allowances.
  Use their official subscription sign-ins. Keep API credits and auto-top-up
  off unless expressly authorized. Cursor third-party models can incur charges.
- Push, CI/IPA builds, tags and releases follow the task's authorization.
  Claude Code has standing authorization to fast-forward its own commits to
  `origin/Claude`, with `[skip ci]` unless CI was requested. If the remote
  advanced, rebase only its own unpushed commits and inspect conflicts. This
  standing push permission applies to Claude Code only. A permission refusal
  must be reported, never retried through a route intended to defeat it.
- This contract is a record of authorized work, not an automatic task scheduler.
  Changes to the contract do not grant build, payment or publication permission.

## Diagnose, correct and verify

1. Read the active task, then its direct source and evidence references. Use
   bounded file/symbol searches and batch independent reads. Avoid reading the
   whole history, loading long journals or recreating an existing report.
2. Reopen a conclusion only for a relevant changed input, contradictory
   observation or untested path. A new session alone is not new evidence.
   Preserve rejected hypotheses and inconclusive results with their conditions.
3. Give each diagnostic command one question and resulting decision. After two
   equivalent inconclusive attempts, change the method or name the missing
   input. A blocked download stops its dependent step, not independent work.
4. Move from an established cause to the smallest supported correction. Test
   the affected behavior and required contracts. Reuse success only with the
   same relevant code, transitive dependencies, tools, configuration and inputs.
   Label evidence fresh, reused or not run. A change can invalidate earlier tests.
5. Record a performance hypothesis against its measured bottleneck and
   comparison conditions. CPU encoding, GPU execution, queue wait, launch time
   and FPS measure different things. Host tests or compilation do not establish
   an iPhone gain.
6. Keep raw evidence in the existing component/evidence location. Summarize its
   decisive outcome here with a link. Preserve failures and input identities.
   Keep secrets, recipient keys and private player logs out of instruction files.
7. When compacting, retain the active request, permissions, branch/HEAD, owned
   dirty paths, input identities, findings, failed attempts, patch/test state,
   blocker and next action. Return concise outcomes to the user in French.

## Product and delivery requirements

- Use RewindBox in new product text. Preserve upstream NeoStation credits,
  licenses, bundle IDs, storage paths, preferences, method channels and ABI.
  Follow [rebranding](REBRANDING.md) and the relevant [component rules](PROJECT_RULES.md).
- Retired components are Mario Kart Pad/KartPad, Dusklight, the Ports playlist
  and MeloNX's external StikDebug/Shortcut launch fallback. Preserve player
  files and historical evidence while keeping their runtime code retired.
- Preserve delivered library behavior and reviewed exceptions. Never erase
  games, saves, firmware, keys, caches, mods or pairing to hide a defect.
  Preserve backups and approved replacement rules. Avoid speculative migrations,
  duplicate hiding or parallel libraries.
- Keep source corrections canonical and reviewable. Preserve generation and
  ownership checks, cancellation, late callbacks, real errors and safe teardown.
  Verify first launch, relaunch, recovery and cross-engine transitions when affected.
  Keep changes scoped to the requested engines, helpers and emulation settings.
- Preserve all 12 locales for changed labels, help, errors and accessibility
  strings. Use en, es, ru, zh, zh_Hant, pt, fr, de, it, id, ja and ko. Verify
  keys, placeholders and Traditional Chinese selection. Raw diagnostics remain
  separate. English fallback does not replace a missing translation. GitHub release
  notes are English unless the maintainer asks otherwise.
- Use existing app journals and executable reproductions. Never request .ips,
  Jetsam or watchdog reports or block work on them. Separate builds, runs,
  cold/warm launches, duplicated logs and game modes.
- Every private IPA uses the [standard delivery recipe](standard-delivery-recipe.md)
  from the last verified delivered IPA plus reviewed changes. Declare the delta
  in its manifest. Rebuild changed components and retain authenticated unchanged
  identities. Rerun affected test groups and always rerun the delivery contract.
  Do not create per-build recipe copies. Keep source, run, artifact, size and hash
  bindings, Release, ABI, legal, signing and payload preservation checks.
- A failed delivery retries only the changed recipe while retaining valid test
  evidence. Compute shared contracts with `build-utils/delivery_contract_memo.py`.
  Preserve modes and invalidate changed inputs. Report observed bottlenecks and
  durations against the under-40-minute end-to-end target.
- Follow [Core swap rules](core-swap-delivery.md). A changed host/application
  source requires the full application build. Windows checks do not compile
  an iPhone IPA. Use authorized Xcode/macOS CI for that step.
- Verify the actual downloaded IPA before giving its usable private link.
  Encrypted transport is not the deliverable. Keep recipient keys out of Git
  and delete private keys after verified delivery. SideStore still supplies
  Apple signing/provisioning. Separate source, tested, compiled, delivered and
  observed-on-iPhone states. Do not claim unmeasured FPS gains.

## Active requirements

| Task and owner | Required outcome and acceptance | Verified state and next action |
| --- | --- | --- |
| TASK-631-MELONX — Claude Code, session `012mUAShv9k6pSCnpW7oAF63` | Review and optimize existing MeloNX work, fix demonstrable omissions and regressions. Source `13700519`, tree `82a29e6f`, SDK 10.0.100. Validate the real prepared source, affected gates and artifact identity. The original 30–40% encoding-time reduction target is a target, not a measured result. | Local review in progress, ahead of GitHub. Queue fixture passes 28/28 scenarios and 6530 checks in real-source and adapter modes with exact SDK. Nine of ten gates passed on that preparation, hogwarts-dma-copies failed. Latest stable observation is a region-upload DMA overlapping-buffer tracking gap under investigation. Next, Claude reproduces and corrects that gap, then records the final evidence/commit and invalidated gates. Core 631 remains reserved for IPA 635. |
| TASK-634-RPCS3 — Claude Code integration | Integrate the verified Core 634 with its host changes and preserve source/artifact bindings. Includes Core 630. | Core and Apple-host jobs of run `41696834507` passed on `792d72c9`. Apple-host artifact `13261452573` downloaded and size/hash verified in the active VM. Core artifact `13261039942` still needs its own verification/pin. No iPhone run. Next, finish the pin checks when MeloNX source is ready. |
| TASK-635-IPA — Claude Code integration | Previously requested private 635 from delivered 629 with reviewed MeloNX 631, RPCS3 634, MoltenVK v1.4.2 and Pocket skins. Preserve the [manifest](../build-utils/delivery/635.json) and [plan](ipa-635-plan-2026-11-03.md). | Preparation, not delivery. The active request prioritizes MeloNX correction. Former SDK/upstream/artifact network refusals are resolved in the active VM. Contracts, new Core production, pins, freeze and actual IPA verification remain dependent work. Next, reconcile the plan with the final source and existing build authorization after the current correction. |
| Shared contract — Codex owns this consolidation, then each agent owns its updates | One shared requirements/results file, automatic update obligation for all agents, no duplicated coordination documents. | Published in `c587c7c5`, five redundant files removed, 49 links verified. All three Claude skills updated to v2 and point here. Next, Claude reconciles only its task/evidence rows against its local corrections at a stable checkpoint. |

Detailed producer identities and hashes remain in the
[Core 634 record](rpcs3-core634-2026-11-03.md),
[MeloNX encoding record](melonx-629-encoding-2026-11-03.md) and pins.
No new Core or IPA is implied by a local test result.

## Findings to carry forward

| Finding and scope | Result and evidence | Reopen only when |
| --- | --- | --- |
| Network prerequisites in the active VM | Resolved after environment access became Full. Official SDK 10.0.100 downloaded and SHA-512 verified, MeloNX `13700519` fetched, LibHac source `23e402eb` exists, archive 614 downloaded/authenticated and required NuGet versions reached. The Ryulynx ryujinx.libhac feed returns 404 but LibHac is built from source. Observed in the session above, awaiting Claude's final file-backed receipt. | A required request actually fails, the environment changes or the source/package requirement changes. Earlier 403 notes describe their recorded sessions. |
| Queued syncpoint blocking guarantees | Before `ec5e3df9`, 21/28 fixture scenarios passed. Renderer barrier, retained unpublished FIFO head and 3D increment ordering corrected. Reports in [queue evidence](evidence/melonx-631-queued-syncpoints/). Exact-SDK real-source run now passes, observed in the active VM. | Relevant queue/caller/fixture inputs change or contradictory runtime evidence appears. |
| Real-source fidelity of queue fixtures | Public IncrementSyncpoint and Syncpointb method frames differed from reconstructed doubles. Claude aligned the fixture with upstream. Both fixture modes pass 28/28 with SDK 10.0.100, changes still local when observed. | Upstream method frames or the extracted production regions change. |
| Current 631 gate result | Nine of ten passed on the tested preparation. hogwarts-dma-copies failed and region-upload tracking is being reviewed. Gate composition/expectation failures must be distinguished from production defects. | The correction changes tested inputs, or a new result contradicts the recorded gate. |
| Upstream UE workaround | Full history shows `13700519` descends from 2.6 and contains `f924c98c`. The earlier missing-ancestor suspicion came from incomplete history. | The pinned revision changes or a different upstream fix is identified. |
| Cowork attribution | Repository/session search did not identify attributable Cowork work. Owner redirected Claude to its own MeloNX work. | The owner provides a specific Cowork deliverable or a verifiable reference is discovered. |

## Update a task in place

Keep each entry concise. Retain the objective and authorization, acceptance
criteria, owner/dirty paths, exact source/build/input identity, finding and
confidence, correction, command/result and evidence reference, remaining blocker,
next action and condition for reopening. Record a failed or inconclusive attempt
as such. Update the existing row instead of appending another task diary.
Reconcile local findings with the final committed proof before marking complete.
A conflict between this summary and direct source/receipts must be investigated
and corrected, not silently resolved by choosing the newest prose.

## Evidence by component

| Scope | Direct references |
| --- | --- |
| Architecture and routing | Relevant section of [ARCHITECTURE.md](../ARCHITECTURE.md) |
| MeloNX measurements and rejected approaches | [optimization map](melonx-optimization-map-2026-11-03.md), [encoding](melonx-629-encoding-2026-11-03.md), [MoltenVK](melonx-moltenvk-rebuild-2026-11-03.md), `build-utils/melonx/dma-core-pin.json`, `build-utils/melonx/moltenvk-rebuild-pin.json` |
| RPCS3 | [Core 634](rpcs3-core634-2026-11-03.md), [Core 630](rpcs3-core630-2026-11-03.md), `build-utils/rpcs3/core-pin.json` |
| Delivery | [standard recipe](standard-delivery-recipe.md), [635 plan](ipa-635-plan-2026-11-03.md), [delivery speed](delivery-speed.md) |
| Library and lifecycle | Relevant section of [PROJECT_RULES.md](PROJECT_RULES.md), [library folders](library-folders-2026-10-10.md) |
| Flutter UI | [Liquid Glass](liquid-glass-ui.md), `lib/screens/systems_screen/`, affected `test/` files |
| Wii and GameCube skins | [Dolphin skins](dolphin-skins.md), [Pocket originals](pocket-originals-2026-11-03.md), [input evidence](evidence/pocket-originals/) |
| RetroAchievements and languages | [608](build608-ra-session-delivery.md), [credentials](ra-credentials-status-2026-11-01.md), [game identity](ra-game-identification-2026-11-01.md), [PS3 hooks](ra-ps3-rpcs3-2026-11-01.md), [translation](achievement-translation.md) |
| Cheats, patches, HD and rights | Relevant [component rules](PROJECT_RULES.md), [enhancements](ENHANCEMENTS.md), [licenses](LEGAL_AND_CREDITS.md) |
| Earlier findings | [existing history](history/README.md), [prior delivery notes](history/agents-delivery-notes-2026-11-03.md). Search only the implicated component/build. |

## MeloNX reuse study — nxnative

Requested by the maintainer, reviewed by Codex on 3 November 2026.
Static source audit of [seedds/nxnative](https://github.com/seedds/nxnative/blob/6a60b722e8af8daaf36f9f056485e5d21c15a887/README.md) at
`6a60b722e8af8daaf36f9f056485e5d21c15a887`. No port, Metal build or iPhone game test
was performed. This is a scoped reuse assessment for MeloNX, not a new native
runtime implementation.

MeloNX currently uses GPU/GAL → Vulkan → MoltenVK → Metal
(`native/melonx/EmbeddedSession.cs`, Vulkan backend and threaded rendering).
nxnative intercepts game NVN/Vulkan/EGL/GL imports and replays them on Metal,
with per-game offline shader preparation and its own Horizon host. Reusing its
graphics ideas does not by itself replace MeloNX CPU execution or create a
generic native-game launcher.

| Candidate | Applicability and evidence | Next targeted validation |
| --- | --- | --- |
| Dynamic texture offsets and gather | Compare [Instructions.cs](https://github.com/seedds/nxnative/blob/6a60b722e8af8daaf36f9f056485e5d21c15a887/dm/third_party/ryujinx/src/Ryujinx.Graphics.Shader/CodeGen/Spirv/Instructions.cs). Runtime offsets are built as OpCompositeConstruct rather than invalid constant composites. Vulkan has an extra constraint below. Presence/absence in the exact prepared MeloNX source is not yet established. | Start with a synthetic dynamic gather and a constant-offset control on MeloNX `13700519` plus current adapters. Compare old/new SPIR-V, Vulkan validation, output pixels and unchanged constant cases before a minimal port. |
| Mixed bindless-handle phis | [TryTableHandle](https://github.com/seedds/nxnative/blob/6a60b722e8af8daaf36f9f056485e5d21c15a887/dm/third_party/ryujinx/src/Ryujinx.Graphics.Shader/Translation/Optimizations/BindlessElimination.cs) selects among C2 candidates when a phi also contains other values. RewindBox already handles nested/loop phis, SHFL and proven local spills in `adapt_bindless.py` and `adapt_bindless_sources.py`. | Reproduce only a remaining mixed case. Prove predication and the assumption that an unmatched candidate's read result is unused. Preserve image-store/atomic restrictions and avoid marking every texture modified. |
| Dirty memory and resource retirement | [t_dirty_retire_race.c](https://github.com/seedds/nxnative/blob/6a60b722e8af8daaf36f9f056485e5d21c15a887/dm/gfx/tests/t_dirty_retire_race.c) reproduces protection vs pool retirement, checking actual writability after retirement. Related upload-slot/budget tests protect memory still used by the GPU. | Transpose the invariant to MeloNX tracking/fences and affected DMA overlap/teardown paths. C/Objective-C structures are not direct C# patches. |
| Image atomics bounds | Vendored shader emitter and [bounds tests](https://github.com/seedds/nxnative/blob/6a60b722e8af8daaf36f9f056485e5d21c15a887/dm/tools/tests/test_image_atomic_bounds.py) provide candidate cases. MetalImageAtomics pairs emitter flags with SPIRV-Cross/MSL support. | Compare the real backend capabilities and exact shader; validate SPIR-V, compiled MSL and GPU behavior. Avoid enabling a Metal-only flag globally in the Vulkan path. |
| Texture-buffer fallback | nxnative's RecordTexelFetch1D pairs shader coordinates with its host's 16384-wide 2D binding. | Treat the emitter and resource binding as one contract. A shader-only transplant would be incomplete. |

**Vulkan constraint.** Without `maintenance8` enabled, image operand `Offset`
is legal only for gather instructions under
[VUID-RuntimeSpirv-Offset-10213](https://docs.vulkan.org/refpages/latest/refpages/source/RuntimeSpirv.html#VUID-RuntimeSpirv-Offset-10213).
nxnative also uses runtime Offset for sample/fetch operations in its offline
SPIRV-Cross path. Do not transfer that whole change to MeloNX without actual
capability support or a legal alternative lowering. Use the matching
`spirv-val --target-env`, runtime Vulkan checks and rendered-output comparison.

**Boundaries established from code.** [hle_vk.m](https://github.com/seedds/nxnative/blob/6a60b722e8af8daaf36f9f056485e5d21c15a887/dm/gfx/vk/hle_vk.m)
uses one serial queue, ignores semaphores/pipeline barriers, and lacks compute
pipelines and secondary command buffers. It is unsuitable as a general
MoltenVK replacement. [hle_gl.m](https://github.com/seedds/nxnative/blob/6a60b722e8af8daaf36f9f056485e5d21c15a887/dm/gfx/gl/hle_gl.m) implements a
single-context subset used by specific games, not a general NVIDIA desktop
driver. NVN interception is a different integration point from MeloNX's GPU/GAL.
The source has implementations newer than some README limitations, so inspect
the exact operation and its test. Metal4-specific algorithms also need OS/GPU
capability guards to preserve RewindBox's iOS 18 baseline.

The project [license](https://github.com/seedds/nxnative/blob/6a60b722e8af8daaf36f9f056485e5d21c15a887/LICENSE) is MIT. Retain copyright/license notices
and inspect each reused third-party component's own notices.

Next action for the implementation owner is the dynamic-gather comparison
above after the current DMA correction reaches a stable point. Reopen this
assessment for a changed pinned revision, demonstrated missing case or new
backend capability. Record each tested candidate here in place.

## Delivered baseline

Last verified delivery is private RewindBox 0.0.8 (629), iOS 18+ with SideStore.
628 was not delivered and 629 must not be reused. Source
`6aae16b9ca0683eb64aa4881dc6855b05b363763`, freeze `79d866ef`,
[manifest](../build-utils/delivery/629.json), effective product `140e5707…`.
Run `41622115556` attempt 1 completed in about 21 minutes.
RewindBox-629.ipa is 194618465 bytes, SHA-256
`952b2641a1151746e43dc81b500371911a668e5736131acf8de75542d0f2bfe6`.
[Delivery receipt](evidence/rewind629/delivery.json),
[signed identity](evidence/rewind629/signed-payload-identity.json) and
[download verification](evidence/rewind629/download629-verification.json)
bind the product. Its private recipient key was deleted.

| Component | Delivered identity |
| --- | --- |
| MeloNX | Core 628, run `41614833262`, source `1ce1cd14`, packaged `dfd9061e…`, iPhone library `1699cf38…`. Reviewed deltas `e34dccf9`, `1ce1cd14`, `2620d011`. No iPhone result. [measurement record](melonx-624-measurement-2026-11-03.md) |
| RPCS3 | Core 627, run `41610162888`, source `6891f9a0`, payload `eccf8535…`, pin `021a15e4`. Reviewed `40c6502a`..`8e68bdee`, `2abb1ac2`. No iPhone result. [Core record](rpcs3-core627-2026-11-03.md) |
| Dolphin / ARMSX2 | Kept from 608, payloads `640e4389…` / `fab55193…`, ARMSX2 ABI 9, archive republished by run `41504526945` |
| libretro and dependencies | Retained through the same authenticated archive chain, last republished by `41622115556`. libretro_internal_bridge bytes changed from 626 despite unchanged effective sources, recorded as a nonblocking undeclared image change. |

629 attempt `41618683768` failed at the Core-install canary name check.
Recipe fix `79d866ef` accepts the Core-specific canary. Do not repeat the
fixed marker list from Cores 587–624. Earlier delivery details remain in the
existing receipts and history linked above.

## Prior reservations and results

These identify earlier work, not current instructions to resume it.

| Prior entry | Recorded outcome and retained evidence |
| --- | --- |
| TASK-586 / TASK-587 | The old board claimed 586 was pending while later receipts exist. Use [586 delivery](evidence/rewind586-delivery.json) and [587 receipt](evidence/rewind587-delivery.json) when the exact earlier product matters. Core 587 run `40718679248`, source `a8a7ce10`, Mac proof `7c3c48d2`. Do not dispatch the old recipe from that stale row. |
| TASK-589 | Core 589 run `40778765122`, source `99a57a6`, binding `700db785`. [Core record](rpcs3-cell589.md) retains the exact source, profile and receipts. No active instruction to produce a separate 589 IPA. |
| TASK-628-RPCS3 | Core 627 was pinned and delivered in 629 instead. References are in the delivered baseline above. Pending device checks remain pending. |
| TASK-630-RPCS3 | Core 630 compiled in run `41646604720` on `e1cd9621`. [Core 630 record](rpcs3-core630-2026-11-03.md) retains both artifact identities. Core 634 includes this work and is the current integration target. |
| Former 583 handoff | Its 28 October snapshot is superseded as a handoff. [583 source/results](rpcs3-cell583.md) and [delivery](evidence/rpcs3-cell583-delivery.json) preserve it. Host steady-state comparison was noisy, so no FPS gain was established. The 583 driver repeated OPT583 instead of OPT581, compensated by Mac/IPA evidence at that time. Follow later source/receipts before reopening the old Write Color Buffers or async-submit proposals. |
