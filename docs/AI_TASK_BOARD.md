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
- Push, tags and releases follow the task's authorization. IPA compilation
  follows the standing authorization below.
  Claude Code has standing authorization to fast-forward its own commits to
  `origin/Claude`, with `[skip ci]` unless CI was requested. If the remote
  advanced, rebase only its own unpushed commits and inspect conflicts. This
  standing push permission applies to Claude Code only. A permission refusal
  must be reported, never retried through a route intended to defeat it.
- This contract is a record of authorized work, not an automatic task scheduler.
  The explicit standing IPA authorization below applies. Other changes to this
  contract do not grant payment or public publication permission.

## Standing IPA compilation authorization

Maintainer decision, 3 November 2026. Claude Code is authorized to launch the
Core producers, GitHub Actions/macOS compilation, packaging and private IPA
delivery needed for an authorized RewindBox task without asking again. This
includes recovering failed attempts and rebuilding affected components after a
correction. Use the standard recipe, reviewed inputs, contracts, pins and signing
checks. This standing decision supersedes older prompts that ask for fresh
approval for these compilation steps. The current task determines which changes
belong in the IPA.

After EVERY IPA compilation attempt, successful, failed or interrupted, give the
maintainer a concise report with build/version, source and Core identities,
workflow run/attempt, tests fresh/reused/failed/not run, outcome, blockers and
next action. On success, verify the actual downloaded IPA and give its usable
private link, size and SHA-256. Record the result and evidence in this shared
contract before finishing or handing off. A failed job requires a failure report
even when no IPA was produced. Keep an in-progress build monitored through its
terminal state when the active task is to produce that IPA.

This authorizes compilation and private delivery within existing project
services. Public releases/tags, account/billing changes and new paid API usage
continue to require their own authorization.

## Command output

For verbose foreground tests or diagnostics, use
`python3 scripts/ai-output.py run -- <command> <arguments>`.
For an existing journal use `python3 scripts/ai-output.py file <path>`.
Each run retains the complete merged binary output, its SHA-256 and a JSON
receipt in a unique system-temporary directory. `run --log-dir <parent> -- ...`
selects an existing parent directory. The child exit status is preserved and
the terminal receives a bounded excerpt. Run mode expects a foreground,
non-interactive command and does not interpret shell pipelines.

Read the reported exit status first. Keywords or their absence never establish
test success. If an excerpt is insufficient, open the relevant range of the full
log. Use the existing MeloNX/RPCS3 analyzers for session semantics. Promote
decisive receipts into the existing evidence location when needed for lasting
proof. Record tested source, dependencies and tools in the task entry before
reusing evidence. This wrapper does not itself establish input equivalence.

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
| TASK-631-MELONX — Claude Code, session `012mUAShv9k6pSCnpW7oAF63` | Review and optimize existing MeloNX work, fix demonstrable omissions and regressions. Source `13700519`, tree `82a29e6f`, SDK 10.0.100. Validate the real prepared source, affected gates and artifact identity. The original 30–40% encoding-time reduction target is a target, not a measured result. | Source corrected and contract frozen, not compiled (3 Nov, 21:05 UTC, GitHub `04727408`). On the real preparation (132 inputs): queue fixture 28/28 and 41 source checks; region-upload buffer gap fixed in `97bfece1` (before: uploaded over a cached buffer; after: declined, counted); eleven gates passed locally on Linux, `counter-report-compaction` added because the queue changes its declared files; contract `7a15f7e5…`, contract test 268 checks. [Run record](evidence/melonx-631-gates/run.json), [component record](melonx-629-encoding-2026-11-03.md). No iPhone run. Next: Core 631 CI (`[melonx-dma-core]`, Apple ARM64), then pin with component `FRESH_GATES = 11`. Core 631 remains reserved for IPA 635. |
| TASK-634-RPCS3 — Claude Code integration | Integrate the verified Core 634 with its host changes and preserve source/artifact bindings. Includes Core 630. | Core and Apple-host jobs of run `41696834507` passed on `792d72c9`. Apple-host artifact `13261452573` downloaded in the VM: 40957 bytes, SHA-256 `c13cc47e…`, report `passed` on `792d72c9` (recorded in the [635 plan](ipa-635-plan-2026-11-03.md) 4 quater). Core artifact `13261039942` not yet verified; no pin. No iPhone run. Next: verify both artifacts with `rpcs3_core_component.pin_errors` and bundle, then write the pin. |
| TASK-635-IPA — Claude Code integration | Previously requested private 635 from delivered 629 with reviewed MeloNX 631, RPCS3 634, MoltenVK v1.4.2 and Pocket skins. Preserve the [manifest](../build-utils/delivery/635.json) and [plan](ipa-635-plan-2026-11-03.md). | Preparation, not delivery. Plan step 1 done (MeloNX contract frozen, `04727408`); `97bfece1` and `04727408` classified as reviewed in the draft. Remaining in order: Core 631 CI and pin, RPCS3 634 pin, recipient key outside Git, contract and freeze, trigger, download and verify. Next: the Core 631 CI under the existing delivery authorization. |
| Output evidence and standing IPA rule — Codex | Reduce verbose tool output while preserving complete logs and child status. Authorize Claude's necessary Core/IPA compilation with a report after every attempt. | `scripts/ai-output.py` implemented with run/file modes. Eleven CLI regression tests passed on Linux, including non-UTF-8, long lines, failure amid success noise, literal arguments, missing commands, unique runs, interruption and SIGTERM/SIGKILL status. One initial signal-flush failure and review findings were corrected before validation. Shared authorization is recorded above. Next, Claude reads this rule and uses the wrapper for verbose foreground commands, then reports each IPA attempt. |
| Shared contract — Codex owns this consolidation, then each agent owns its updates | One shared requirements/results file, automatic update obligation for all agents, no duplicated coordination documents. | Published in `c587c7c5`, five redundant files removed, 49 links verified. All three Claude skills updated to v2 and point here. Next, Claude reconciles only its task/evidence rows against its local corrections at a stable checkpoint. |

