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

## Adaptive delegation

Maintainer request, 3 November 2026. Route by the task's uncertainty and risk,
not by game name alone. For a tiny edit or one exact command, work directly;
spawning an agent is optional and must replace useful work, not duplicate it.

| Work | Agent | Model / effort | Boundary |
| --- | --- | --- | --- |
| Exact file, symbol or recorded-result lookup | `rb-lookup` | Haiku / low | Read-only facts; escalate ambiguity |
| Bounded source/upstream investigation | `rb-research` | Sonnet / medium | Read-only evidence and applicability |
| Understood, isolated code correction | `rb-code` | Sonnet / medium | Explicit paths, base SHA and targeted acceptance |
| Difficult core, JIT, GPU ordering, memory or ABI review | `rb-core-review` | Opus / high | Read-only review of a specified change |

- Select BOTH model and effort for every delegated task; pass both explicitly
  to the native Agent tool when supported, including the Explore fallback.
  Do not inherit an expensive session effort accidentally.
- Select main-turn effort before substantive work through the native inline
  `rb-effort-low`, `rb-effort-medium` or `rb-effort-high` skill. These selectors
  set real `effort` frontmatter and leave the session model unchanged. Use low
  for factual/status-only turns, medium for understood bounded changes and
  high for unresolved Core/JIT/GPU/memory/concurrency/ABI work. Classify by the
  highest-risk substantive work REMAINING in the turn: a status interruption
  must not lower effort before resuming core implementation. Select again on
  the next user turn because the skill override lasts only for its current turn.
  Extra/max are exceptional escalations with a named difficulty, not defaults.
  The project fallback effort is medium; the running async core task uses high.
- The three effort selectors can be chosen automatically through Skill; their
  invocation applies a native setting, while choosing the appropriate selector
  remains Claude's task classification, not a deterministic external router.
  After first adding the skills directory, run `/reload-skills` without restarting.
  Reuse that command after edits if the new directory is not watched. Confirm
  the loaded names, invoke the high selector for the current core work and read
  its expanded `${CLAUDE_EFFORT}` value. Environment effort overrides and admin
  caps can prevail; report a mismatch without claiming automatic effort works.

- The main Claude session owns the current request, integration, shared board,
  pins, CI and IPA delivery. Default to one coding agent total, counting the
  main session. While `rb-code` writes, the coordinator does not edit its paths.
  Use at most two independent read-only workers at once. Do not create agent
  teams, nested delegations or paid external-agent/API workflows for this routing.
- Delegate one question with the exact source identity, relevant board result,
  assigned paths/diff, required output and stopping condition. Give read-only
  reviewers the exact diff text or a readable diff artifact. Reuse a prior
  finding unless its inputs changed. After two equivalent inconclusive attempts,
  name the missing evidence or change the method. Escalate a low-effort lookup
  once to research when ambiguity needs reasoning; do not repeat cheap guesses.
- Worktrees use `worktree.baseRef: head`, but do not include uncommitted changes.
  An isolated worker keeps its assigned temporary branch; only the coordinator
  integrates into `Claude`. It must not check out or move `Claude` or `main`.
  Keep dirty/core work with its current owner unless an exact reviewed snapshot
  is explicitly prepared. The coding worker verifies its base before writing.
  Review the returned diff and checks before integration; never auto-merge.
- Failure escalation (maintainer, 4 Nov 2026): classify each failing check from
  its exact run/job/log before retrying: changed production code, changed test
  harness, existing baseline failure, or infrastructure/dependency. A red check
  alone does not justify a stronger model. Fix a demonstrated simple defect
  directly; preserve tests and never weaken acceptance to make CI green.
  After two targeted attempts at the same unresolved code/harness cause, or
  immediately for a demonstrated complex UIKit/orientation/input-lifecycle
  ambiguity, stop equivalent retries, change the method and escalate once to
  Opus / high. Use one scoped native read-only review with explicit model AND
  effort if useful; keep one writer. Pass exact diff, run/job, failed assertions,
  attempted fixes and required tests, then verify the correction. A network,
  missing artifact or pre-existing failure needs its own remedy/attribution,
  not blind model escalation or full-workflow relaunch.
  A targeted principal-model change for this failure review is authorized at a
  stable checkpoint; do not oscillate models on each command. A skill or text
  instruction is not a principal-model switch. If the session lacks a native
  self-switch, use the scoped native reviewer and report that limitation; never
  claim the principal changed without an observed control/runtime result.
  Record chosen/observed model and effort, cause, result and next action here.
