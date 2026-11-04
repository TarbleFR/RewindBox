# RewindBox — shared requirements and results

Sole working contract for Claude Code, Codex and Cursor. Updated 4 November 2026.
Read **Shared working rules**, your routing section and only your active task;
then open its direct evidence. Do not load the full history for routine work.

This page holds current instructions and one current record per task.
Detailed measurements, failures, receipts and input identities remain in their
component files and the [complete pre-consolidation record](https://github.com/TarbleFR/RewindBox/blob/17b2978093d386465def7e87d640cf4e4cb0efc9/docs/AI_TASK_BOARD.md).
That immutable record is evidence, not an instruction to resume old work.
A recorded run status is a snapshot: inspect the actual run before taking action.

## Shared working rules

1. **Scope and ownership.** Follow the maintainer's current request and standing
   authorization. Claude Code owns substantive implementation; main session
   `012mUAShv9k6pSCnpW7oAF63` owns integration, Core producers, pins, CI, freeze
   and private delivery. Codex coordinates/reviews or makes explicitly delegated
   changes. Keep each component with its existing owner. No new feature, worker,
   duplicate diagnosis or concurrent workflow merely to obtain another green badge.
2. **PRIORITY / STRICT: constraints must lead to improvement work.** For every
   in-scope performance, stability, rendering, audio or input constraint, pursue a
   concrete modification, executed before/after verification and reviewed handoff.
   "GPU-bound", "first-use compilation" or "real constraint" alone never closes it.
   Record symptom, source, lever, change, executed check and outcome. A failed
   hypothesis requires a materially different evidenced approach. A diagnostic or
   unexecuted test is an intermediate step. Keep actionable work open; a genuinely
   unavailable device/access dependency or demonstrated irreducible limit needs
   evidence and a precise next action. Continue independent improvements. Never
   invent a patch/gain or weaken rendering, synchronization, data or tests.
3. **Finish authorized work autonomously.** Do not stop at diagnosis/draft PR or
   repeatedly request general approval for approved corrections, reviews, builds
   and private delivery. Resolve missing technical evidence with existing logs,
   source and a bounded executable check. Ask only for a necessary new decision,
   access or physical-device observation that the environment cannot provide.
   Respect actual platform/tool refusals; never route around them.
4. **One writer and preserved history.** Inspect actual branch, HEAD, remote and
   dirty paths before writing. Work on `Claude` for integration and an owned task
   branch for component changes; preserve `main`, `backup`, tags and baseline refs.
   Preserve concurrent/local-only work. No force-push, reset, clean or silent
   conflict resolution. Main alone integrates component changes.
5. **Safe follow-up branches.** Fetch/compare exact ancestry and intended diff.
   After a task branch was squashed/integrated or its PR closed, create a fresh
   named branch from current `Claude`, retain dirty/unpushed work and replay only
   the owned delta; ordinary push and a new PR. Reuse an active branch only when
   its remote head is an ancestor and the diff is correct. No forced branch reuse
   or synthetic `ours` merge to bypass a refusal. Separate commit and push steps.
   At integration carry the product delta AND reconcile its current evidence row.
6. **Update, do not append a diary.** After meaningful results and before ending,
   compaction or handoff, replace your current task record with owner, input/source,
   finding/change, decisive proof, validation state, limitation and next action.
   Distinguish dirty/local/published/tested/compiled/delivered/device-observed.
   Link detailed receipts instead of pasting journals or all previous attempts.
   Preserve negative results and private input hashes in their evidence location.
   Fetch the latest board and edit only the relevant section; never push an old
   branch's whole board over newer records. Correct permanent rules in place.
7. **Included services only.** Use official subscription sign-ins. No paid APIs,
   outside agent launchers, quota polling, subscription/billing changes or auto-top-up.
   Claude/ChatGPT/Cursor allowances are separate; a quota limit does not transfer
   code ownership or chat history. Public publication and unrelated destruction
   need their own authorization. This contract is not an automatic scheduler.
8. **Communication.** Report concise outcomes in French. Notify meaningful results,
   required attempt outcomes and real blockers; avoid repetitive progress messages
   or requests for logs already published. A completed label alone is not proof.

**Misaddressed private attachments.** Main owns routing: identify source session,
destination owner and exact input batch, then use native attachment/file-sharing
when available or the authorized Codex browser coordinator to download/re-attach
the originals. Session text/metadata access does not prove access to attached bytes.
Verify size/SHA-256 and destination receipt; record sent/queued/received separately.
Never substitute older similarly named logs, paste raw private logs into Git, create
a new worker or leave the files silently stranded. If the originals cannot be
retrieved, name that precise access limitation and continue independent work.

## Adaptive delegation

Classify by uncertainty and highest-risk substantive work remaining, not console
name. Tiny work is direct. Prefer one coding agent total; any authorized parallel
coding must use separate branches/checkouts and disjoint owned paths. At most two
useful independent read-only reviewers; no nested teams or duplicate reviews.

| Work | Native Claude agent | Model / effort |
| --- | --- | --- |
| Exact lookup of a file, symbol or recorded result | `rb-lookup` | Haiku / low |
| Bounded source/upstream investigation | `rb-research` | Sonnet / medium |
| Understood isolated correction | `rb-code` | Sonnet / medium |
| Difficult Core/JIT/GPU/memory/ABI or native lifecycle review | `rb-core-review` | Opus / high |

Pass model AND effort explicitly when native tools support them. Supply exact base,
owned paths/diff, existing findings, one question, acceptance and stopping condition.
Workers return decisive evidence and next action, usually 200–400 words.
Use `worktree.baseRef: head`; worktrees omit uncommitted changes. Only main integrates.
If tools/agents are unavailable, keep work with the owner and report the limitation.

**Main-turn effort is a real setting.** Invoke inline `rb-effort-low`,
`rb-effort-medium` or `rb-effort-high` through native Skill before substantive work:
low = factual/status only; medium = understood bounded work; high = unresolved
Core/JIT/GPU/memory/concurrency/ABI, UIKit lifecycle, skin hit-testing/stick geometry,
orientation or difficult regression review. A status interruption does not lower the
effort needed for the code resumed afterwards. Reassess on each new user turn and
genuine phase boundary, not every command; return to medium/low once only routine
records/handoff/facts remain. Extra/Max require a named hard ambiguity and end when
it is resolved. If that exceptional level lacks a loaded selector/self-control,
report the exact limitation to the coordinator for the already-authorized native UI
adjustment. Keep the principal model stable within a task; a model switch is a
separate native operation, not a claim about reasoning.

**Verify activation in each session.** Manual Max persists as a session setting;
project `effortLevel: medium` does not clear it. A loaded skill's `effort` overrides
the session for its turn, but the skill must actually be invoked again next turn.
After config changes, sync only relevant files without overwriting dirty work and
use `/reload-skills` if needed. Record loaded selector, requested level and native
expanded `${CLAUDE_EFFORT}`; compare the displayed session setting separately.
`CLAUDE_CODE_EFFORT_LEVEL` and organization caps can prevail: inspect only relevant
non-secret effort settings on a mismatch, never weaken permissions. The UI alone
does not prove an already-running request's effort; the permissions Auto button is
not effort automation. Do not claim adaptive routing or savings without execution.

**Escalation.** Classify an exact failing run/job/assertion as changed product,
harness, baseline or infrastructure first. Correct simple causes directly. After
two equivalent inconclusive attempts, change method; for a complex native ambiguity,
escalate once to Opus/high or a useful authorized scoped review. Pass attempts and
required checks; do not repeatedly switch models or relaunch full workflows for
network/missing-artifact/baseline failures.

Configuration: `.claude/agents/`, `.claude/skills/rb-effort-*/SKILL.md`,
`.claude/settings.json`. Actual activation is session-specific:
main's high selector succeeded on 3 Nov after reload; earlier unavailable-agent
checks are historical, not a permanent ban. Skins' latest correction/pending native
verification is in the Codex task below. No blanket all-session activation claim.
Sources: [skills](https://code.claude.com/docs/en/skills),
[model/effort](https://code.claude.com/docs/en/model-config),
[subagents](https://code.claude.com/docs/en/sub-agents),
[worktrees](https://code.claude.com/docs/en/worktrees#choose-the-base-branch).

## Codex model and effort routing

Use direct work for tiny tasks. Delegate only when authorized/useful; verify current
native availability, pass both parameters with `fork_turns: none` and minimum context.

| Work | Native collaboration model | Effort |
| --- | --- | --- |
| Exact independent lookup/receipt | `gpt-6-luna` | low |
| Bounded research, understood correction/check | `gpt-6.1-sol` | medium |
| Difficult Core/GPU/JIT/memory/concurrency/ABI review | `gpt-6-astra` | high |

These are Work Mode aliases, not API IDs. Escalate once for a named ambiguity.
The app controls Codex's primary backend model/effort: never claim to have switched
them through project text. No paid API/launcher permission is implied.
The personal routing entry point points here and holds no duplicate task history.

## Standing IPA compilation authorization

The maintainer's 3 Nov authorization and 4 Nov confirmations remain in force:
main Claude may review/integrate approved deltas, run/recover affected Core/macOS CI,
package, sign/check and privately deliver the common IPA without asking again.
Its own ordinary fast-forward commits to `origin/Claude` are authorized; use
`[skip ci]` unless CI is intended. If remote advanced, reconcile only owned unpushed
commits after inspecting conflicts. Component sessions keep their own task branches.

The targeted recipe change accepting already-integrated, explicitly reviewed and
classified merges is APPROVED (`49e4f2e`). Preserve shared history, all source,
component/package/signature checks and the ban on merges after freeze.
The former decision blocker is resolved; do not ask it again.

Use the standard recipe and the last verified delivery plus declared reviewed delta.
Rebuild changed components; authenticate retained ones. Rerun affected tests and always
the delivery contract; reuse evidence only with equivalent full relevant inputs.
Preserve Release/ABI/legal/signature/payload identities and source/run/artifact/hash
bindings. Use `build-utils/delivery_contract_memo.py` where required. A host change
needs a full app build; Windows checks do not compile an iPhone IPA. Follow
[Core swaps](core-swap-delivery.md) and [delivery speed](delivery-speed.md), including
the under-40-minute target without removing checks.

After EVERY attempt (success/failure/interruption), report build/version,
source/Core identities, run/attempt, fresh/reused/failed/not-run tests, outcome,
cause/blocker and next action; retain its receipt. Follow active attempts to terminal
state and avoid duplicate dispatches. Verify the downloaded plaintext IPA, manifest,
component identities and signing receipt before delivering its usable private link,
size and SHA-256. Encrypted transport alone is not the deliverable. Keep recipient
keys out of Git; delete private keys after verified delivery. SideStore supplies
Apple provisioning. Mark unavailable file verification explicitly.
Public tags/releases/posts and new paid services are not authorized by this rule.

## Command output

Use `python3 scripts/ai-output.py run -- <command> <arguments>` for verbose
foreground checks; `file <path>` reads an existing journal. The wrapper retains full
binary output, SHA-256 and receipt; `run --log-dir <parent> -- ...` selects its parent.
It preserves child status, is non-interactive and does not interpret pipelines.
Read exit status first; keywords never prove success. Inspect the necessary full-log
range and existing analyzers if the excerpt is insufficient. Promote decisive
receipts to existing component evidence. Eleven CLI regression cases passed; wrapper
success does not establish source equivalence.

## Diagnose, correct and verify

- Read current source and existing findings before diagnosing. Reopen only for a
  changed input, contradiction or untested path; a new session is not evidence.
  Give each check one question/decision; after two equivalent inconclusive checks,
  change method. A blocked dependency does not stop independent work.
- Disposition every actionable finding: defect → correction + executed test;
  already fixed → exact change/build; hypothesis → discriminating check;
  proven unavailable observation/limit → evidence + next action. Apply the strict
  improvement rule; instrumentation is intermediate, not a completed improvement.
- Compare real controls/candidates and full transitive test dependencies.
  Classify baseline failures independently; no weakened assertion, skipped required
  test or repeated unchanged diagnosis to get a badge. A reused test must bind the
  same relevant code, dependencies, tools, config and inputs.
- Separate CPU encoding, GPU execution, queue wait, launch time and game FPS.
  Host/simulator/compile/package checks do not establish iPhone gameplay, FPS,
  audio or visual improvement. Never claim unmeasured gains.
- Use app journals; never request .ips/Jetsam/watchdog reports or block on them.
  Separate build/PID/session/game/mode, cold/warm and duplicate/rotated logs.
  Keep raw private logs, secrets and recipient keys out of Git/instructions.
- On handoff/compaction retain request, authorization, branch/HEAD, owned dirty paths,
  input identity, findings/rejected approaches, exact patch/tests, blocker and next.

## Product and delivery requirements

- Brand new text RewindBox. Preserve upstream NeoStation credits/licenses, bundle IDs,
  storage/preferences, method channels and ABI. Follow [rebranding](REBRANDING.md)
  and the relevant [component rules](PROJECT_RULES.md).
- Retired: KartPad/Mario Kart Pad, Dusklight, Ports playlist and MeloNX external
  StikDebug/Shortcut fallback. Preserve player files and historical evidence.
- Preserve library behavior, reviewed exceptions, backups, games/saves/firmware/
  keys/caches/mods/pairing and approved replacement rules; no destructive concealment,
  speculative migration, duplicate hiding or parallel library.
- Preserve canonical source/ownership/generation, cancellation, late callbacks,
  real errors and safe teardown. Verify affected first/relaunch/recovery and
  cross-engine transitions. Keep Hogwarts 1x and complete equivalent rendering;
  no hidden resolution/quality reduction, unsafe synchronization or unverified
  global workaround. The shader interpreter stays off unless separately approved.
- Preserve 12 locales: en/es/ru/zh/zh_Hant/pt/fr/de/it/id/ja/ko for changed text/help/
  errors/accessibility; check keys/placeholders/Traditional Chinese. English fallback
  does not replace translation; raw diagnostics remain separate.
- Skins: keep old packs/IDs/previews/imports/selections. New approved visual variants
  are additive; reproduce target finish/geometry in both orientations and verify
  actual overlay/input/Menu, precise contours, press/release/sticks, rotation and
  persistence. Preserve portrait-only lock, dual-layout rotation and restoration.
  Document necessary adaptations and unobserved iPhone feel/gameplay.

## Release notes and publication checklist

Main owns [releases/NEXT.md](releases/NEXT.md); component owners supply exact source,
evidence and concise user-facing English notes. Update after reviewed changes and
verified private deliveries. Distinguish planned/implemented/tested/private/public;
include fixes, features, stability/compatibility and limits without unmeasured gains.
Before public release reconcile ALL unannounced approved changes since the actual
public tag against final manifest/receipts; record any deferral/exclusion.
After an authorized PUBLIC release, archive `docs/releases/<actual-tag>.md` with
tag/build/source/publication URL, start fresh NEXT and carry unshipped/unannounced
items. A private IPA does not reset the public baseline. Provide ready-to-post English
notes and label previews. Writing notes is authorized; public posting is separate.
NEXT is communication evidence, not a second implementation queue.

## Active requirements

One record per current task below. Older task numbers (631/634/635), failed attempts,
input hashes and review details are retained in component records and the
[pre-consolidation history](https://github.com/TarbleFR/RewindBox/blob/17b2978093d386465def7e87d640cf4e4cb0efc9/docs/AI_TASK_BOARD.md#active-requirements).
Do not treat their old "next" steps, branch names or unresolved approvals as current.

### Common IPA — main Claude Code

Owner: `012mUAShv9k6pSCnpW7oAF63`. Integrate reviewed RPCS3, MeloNX, skins and all
already-approved content into one common private IPA; no omitted lot or concurrent
delivery. New work after a frozen manifest belongs to the next manifest.

**Latest recorded state:** IPA **650** frozen `f8d58ca2`, effective `b46f7f65…`;
requested run `41861290919`: RPCS3 **645**, MeloNX **649** (pin `c5f1461e…`,
fingerprint `a137ac95…`, 23 engine-evidence gates), PR **157** skins and updated
legal declaration, nine reviewed commits. This is a request/freeze record, not
terminal success. Core 651 belongs to the next IPA. Prior drafts 646/648 are superseded.

**Next:** inspect that run's actual status without duplicate dispatch; report attempt
outcome and verify/download per recipe. Review subsequent Core 651 and additive PS2
handoffs for the next common manifest. Device tests follow a verified IPA and are not
a circular requirement to package. Last verified delivery is 643 below.
### RPCS3 FPS, stability and audio — main Claude Code
Core **645** timeout-mix correction is compiled/pinned: source `eeb36c27`,
run `41839324272` on `60b388d9`, dylib `bf2141f9…`, fingerprint `a2d42107…`,
pin digest `fc1b8807…`. Source-chain/Apple checks passed, codegen unchanged;
[Core 645 record](rpcs3-core645-2026-11-04.md). IPA643 PID6665 logs were verified
from private archive `40b950da…` (1782552 B); eight original identities remain in
[the relay
record](https://github.com/TarbleFR/RewindBox/blob/17b2978093d386465def7e87d640cf4e4cb0efc9/docs/AI_TASK_BOARD.md#active-requirements),
raw files private.
**Current correction:** Core **651**, `REWINDBOX_AUDIO_LOW_RING_MIX_651`, ends
late-port waiting once a due period has fewer than two ring blocks. Host burst model
versus 645: filler 198144→0, refill silence 73216→0, recoveries 51→0; trade-off:
late-port lost blocks 1021→1247, discontinuities 839→1033. Clean and 645 cases
identical; closure/codegen/AUDIO641 admission pass; full suite was running, compile
next. This is a host result, not a measured audio gain on iPhone.
**Open performance work:** AC ≈1400 draws/51 passes, GPU 30–40 ms/frame.
Depth-feedback barriers (~8.7/frame) protect real hazards; removing them at identical
output was rejected, strict query scopes off, reset only on exhaustion, fast math on.
Census the other pass-ending sites/restarts/full-clear candidates, then correct the
dominant justified source. BO2's three 640 pipeline fingerprints do not rebuild in
643; residual first-use cost is vkCreateGraphicsPipelines (234–1008 ms), including
five new programs in one 2.77 s frame. Investigate FIFO shader-program lookahead or
correct-config MoltenVK module-library warm-up; no shader-only gain claim.
**Next:** finish/test 651, compile/pin under main ownership and retain its audio
trade-off in review; pursue AC/BO2 levers under the strict rule. Device AC same-scene
audio/34-vs-64ms buffer/lip-sync, BO2 second session and SPU-warmup A/B remain
unobserved. Historical ZCULL/GOW3 work and rejected paths: [Core 638](rpcs3-core638-2026-11-03.md),
[Core 641](rpcs3-core641-2026-11-04.md), [full
dispositions](https://github.com/TarbleFR/RewindBox/blob/17b2978093d386465def7e87d640cf4e4cb0efc9/docs/AI_TASK_BOARD.md#findings-to-carry-forward).
### MeloNX FPS, memory, black launch and artifacts — existing owner
Owner `012mUASkkFGHaPcEUx9dsp8q`; main integrates/builds/pins. Preserve Hogwarts 1x,
full rendering and ordering. Direct evidence: [optimization
map](melonx-optimization-map-2026-11-03.md)
and [621 logs/dispositions](melonx-621-measurement-2026-11-03.md).
**Integrated lineage:** 639 = 631 + PR153 warm-up parity and safe device-short trim,
including the three private 621 logs; 642 adds PR154 MoltenVK barrier/descriptor fixes
and attribution; 644 readback receivers/present attribution; 647 PR156 follow-up
teardown compile cancellation and guest-thread pause record; 649 adds teardown phase
marks (23 engine gates per latest main record), selected for 650.
Receipts: [639](evidence/melonx-639-gates/run.json),
[642](evidence/melonx-642-gates/run.json), [647](evidence/melonx-647-gates/run.json);
exact current identities come from pins/contracts, not this lineage summary.
**Keep causes distinct:** the receiver defect/signalling without data is corrected
in source, but its relation to black launch is unproved. Black launch ends after a
2–4s pause, with presented frames already recorded; presentation alone does not prove
visible image. Compare early color-mask pass splitting/load-store behavior from
Hogwarts IPA643 sessions 6451/7170/7613 (same Core); correction candidates remain
hypotheses. The 7170 black-screen confirmation/artifact timing was requested; do not
infer it. SSBU flicker is not automatically the Hogwarts-policy defect.
**Maintainer correction:** endless close occurs while recording; a recording spans
app relaunch, so the former "30.5s without recording" claim is not established.
Compile cancellation is corrected separately; vkDeviceWaitIdle/presentation stall
while recording remains a hypothesis. Occupied readback branch/first-occupant and
PrimitiveRestartEnable/Topology miss diagnostics are intermediate evidence, not
finished optimizations. Do not reopen already-corrected readback/trim/cache issues
as new defects.
**Next:** owner reads later receipts, finishes supported corrections and hands off
exact commits/tests once; main verifies integration. On a produced IPA, cold launch
without menu, launch/cutscene recording, Present-source/DMA lines and SSBU close
while recording decide remaining hypotheses. No controlled FPS/visual gain established.
### Skins/orientation and additive PS2 Original — existing owner
Owner `012mUASjgVWk8DKKjVbwTD2n`.
- **Integrated history:** PR152 `705e90c7`; PS2 playlist Skins `b8794226`; PR155 GC/Wii
  Originals `5ab7273d` (in 643); PR157 touch/pressed/stick fix in frozen 650 per main.
  Integrated branches are never reused or force-pushed.
- **Evidence:** [touch audit](evidence/pocket-originals/touch-fix/),
  [boards](evidence/pocket-originals/board-originals/),
  [pack record](pocket-originals-2026-11-03.md).

**PS2 Pocket — Original (current):** branch `work/skins-ps2-original-20261104` from
`c37b71d`, source `628a730`, draft [PR158](https://github.com/TarbleFR/RewindBox/pull/158).
- **Input:** zip `13e739fe…eac`, 1728531 B, re-hashed here. The target PNG `e37c95a5…95da`
  is copied byte for byte to `docs/design/pocket/approved-ps2.png`. IMG_0399/0400 are captures
  of the current skin, not targets, kept private.
- **Pack:** new id `ps2-pocket-original`, archive `07f4b6fb09fcf61f…6355`, 7283088 B, rebuilt
  identical. Catalog goes from 5 to 6 entries (`16a25a9d…42ac`). Built from the maquette's
  pixels with the GC/Wii method:
  - L3/R3 are bands under the caps; their press dims the letters;
  - the portrait Menu is added in landscape;
  - the landscape island gets a harmonic fill.

  GC/Wii archives and `ps2-pocket` `2106e5f7` (id, previews, selections) are unchanged.
- **Native:** `ARMSX2SkinOverlay` resolves touches by the drawn shape (`ARMSX2SkinHitTest.h`,
  the same code as `DOLSkinHitTest.h`). The ARMSX2 floating menu hides over a skin with its own
  Menu (it covered L1 in landscape on both PS2 packs).
- **Fresh host tests:**
  - verifier 6 packs; input chain 18 layouts: both headers compiled, 4352846 drawn points
    reach their own control, earlier packs equal the old rectangle test (874602 points);
  - menu-button and session-chrome tests and contracts pass;
  - Flutter 3.47.2 skin/pocket/ARMSX2 249/249 (catalog, separate install, selection,
    persistence); analyze clean;
  - fidelity: mean abs diff 1.3–1.45, PSNR 37.5–37.9 dB.
- **Simulator** (ARMSX2 suite on both PS2 archives, run `41865972707`): pending at this record,
  not claimed.
- **Evidence:** [ps2-original/](evidence/pocket-originals/ps2-original/).
- **Board-bound limits (maintainer decision):**
  - landscape L3/R3 about 26 pt tall and SELECT/START about 40 pt;
  - SELECT/START 4.3–5.0 pt into the home band;
  - opposite-rotation sensor housing over Circle.

  Portrait is ≥44 pt fitted everywhere. iPhone feel and game response are unobserved.
- **For main:** a reviewed legal overlay for the 6th pack (the source-evidence check binds 5)
  and integration into the next common IPA. No merge, IPA, pin or Core change from here.
- **Effort routing (observed):** `/reload-skills` returned 37 skills, none added or removed;
  the branch contains `b8e12584` and `20c14011`. The native `Skill rb-effort-high` return at
  the hit-test/geometry review checkpoint was "Effective effort reported by Claude Code: high".
  A second call returned "already loaded… instructions unchanged", with no new substitution.
  Environment `CLAUDE_EFFORT=high`; no `CLAUDE_CODE_EFFORT_LEVEL` override. No mismatch.
  Next level: high until the simulator result is read, then medium for the handoff and docs.
- **MeloNX log export (maintainer relay):** the 5 originals of PID7613/E3542E16 were
  re-hashed. Their sizes and SHA-256 match the relay, and the PID6451 lot was not used.
  - Private ZIP `rewindbox-melonx-logs-pid7613-20261104.zip`, 900515 B, SHA256
    `12b5f01926d2bf5f6c34a6f6ebb5165e0aa38309c5c4f6dc823661cb82562f04`: unchanged originals
    plus INPUTS.json and SHA256SUMS, not in Git.
  - Exposed as this conversation's downloadable attachment (file
    `d585ba9d-2e26-4982-9155-b1471f1850d2`).
  - A single native attach to `012mUASkkFGHaPcEUx9dsp8q` via `send_message.attachments` was
    refused: "attachments is only valid from a project's channel session to one of its thread
    sessions". Nothing was transferred; Codex re-attaches.
### Codex orchestration — Codex
Coordinate existing owners, independent evidence and concise current records; no
new worker/diagnosis/workflow while equivalent authorized work proceeds.
Verified640 delivery watch reached its stop condition; the later recording that it
was still enabled/no IPA delivered is historical. Do not recreate a watch by
misreading that record. Public-release notes remain in NEXT.
**Effort correction:** `b8e12584` adds native skin risk to high-selector description;
`20c14011` corrects per-session/phase routing. Skins UI changed Max→High for
subsequent requests, model remains Opus5.5. `/reload-skills` and one consolidated
follow-up were pending behind active PS2 work at the last observation; native
reload/Skill-return/automatic transition are NOT yet verified. Owner must report
the actual expanded effort at its safe checkpoint, not merely a prose claim.
No repeated identical prompt is needed.
**Misaddressed logs, current routing request:** five private MeloNX files were
attached to skins rather than owner `012mUASkkFGHaPcEUx9dsp8q`: Hogwarts IPA643,
PID7613, capture `E3542E16`, 14:53:42–14:55:05 UTC (distinct from older PID6451).
Source skins receipt lists core1282233B/`10f45789…32ef4`, launch141798B/
`4649b86d…32f23`, performance4280061B/`73eebbbd…0a223a`,
stderr.previous5242502B/`587cca0f…a712a`, stderr2973737B/
`cf5e647f…d4ed4a`; full original identities stay with source attachments.
The earlier session-message relay alone did not transfer these bytes.
Source attachments were located in skins message10; their UI tiles expose no
retrieval control in the observed interface. One private ZIP-export request is
queued in skins; one consolidated instruction is present in main and marked read
by Claude (routing plus the board-format change). No owner export or destination
byte receipt yet. Next: source exposes the five originals with full hashes through
native file delivery; main or the authorized browser coordinator attaches them to
MeloNX and verifies receipt. Do not resend either request or claim transfer done.
**This consolidation:** entry files already short (AGENTS708 chars, CLAUDE912);
board had 149278 characters with 27k-character task rows, duplicate chronology and obsolete
current-state claims. Current rules/statuses are consolidated; full prior content
remains at the immutable history link. No product, pins, workflows, permissions,
private input or delivery acceptance changed. Next: owners update only current
sections from fresh source/receipts and keep detail out of this page.
### Completed housekeeping — no new cleanup requested
Nine obsolete refs removed (14→5 branches at that time); PR152 closed after exact
squash comparison, Dependabot151 retained. 1069 runs deleted with audited receipts,
all initial artifacts and retained producers preserved.
[Verification](evidence/github-cleanup-2026-11-04.json).
Counts are historical, not today's inventory. No instruction to delete anything else.
## Delivered baseline
Last verified delivery is private RewindBox 0.0.8 (**643**), iOS 18+ with SideStore, delivered 4
November 2026 on the delivered 640: RPCS3 Core 641 (audio diagnostics exported, log text only),
MeloNX Core 642 (PR #154 lot), PS2 playlist Skins entry, GameCube/Wii Pocket Originals and Dolphin
session buttons off skin controls (PR #155). Trigger `f19ed8cd`, freeze `2740e79c`,
[manifest](../build-utils/delivery/643.json), effective product `e8bad150…`. Run `41772933869`
attempt 1: preflight, republish, flutter, native and application passed. RewindBox-643.ipa is
236198342 bytes, SHA-256 `eb6f88ea41889fea072672ae82cd6b11d2a97336aa0bed4974ba3e9c78872f0a`, sent
privately to the maintainer in the Claude session (file `a048d6dc-8b1f-4e62-93d2-a2c24809d0f6`).
[Delivery receipt](evidence/rewind643/delivery.json) and [download
verification](evidence/rewind643/download643-verification.json) bind it (four parts against the API
metadata, SHA256SUMS and signer receipt, 90 images, pins `eb0d0051…`/`281aa3a4…`, 44 retained, six
validators). libretro_internal_bridge changed without an effective source change (undeclared,
nonblocking, as in 629). Private recipient key deleted. Not tested on an iPhone; no FPS, audio or
visual claim. Previous: 640 (source `38c465b2`, 221255575 bytes, `c0f1d042…`),
[receipt](evidence/rewind640/delivery.json), completed with its 12 proof files in `04a4db80`.

The older component table describing Cores627/628 belonged to IPA629, not643;
use manifest643 and its authenticated receipt for actual packaged identities.
Prior640/629 failures, superseded Cores and old permission decisions remain in
[history](https://github.com/TarbleFR/RewindBox/blob/17b2978093d386465def7e87d640cf4e4cb0efc9/docs/AI_TASK_BOARD.md#delivered-baseline). Do not dispatch an old build from those entries.

## Findings to carry forward

Use linked component records and [historical findings](https://github.com/TarbleFR/RewindBox/blob/17b2978093d386465def7e87d640cf4e4cb0efc9/docs/AI_TASK_BOARD.md#findings-to-carry-forward)
only for a relevant changed input or contradiction. Retain negative results:
Core634 cache/budget defects were handled by later work; a baseline/harness failure
is not automatically a product regression. Never turn a not-run test into a pass.

**nxnative reuse study:** static at `6a60b722e8af8daaf36f9f056485e5d21c15a887`, no port,
Metal build or iPhone run. Dynamic offsets already lower legally in the Vulkan path;
no missing case demonstrated. Mixed bindless phis had no recorded failing case.
Dirty-retirement/image-atomic/texture-buffer ideas require matched backend/host
contracts, legal SPIR-V and actual capability checks; no blind shader transplant.
Its serial Metal subset is not a general MoltenVK replacement; preserve iOS18
capability guards and per-component MIT/third-party notices.
[Exact source links, rejected cases and validation triggers](https://github.com/TarbleFR/RewindBox/blob/17b2978093d386465def7e87d640cf4e4cb0efc9/docs/AI_TASK_BOARD.md#melonx-reuse-study--nxnative).
No new implementation task is created by this study.

## Update a task in place

Keep one current task section with owner/branch, required outcome, latest source
and proof, unresolved failure/limit and next action. Aim for a short summary;
move detailed tests/measurements to the existing component evidence, retaining
their identities and a direct link. Do not append repeated "next"/"in progress"
states after a terminal result or paste another session's whole task history.
Preserve exact attempt receipts, input hashes and rejected hypotheses off the
instruction path. Refresh the file before writing; reconcile concurrent changes.

## Evidence by component

| Scope | Direct references |
| --- | --- |
| Architecture and routing | Relevant section of [ARCHITECTURE.md](../ARCHITECTURE.md) |
| MeloNX measurements and rejected approaches | [optimization map](melonx-optimization-map-2026-11-03.md), [encoding](melonx-629-encoding-2026-11-03.md), [MoltenVK](melonx-moltenvk-rebuild-2026-11-03.md), `build-utils/melonx/dma-core-pin.json`, `build-utils/melonx/moltenvk-rebuild-pin.json` |
| RPCS3 | [Core 645](rpcs3-core645-2026-11-04.md), [Core 641](rpcs3-core641-2026-11-04.md), `build-utils/rpcs3/core-pin.json` |
| Delivery | [standard recipe](standard-delivery-recipe.md), [delivery speed](delivery-speed.md) |
| Library and lifecycle | Relevant section of [PROJECT_RULES.md](PROJECT_RULES.md), [library folders](library-folders-2026-10-10.md) |
| Flutter UI | [Liquid Glass](liquid-glass-ui.md), `lib/screens/systems_screen/`, affected `test/` files |
| Wii and GameCube skins | [Dolphin skins](dolphin-skins.md), [Pocket originals](pocket-originals-2026-11-03.md), [input evidence](evidence/pocket-originals/) |
| RetroAchievements and languages | [608](build608-ra-session-delivery.md), [credentials](ra-credentials-status-2026-11-01.md), [game identity](ra-game-identification-2026-11-01.md), [PS3 hooks](ra-ps3-rpcs3-2026-11-01.md), [translation](achievement-translation.md) |
| Cheats, patches, HD and rights | Relevant [component rules](PROJECT_RULES.md), [enhancements](ENHANCEMENTS.md), [licenses](LEGAL_AND_CREDITS.md) |
| Earlier findings | [existing history](history/README.md), [prior delivery notes](history/agents-delivery-notes-2026-11-03.md). Search only the implicated component/build. |