Detailed producer identities and hashes remain in the
[Core 634 record](rpcs3-core634-2026-11-03.md),
[MeloNX encoding record](melonx-629-encoding-2026-11-03.md) and pins.
No new Core or IPA is implied by a local test result.

## Findings to carry forward

| Finding and scope | Result and evidence | Reopen only when |
| --- | --- | --- |
| Independent review of Core 631 — Codex, 3 Nov 2026 | Read-only review of `97bfece1` / `04727408` / `ba02135`. No additional production omission established in the reviewed descriptor, DMA overlap and queued-syncpoint paths. The changes target measured 629 costs (compute descriptors 30.7 ms/frame, draw descriptors 7.6 ms/frame, query waits 11.8 s/90 s). The 30–40% target concerns 9.5 ms of draw encoding, not global FPS. Allocations, RAM pressure, pipeline misses and launch costs are already recorded as pending. Existing host tests establish scoped behavior, not iPhone frametime stability. No unchanged suites rerun and no additional corrective instruction sent to Claude. | A relevant source/input change, contradictory device measurement or a reproducible untested path. Continue the existing delivery/device comparison plan before claiming a gain. |
| Network prerequisites in the active VM | Resolved after environment access became Full (3 Nov, 20:30 UTC). Official SDK 10.0.100 SHA-512 verified, MeloNX `13700519`/`82a29e6f` fetched pristine, LibHac source `23e402eb` exists, archive 614 downloaded and authenticated, the 53 + 1 declared NuGet versions and the iOS NativeAOT packs return 200. The Ryulynx feed has no ryujinx.libhac (404); LibHac is built from source. File-backed in [the run record](evidence/melonx-631-gates/run.json). | A required request actually fails, the environment changes or the source/package requirement changes. Earlier 403 notes describe their recorded sessions. |
| Queued syncpoint blocking guarantees | Before `ec5e3df9`, 21/28 fixture scenarios passed. Renderer barrier, retained unpublished FIFO head and 3D increment ordering corrected. After: 28/28, 6530 checks, adapter text and real prepared source, SDK 10.0.100. Reports in [queue evidence](evidence/melonx-631-queued-syncpoints/). | Relevant queue/caller/fixture inputs change or contradictory runtime evidence appears. |
| Real-source fidelity of queue fixtures | Public IncrementSyncpoint and the texture refresh in Syncpointb differed from the reconstructed frames. Aligned in `97bfece1`; extracted regions now equal the prepared source except diagnostic `PD` lines, covered by a double. | Upstream method frames or the extracted production regions change. |
| Current 631 gate result | First pass 9/10: `hogwarts-dma-copies` failed on its own composition (queue Library line), not on production code. Freeze then showed `counter-report-compaction` had to rerun. After `97bfece1`: 11/11 on a fresh preparation, receipts valid for the frozen contract. Local Linux receipts; the Core CI reruns them on Apple ARM64. | Any adapter, gate script, plan or prepared input changes (refreeze), or the CI rerun disagrees. |
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
| Dynamic texture offsets and gather | Compare [Instructions.cs](https://github.com/seedds/nxnative/blob/6a60b722e8af8daaf36f9f056485e5d21c15a887/dm/third_party/ryujinx/src/Ryujinx.Graphics.Shader/CodeGen/Spirv/Instructions.cs). Runtime offsets are built as OpCompositeConstruct rather than invalid constant composites. Vulkan has an extra constraint below. **Claude, 3 Nov, static on the prepared `13700519`:** already handled differently. The Vulkan backend declares `supportsNonConstantTextureOffset: false` (`VulkanRenderer.cs:912`), so `TexturePass.InsertConstOffsets` rewrites every non-constant offset before code generation: coordinates shifted by offset/size for one offset, four gathers for `Offsets`. Only constant `ConstOffset`/`ConstOffsets` reach SPIR-V, legal under VUID-10213 and for MoltenVK. No port: no missing case, and no measured GPU bottleneck (629: the render thread, not the GPU, limits). | Reopen with a shader that reaches SPIR-V with a non-constant offset, a translation/validation error, or a measured gather-bound GPU window. |
| Mixed bindless-handle phis | [TryTableHandle](https://github.com/seedds/nxnative/blob/6a60b722e8af8daaf36f9f056485e5d21c15a887/dm/third_party/ryujinx/src/Ryujinx.Graphics.Shader/Translation/Optimizations/BindlessElimination.cs) selects among C2 candidates when a phi also contains other values. RewindBox already handles nested/loop phis, SHFL and proven local spills in `adapt_bindless.py` and `adapt_bindless_sources.py`; phis mixing a handle with 0 or other loads take the full-pool path (case 6), never for image stores/atomics. **Claude, 3 Nov:** no recorded unbound mixed case in the MeloNX records; not ported. | Reproduce only a remaining mixed case (journal naming an unbound phi). Prove predication and the assumption that an unmatched candidate's read result is unused. Preserve image-store/atomic restrictions and avoid marking every texture modified. |
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