- Keep the coordinator's model stable during a task to preserve prompt caching.
  Sonnet/medium is the starting recommendation for future routine sessions;
  Opus/high fits difficult core reasoning. Preserve the running core session's
  chosen model. `xhigh`/`max` require a concrete difficulty and useful result,
  not routine use. Per-agent frontmatter selects workers; do not model-switch
  the main conversation via skills on every request.
- Check the actual loaded agent, model and effort on first use. Organization or
  environment overrides can win. A missing agent/tool/model or wrong base falls
  back to the coordinator; report the limitation rather than claim a cheaper
  delegation happened. Do not restart an active build/session just to reload
  agents. Ordinary cloud sessions load repo agents; Project threads may not.
- Each worker returns decisive references, result, validation status and next
  action, usually within 200–400 words. Read-only workers hand board-ready results
  to the coordinator, who records them here once. Use `scripts/ai-output.py`
  for verbose foreground checks. No duplicate handoff or requirements files.
  `maxTurns` bounds a run, not its token spend; do not automatically resume loops.
- Activation check, 3 Nov 22:05 UTC, Claude session `012mUAShv9k6pSCnpW7oAF63` (Claude Code 2.1.317, synced to
  `b99d61a1`): one `rb-lookup` call requested with model haiku, effort low returned "Agent type 'rb-lookup' not
  found"; this running session lists only its built-in agents (claude, claude-code-guide, Explore,
  general-purpose, Plan, statusline-setup, web-fetch). Observed type, model and effort: none, the call did not run.
  Routing is not active in this session; the coordinator keeps the work. Recheck in a new session.
  Native fallback, same session, 22:00 UTC: one read-only `Explore` call requested with model haiku, effort low
  (both parameters are exposed by the Agent tool) answered correctly (`docs/AI_TASK_BOARD.md`, CLAUDE.md line 3).
  Observed: type Explore; model self-reported as Haiku 5.5 from its environment, not independently verified;
  effort not observable. `rb-*` stay prepared, not loaded here. Requests can be typed normally.
  Effort selectors, 22:25 UTC, synced to `15377399`: `Skill rb-effort-high` returned "Unknown skill" (the skills
  folder arrived after session start; `/reload-skills` is needed). No `${CLAUDE_EFFORT}` expansion observed. Session
  environment, non-secret: `CLAUDE_EFFORT=high`, `MAX_THINKING_TOKENS=31999`; no project or user setting overrides effort.
  Subagents share the plan quota. Savings are an objective, not a measured claim.

Configuration: four short native definitions under `.claude/agents/` and only
the worktree base and fallback effort in `.claude/settings.json`; local settings, hooks, worktrees
and credentials stay ignored. No permissions or paid features are enabled.
Runtime preflight in the current Claude session: 2.1.317, both settings files
absent before this change; UI offers Haiku/Sonnet/Opus 5.5. Static validation
passes; loading and a bounded runtime lookup must still be verified in Claude.
These checks establish configuration behavior, not token savings.
Main-turn effort correction, 3 Nov: three effort-only native selectors added;
static schema/visibility checks passed. Codex executed /reload-skills in the
existing Claude UI: 37 available, 3 added. Claude then selected rb-effort-high
for the remaining async core work; the native Skill call succeeded and expanded
${CLAUDE_EFFORT} to high. The UI is High (previously Extra), model Opus unchanged.
Low/medium selectors are schema-validated, not separately run during core work.
Selection is task-based model judgment; no deterministic-router or savings claim.
The async-before-IPA priority remains unchanged.

Sources: [subagents](https://code.claude.com/docs/en/sub-agents),
[cloud compatibility](https://code.claude.com/docs/en/claude-code-on-the-web),
[worktree base](https://code.claude.com/docs/en/worktrees#choose-the-base-branch),
[prompt caching](https://code.claude.com/docs/en/prompt-caching#switching-models).

## Codex model and effort routing

Maintainer request, 3 November 2026: apply the same bounded orchestration to
Codex, selecting BOTH delegated model and native reasoning effort.

| Work | Native collaboration model | Effort |
| --- | --- | --- |
| Tiny direct edit or exact command | Main agent directly; no mandatory worker | App-managed setting |
| Independent exact lookup or receipt extraction | `gpt-6-luna` | `low` |
| Bounded source research, understood code or targeted verification | `gpt-6.1-sol` | `medium` |
| Difficult Core/JIT/GPU ordering, memory, concurrency or ABI review | `gpt-6-astra` | `high` |

These are Work Mode collaboration aliases, not API model IDs. Verify the currently
advertised models and efforts before spawning. Set both parameters explicitly;
use `fork_turns: none` with overrides and pass minimum task-local context.
Escalate once for a named ambiguity or changed evidence; do not use maximum
effort or multiple reviewers by default. Use the shared ownership, evidence,
output and stopping rules above. A user-authorized parallel coding task has its
own branch/checkout and disjoint paths; one writer owns each path.

Codex cannot change this conversation's primary backend model or native effort
through these tools. The application controls them. Adapt work/explanation depth,
but do not claim a primary-model switch, a native main-effort change or measured
token savings. No API billing, outside agent launcher or subscription changes
are authorized by this routing. If native delegation is unavailable, work directly.

The personal routing instructions are a thin entry point to this shared contract,
not another requirements/history file. Codex must update its owned result here
after meaningful work and before handoff, just as Claude updates its own rows.

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
   For every actionable log finding, record a disposition: a confirmed defect
   gets a scoped correction and verification; an already-fixed case names its
   change/build; an unproven hypothesis gets one decision-making check; a real
   constraint or missing input is explained. Do not repeat an unresolved finding
   without a next action or invent a patch unsupported by evidence.
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
| TASK-631-MELONX — Claude Code, session `012mUAShv9k6pSCnpW7oAF63` | Review and optimize existing MeloNX work, fix demonstrable omissions and regressions. Source `13700519`, tree `82a29e6f`, SDK 10.0.100. Validate the real prepared source, affected gates and artifact identity. Player-facing goal: higher game FPS and fewer long frames on iPhone. The 30–40% draw-encoding target is a separate CPU metric. Compare 629 and the build carrying 631 on the same Hogwarts save, device, 1x settings and comparable thermal state. Separate cold and repeated warm passes. Record median game FPS, p95/p99 frame time, stalls over 100 ms per minute, crashes and rendering regressions. Correlate remaining stalls with allocation rate/GC pauses, memory footprint/available memory, pipeline builds and warm-up misses. Label improvements only after device evidence. | Compiled and pinned, not delivered (3 Nov, GitHub `9ca1a8b1`). Contract `7a15f7e5…` frozen at `04727408`, source `523ad922`. Run `41720730870` on Apple ARM64: attempt 1 failed in infrastructure (`xcrun simctl bootstatus` over 300 s, no gate reached), attempt 2 passed the eleven fresh gates; job `126226812312`, artifact `13274787426` (90225090 bytes, `4d483a46…`), iPhone engine `7f56c460…` (37913824 bytes), packaged fingerprint `b930d1c2…`; `engine_evidence` verified offline, component `FRESH_GATES = 11`. [Run record](evidence/melonx-631-gates/run.json). No iPhone run, no FPS claim. Next: carry the 631 pin into the next private IPA manifest (`pinSha256` to update). |
| TASK-634-RPCS3 — Claude Code integration | Integrate the verified Core 634 with its host changes and preserve source/artifact bindings. Includes Core 630. | Pinned (`ffd5b62d`), superseded as delivery target by Core 636 (below). Run `41696834507` on `792d72c9`: Core artifact `13261039942` (29324314 bytes, `3c82cd8d…`), Apple-host `13261452573` (40957 bytes, `c13cc47e…`); `pin_errors` none, `bundle` passed (ABI 30, 92 exports, codegen unchanged, 15 host commands). Audit (`e69ac22a`) defects reproduced on 634 by `test/rpcs3_core636_test.py` negative witnesses. No iPhone run. |
| TASK-635-IPA / next private IPA — Claude Code integration | Latest maintainer direction, 3 Nov: let ALL current coordinated work finish, then integrate the reviewed RPCS3 FPS/stability changes, MeloNX post-631 FPS/memory work, skin/orientation corrections (now including the explicitly approved PS2 Pocket black-matte skin and GC/Wii/PS2 control/Menu verification) and already-approved delivery contents into ONE new private IPA. Main session `012mUAShv9k6pSCnpW7oAF63` owns final review/integration, affected Core producers/pins, final manifest and private delivery; authorization includes this integration and compilation without asking again. Wait for the MeloNX and skin handoffs before freezing/packaging the final IPA. Preserve already-running builds; reuse their artifacts only if their effective inputs still match. Source completion and required build/test gates precede delivery; iPhone FPS/visual measurements follow the produced test IPA and are not a circular pre-delivery requirement. | All-work delivery hold recorded by Codex and sent to all three existing sessions. Main Claude explicitly acknowledged: finish RPCS3, do not freeze 637, wait for the MeloNX and skin handoffs, review/integrate them and compile one private IPA containing all. A bounded hourly condition watch is enabled to follow readiness/delivery without repeated diagnostics or duplicate builds and stops after verified delivery or a decision-blocking interruption. RPCS3 source/Apple-harness work is active; MeloNX session `012mUASkkFGHaPcEUx9dsp8q` is active on `work/melonx-fps-stability-20261103`; skins session `012mUASjgVWk8DKKjVbwTD2n` has draft PR #152. No new combined IPA has been compiled. The former 635 and current 637 manifests are drafts: choose a final number above all actual Core/build identities once sources settle. Next: workers finish their bounded tasks, report exact commits/PR/tests/limitations in this shared contract, then main reviews and integrates them, fixes demonstrated integration failures, builds affected Cores, verifies pins/contracts and compiles the combined IPA. Report every IPA attempt; on success verify the downloaded IPA and provide private link, size, SHA-256, included changes and unmeasured items. Do not silently omit a requested chantier or substitute an earlier Core after failure. Codex watch, 3 Nov 23:29 UTC: Core 638 run `41737262282` has both required jobs completed/success (Apple harness `126269535214`, iPhone Core `126269535708`); this is not an IPA delivery. MeloNX draft [PR #153](https://github.com/TarbleFR/RewindBox/pull/153) at `92da0eb6220da6092b48793d59b602ff1d672f62` has a passing [host parity/cache receipt](evidence/melonx-pipeline-warmup-parity/checks.json) on its branch, but its adapter remains unwired and Apple/Core integration belongs to main. Skin draft PR #152 advanced to `f11e9a3c4b92f476aef114891a4648c2af9d5735`: PS2 ARMSX2 implementation and host checks are recorded on that branch; required ARMSX2/Dolphin Apple compilation/UI evidence is still absent from its handoff. All three final remises are therefore not ready; preserve the hold. No duplicate worker, session message, merge, pin edit or build dispatch. Next watch reads the existing owners' receipts; no user decision currently required. |
| RPCS3/MoltenVK async before next IPA — Claude Code implementation, Codex coordination | Explicit maintainer priority, 3 Nov: start and integrate the relevant async work before the next private IPA. Reuse existing ZCULL/report and asynchronous-submit paths; correct demonstrated artificial waits, missing activation or ordering/lifetime defects per AC/GOW3/BO2. Preserve complete rendering, exact report dependencies and safe resource retirement. Source changes, targeted dependency/fallback tests, successful Apple/iPhone build and exact Core pin are required before delivery. Device FPS/1% low/p99 and visual comparison follow on the produced test IPA; unavailable device results must be labelled, not invented or made a circular pre-delivery requirement. | Core 636 compiled (3 Nov): run `41730169021` Core job `126245102526` passed, artifact `13278257973` (29323965 bytes, `77d76bc7…`), dylib 77739176 bytes `a2f8b2cc…`, identity `rpcs3-ios-core636`, ABI 30, 92 exports, PPU `a987639e9f838d1c` / SPU `477a3fa442d27917`, fingerprint `66bd9877…`. Apple host job of that run failed on one decision check: the slot-wake model compared a measured 636 wait (807 µs) with an ideal, unmeasured 634 sleep (209 µs). Fixed in `31a7651c` (both forms measured from the release instant; Linux 634 159-166 µs → 636 42-46 µs median, host only); full local suite passes. Apple rerun `41733834801` (`2a62ce08`) attempt 1: slot wake passed; the historical Core 630 wait-budget scenario (ASan, reverted tree, code unchanged by 636; passed in `41730169021`) failed on timing (`test/rpcs3_core621_zcull.py:107`), attempt 2 job `126260668235` passed (artifact `13279365164`, 41750 bytes, `92ef9af2…`): Core 636 compiled and host-verified, not pinned because Core 638 supersedes it (artifacts kept to 3 Dec as fallback). [Record](rpcs3-core636-2026-11-03.md). **Log dispositions (actionable-finding rule).** AC 4.4 s/5 s guest waits, 3.6 services per read (Build 629, Core 627): already corrected by Core 630 per-slot reads, contained in 634/636; iPhone validation pending (`ZCULLDEMAND619` stale/waits/services, `ZCULLWAIT616 sync`). AC pause after slot release: corrected by Core 636 slot wake, Apple confirmation pending. AC ~25 submissions/frame: each remaining pending-slot read submits only the command buffer holding its deciding query; required for exact results, no compatible reduction demonstrated, read `services` on 636. BO2 22 blocking pipeline builds (8.4 s): insufficient data; pipeline key normalized, no volatile field found, VkPipelineCache wired; missing Build 629 session 1 `SHADERPIPE543` new_fragment/new_vertex/state_only/repeated_builds and `PRESSURE547`, plus a second session on the same install. BO2 per-frame newest-report read (11-13 ms): real dependency; only conservative reports avoid it and they change values: limit. GOW3 `READBACK555 fault_read` 132 × 3.69 MB, 554 ms/window, 16-30 submits/frame: WCB required (not disabled); these sections were not pre-copied by the upstream speculative readback (only unsynchronized sections are counted); missing: speculative copies/mispredictions per window and the GPU-wait vs copy split of `fault_read`. GOW3 GPU 34-37 %: source line not traced in the docs. Async Recompiler and an unproven second texture queue stay excluded. Pre-existing failure, not caused here: `test/neo_swap_core_pin_test.py` on clean `HEAD`. **Core 638 pinned** (`01562c63`, pin digest `725ef06e…`): run `41737262282` attempt 1 on `5a6d2485`, Core job `126269535708`, artifact `13279848360` (29325101 bytes, `1bbdcbd3…`), Apple host job `126269535214` (15 commands, artifact `13279912187`); `pin_errors` none, `bundle` passed: `rpcs3-ios-core638`, ABI 30, 92 exports, PPU `a987639e9f838d1c` / SPU `477a3fa442d27917`, canonical `b6d87995`, fingerprint `c35b792e…`, marker `COREPROF READPREDICT638`. Core 638 = Core 636 + GOW3 decision instrumentation only ([record](rpcs3-core638-2026-11-03.md)). RPCS3 is ready for the combined IPA; no iPhone result. |
| Skin orientation — Claude Code, separate session `012mUASjgVWk8DKKjVbwTD2n` |Applied portrait-only playable skin locks the game to portrait from launch; a dual-layout skin preserves ordinary iPhone rotation. Release the restriction when returning to dual/default and on stop/failure. Preserve per-game/console inheritance, menu transitions and existing engine exceptions. **Maintainer extension (3 Nov):** add the approved PS2 Pocket black-matte reference as a real portrait/landscape ARMSX2 skin; all visible controls must be bound and pressable, including both sticks and L3/R3, and a visible RewindBox Menu in both orientations. Audit the effective GC/Wii Pocket controls and menu too, including release/cancel/multitouch, safe hit targets and menu/resume/return-to-library. Preserve orientation selection rules and existing player data. | Codex pre-handoff verification, 3 Nov, main `138ede92`, skin PR #152 `11ef6572`: PS2 reference omits landscape Menu; older Wii concept does too; GC concept shows it. Actual GC/Wii generator already includes Menu in all eight layouts (including both landscape variants); [asset receipt](evidence/pocket-originals/asset-checks.json) passes with exact catalog archive digests, but device/gameplay flags are false. The native Dolphin path canonicalizes Menu and calls `menuHandler`; no live touch verified. [Pack record](pocket-originals-2026-11-03.md), `tools/skins/build_pocket_skins.py` and `verify_pocket_skins.py` are the direct evidence. New PS2 reference image attached and concrete task sent to existing skin session `012mUASjgVWk8DKKjVbwTD2n`, now named `02 — RewindBox — Skins : portrait, paysage et rotation`; it has resumed. PS2 catalog art alone is insufficient: verify/implement the actual ARMSX2 host skin/input route, or name the exact integration blocker, without touching Cores or pins. Orientation code/tests/handoff remain in PR #152; Apple Dolphin compilation/presentation still needs the required checks. Next: skin owner updates its existing task/PR with PS2 and controls/menu results and exact tests; main owner reviews/integrates this expanded handoff before the one combined IPA. No autonomous merge/build from Codex or skin delivery. **Failure-escalation coordination, 4 Nov (Codex):** PR #152 head `b349d640`; run `41738688166`, job `126274382721` confirms Libretro/Dolphin/ARMSX2 iPhone compilation passed, with failures in frontend fixtures, pip setup and simulator harnesses (not a delivered IPA regression). Skin owner corrected test-loop syntax, uses a Python venv and a separate Dolphin orientation harness; latest run `41740697730` is in progress, preserve it. Codex changed this existing session's visible selector from Sonnet 5.5 / medium to Opus 5.5 / high for one bounded native/UI validation review; future failure routing follows the rule above. Relay sent to the existing skin session; it invoked the high-effort selector, reported `session_context` model `claude-opus-5-5` / effort `high` (last-served model still Sonnet for its preceding turn), read commit `14421bbc` and resumed the existing run. This confirms configuration/receipt, not a guarantee of corrected simulator behavior. Required simulator touch/orientation/menu results remain pending. No Core/pin/integration/build ownership transfer. |
| MeloNX FPS/stability after 631 — Claude Code, separate session `012mUASkkFGHaPcEUx9dsp8q`; Codex coordination | Maintainer explicitly requested a parallel MeloNX discussion, 3 Nov. Turn actionable log findings into scoped corrections with evidence; prioritize remaining allocation/GC/RAM, pipeline misses and proven artificial waits. Preserve Hogwarts 1x, complete rendering and resource ordering. Reuse 631 results; no unsupported phone FPS claim. | Native `rb-effort-high` invoked (expanded effort `high`) for both turns. Branch `work/melonx-fps-stability-20261103`, draft [PR #153](https://github.com/TarbleFR/RewindBox/pull/153) to `Claude`, merged with `Claude` `dc833b7` (no rebase or force-push), not wired into a Core. Inputs: MeloNX `13700519` prepared by this branch's `prepare_embedded.py` (Core 631 preparation; touched members equal the frozen `dma-core-contract.json`), SDK 10.0.100, Linux x86_64. **Lot 1, pipeline warm-up parity** (`77dd706`, `92da0eb`): the warm-up key lacked alpha to coverage/alpha to one, so such programs miss their warm-up and compile again on the render thread. `adapt_pipeline_warmup_parity.py` (7 files) fixes it with the disk cache bytes unchanged and names the differing fields on the once-per-program miss. Proof `test/melonx_pipeline_warmup_parity_test.py`, control 631 vs candidate, production Vulkan and GPU assemblies ([receipt](evidence/melonx-pipeline-warmup-parity/checks.json)); 629 findings classified in the [map](melonx-optimization-map-2026-11-03.md). **Lot 2, the second player's 621 logs** (input identities verified at reception: stderr 584009 / `61cbc6f2…`, core 189386 / `f3c9f52c…`, performance 1049984 / `d9644d20…`; sessions A `12AAAE01` PID 57222, B `2F562F0F` PID 63461, C PID 67481 firmware stage only; raw logs not in Git). Dispositions in [621 record](melonx-621-measurement-2026-11-03.md): read-back flushes, already corrected in 623/625/628; device-short trims, a defect, corrected; late-B GC pauses of 8.7-25.2 s per window with CPU 29-75 % and the device at 4-7 %, a symptom whose cause needs a named missing datum (per-GC suspension vs work, process compressed/page-in memory); about 4 GiB of footprint unattributed (MoltenVK pipeline caches 569-768 MiB main are the largest identified, not changed blind); pipeline builds are startup warm-up and new states, with no miss lines; one-time shader-cache reload errors; syncpoint waits over 1 s inside the stall. Correction `adapt_device_short_trim.py` (3 files): while only the device is short and the process keeps at least 768 MiB of headroom, the texture trim evicts only textures the cache alone holds without GPU-written data (no flush, real release), and reports kept bytes. Own-process pressure, targets, floor, intervals and buffers are unchanged. 621 B: 68 trims and 2008 MiB "released" in 13 min, texture flushes up to 120-301 ms per trim window, no relief. Proof `test/melonx_device_short_trim_test.py` (production `AutoDeleteCache` + `Texture` reference members, doubles for storage; delivered trim identical in control and candidate; [receipt](evidence/melonx-device-short-trim/checks.json)); candidate GPU assembly compiles. No iPhone result, no FPS claim. Next (integrator, main session): review PR #153; in the next Core plan wire both adapters after `adapt_host_qos_pipeline_budget`, rerun both tests and the gates declaring the touched files, Core CI on Apple ARM64; device: miss lines and named fields, trim lines with kept bytes, texture flush time, pauses over 100 ms and GC pause per window. |
| Codex orchestration — Codex | Select suitable native worker model and reasoning effort, avoid duplicated diagnostics and preserve one shared contract. | Routing table recorded here. Thin personal entry point installed and its persisted active path verified. Schema validation passed. A native gpt-6-luna / low forward check read the real contract and correctly selected lookup low, bounded research/code medium and difficult GPU review high; no code or CI was launched. Primary model/effort remain application-controlled. No measured token-saving claim. |
| Output evidence and standing IPA rule — Codex | Reduce verbose tool output while preserving complete logs and child status. Authorize Claude's necessary Core/IPA compilation with a report after every attempt. | `scripts/ai-output.py` implemented with run/file modes. Eleven CLI regression tests passed on Linux, including non-UTF-8, long lines, failure amid success noise, literal arguments, missing commands, unique runs, interruption and SIGTERM/SIGKILL status. One initial signal-flush failure and review findings were corrected before validation. Shared authorization is recorded above. Next, Claude reads this rule and uses the wrapper for verbose foreground commands, then reports each IPA attempt. |
| Shared contract — Codex owns this consolidation, then each agent owns its updates | One shared requirements/results file, automatic update obligation for all agents, no duplicated coordination documents. | Published in `c587c7c5`, five redundant files removed, 49 links verified. All three Claude skills updated to v2 and point here. Next, Claude reconciles only its task/evidence rows against its local corrections at a stable checkpoint. |

Detailed producer identities and hashes remain in the
[Core 634 record](rpcs3-core634-2026-11-03.md),
[MeloNX encoding record](melonx-629-encoding-2026-11-03.md) and pins.
No new Core or IPA is implied by a local test result.

## Findings to carry forward

| Finding and scope | Result and evidence | Reopen only when |
| --- | --- | --- |
| RPCS3 asynchronous adaptation — Codex, 3 Nov | Feasible through existing per-title paths. `core630-from-627.patch` (included in 634) services pending ZCULL reports by their 16-byte slot while the RSX continues. The 629 AC reference shows 4.4 s/5 s of guest waits, so reducing artificial whole-page/serial waits is well targeted. BO2 may still need its most recent GPU result (11–13 ms), an actual dependency. MoltenVK asynchronous submits already exist with ordering and boot-canary guards. In `rpcs3_game_profile_service.dart`, texture streaming is disabled for AC/GOW3 because it introduces a second transfer/compute queue with separate lifetime/synchronization concerns. Async Recompiler omits draws until ready and conflicts with the preserved full-rendering requirement. | First fix the audited Darwin X29/X30 fault-access case on the successor source. Then compare existing async on/off on matched, warmed heavy gameplay with current metrics: effective policy/canary, game FPS, 1% low/p99, report wait/service time, submissions and visual correctness. Reuse current caches/prewarm. Expand the async implementation only for a reproduced independent wait or safe ownership/synchronization contract; preserve required report and resource ordering. |
| RPCS3 634 independent audit, 3 Nov — Codex | **Stability, inherited from 630.** In [the fault handler](../build-utils/rpcs3/core630-from-627.patch), a legal ARM64 load with X29 as its base reaches `GPR(context,29)`. Darwin's `__x[29]` contains X0–X28. X29 and X30 are separate FP/LR fields. A host bounds-sanitized reproduction with Darwin field layout fails on `LDR X8,[X29]` (0xf94003a8). The [non-Darwin fixture](../test/rpcs3_core630/guest_access_test.cpp) uses 32 slots. No observed device crash attributed to this case. | Fix/test before accepting this path on iPhone. Guard scalar/pair base, index and data operands before access, using platform-correct accessors or the existing fallback. Recheck with a Darwin-shaped fixture and Apple ARM64. |
| RPCS3 634 SPIR-V disk cap | The [writer](../build-utils/rpcs3/core634-from-630.patch) removes pending bytes from its accounting before writing completes. Deterministic Linux repro on production header blob `b1e4b09e964f85b0bdceef1d64714bba888c95bb`: start 1024 bytes below the 256 MiB cap, accept 840 bytes, pause flush at write, accept 840 more and reopen after both flushes. Both entries readable, file 268436112 bytes, cap 268435456. | Reserve the in-flight batch and header, or recheck the physical limit before writing. Combine concurrent add/flush with near-capacity input in the existing store test. This reproduces disk growth, not a frame-rate regression. |
| RPCS3 634 PPU cache probe | The serial check could stop at the first missing module. The parallel probe now issues the remaining checks despite a known miss and lacks a stop check during that batch. The [current fixture](../test/rpcs3_core634/jit_load_test.cpp) expects all 100 calls again even when one object is absent. | Test fully warm, partial/missing and cancelled checks. Stop assigning further checks on miss/cancel and join in-flight workers. Effect on cold boot or stop latency is not measured. |
| RPCS3 performance and diagnostic scope | The Core 627 iPhone records show a real SPU load reduction in Black Ops II menus, modest heavy-scene AC FPS and poor BO2 multiplayer 1% lows. [Core 630](rpcs3-core630-2026-11-03.md) targets guest report waits. [634](rpcs3-core634-2026-11-03.md) chiefly targets boot and memory. Its verified pin is `ffd5b62d`; no 634 gameplay result yet. Suites 634→630→627 re-execute historical checks on reverted trees. | Compare matched heavy gameplay, cold/warm boots and Light-vs-normal measurement using existing logs. Reuse historical receipts only on matching code, tests, tools, flags and environment; keep fresh checks of changed behavior on the effective Core. |
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
