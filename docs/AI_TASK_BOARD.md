# RewindBox — shared requirements and results

**Single contract · 13 November 2026.** Current maintainer instructions override
older records. Read the rules, your routing and **one relevant task**; open only
its needed evidence. A recorded status is not a live CI result.

[Rules](#shared-working-rules) · [Claude routing](#adaptive-delegation) ·
[Codex routing](#codex-model-and-effort-routing) · [IPA authorization](#standing-ipa-compilation-authorization) ·
[Tasks](#active-requirements) · [Delivered baseline](#delivered-baseline) ·
[Evidence](#evidence-by-component)

Detailed inputs, hashes, attempts and rejected hypotheses are preserved in
[the immutable prior record](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md) and linked component evidence.
They are evidence to consult selectively, not old instructions to resume.

## Shared working rules

1. **PRIORITY / STRICT — turn constraints into improvements.** Every in-scope
   performance/stability/rendering/audio/input constraint requires concrete
   modification work, executed before/after verification and reviewed handoff.
   “GPU-bound”, “first-use compilation” or “real constraint” alone never closes it.
   Record symptom → source/lever → change → executed check → outcome.
   Diagnostics and unexecuted tests are intermediate. If a hypothesis fails,
   change the approach; keep actionable work open. A demonstrated irreducible
   limit or unavailable device/access needs evidence and an exact next action.
   Continue independent improvements. Never fabricate a patch/gain or weaken
   rendering, synchronization, data or tests.
2. **Finish approved work without repeated approval.** Continue through correction,
   verification, integration and authorized private delivery. Resolve missing
   technical evidence with existing logs/source and a bounded executable check.
   Ask only for a necessary new decision, access or physical observation unavailable
   in the environment. Respect actual tool/platform refusals; never bypass them.
3. **Preserve ownership and work.** Main is the coordination role, normally the
   principal Claude session. The active task may explicitly delegate its execution
   to Codex. That coordinator owns integration, Cores, pins, CI, freeze and delivery;
   component sessions own their changes. Inspect branch, HEAD, remote and
   dirty paths first. One writer per path; preserve concurrent/local-only work,
   `main`, `backup`, tags, baselines and history. No force-push/reset/clean,
   silent conflict resolution, duplicate diagnosis/build or unrelated feature.
4. **Use safe branches.** Component follow-ups after squash/integration/closed PR
   start a fresh local branch/worktree from current `Claude`, preserve local work
   and replay only the intended delta. Publish an unfinished lot through the
   [Backup archive and exact-SHA handoff](branch-archive.md), not by recreating
   archived remote branches. A new PR/remote branch requires an explicit current
   integration decision. No forced reuse or synthetic `ours` merge around a refusal.
   Separate commit from push. The coordinator integrates the reviewed delta and evidence.
5. **Keep this contract current and small.** After meaningful results and before
   ending/compaction/handoff, replace only your task's current state; delegated agents
   submit that update to its coordinator unless explicitly assigned the board entry. Correct
   permanent instructions in place. Fetch latest first: never overwrite the board
   from a stale branch. Link detailed evidence; do not append a chronological diary.
   Distinguish dirty/local/published/tested/compiled/delivered/device-observed.
6. **Use included services.** Official subscription sign-ins only; no paid API,
   outside agent launcher, quota polling, billing/subscription changes or auto-top-up.
   No new worker merely for another badge; delegation limits below still apply.
   Quota loss transfers neither ownership nor history. Public posting and unrelated
   destructive actions require separate authorization. This file is not a scheduler.
7. **Communicate meaningful outcomes in French.** Report required attempt outcomes,
   significant results and real blockers; avoid repetitive updates, identical
   relaunches and requests for already-published logs. “Done” without checks is not proof.

**Misaddressed files:** main routes the exact batch from source session to owner
using real native file sharing, or authorized Codex download/re-attachment.
Text/session metadata access is not file access. Verify sizes/SHA-256 and destination
receipt; distinguish queued/sent/received. No substitution with older namesakes,
raw private logs in Git, public links or extra worker. State the exact access
limitation if originals cannot be retrieved; continue independent work.

## Adaptive delegation

Prefer direct work for tiny tasks and **one coding agent total**. Authorized
parallel coding uses separate branches/checkouts and disjoint paths; at most two
useful independent read-only reviewers, no nested teams or duplicate reviews.

| Work | Native agent | Model / effort |
| --- | --- | --- |
| Exact file/symbol/result lookup | `rb-lookup` | Haiku / low |
| Bounded source/upstream investigation | `rb-research` | Sonnet / medium |
| Understood isolated correction | `rb-code` | Sonnet / medium |
| Difficult Core/JIT/GPU/memory/ABI/native lifecycle review | `rb-core-review` | Opus / high |

Pass BOTH model and effort when supported, exact base/diff/owned paths, prior
findings, one question, acceptance and stopping condition. Return decisive evidence
and next action (normally 200–400 words). `worktree.baseRef: head` omits dirty work;
only main integrates. If unavailable, owner continues and reports the limitation.

**Main-turn effort:** invoke native Skill `rb-effort-low`, `rb-effort-medium` or
`rb-effort-high`; a prose claim does not change it.

| Remaining work | Effort |
| --- | --- |
| Facts/status only | low |
| Understood bounded correction or routine handoff | medium |
| Unresolved Core/GPU/JIT/memory/concurrency/ABI, UIKit, skin hit/stick/orientation or risky review | high |
| Named exceptional hard ambiguity | Extra/Max, then exit after resolution |

Reassess each user turn and genuine phase boundary, not each command. A status
interruption does not lower effort before resuming risky code. Keep the principal
model stable within a task; model changes are separate native operations. If an
exceptional level lacks a selector/self-control, report the exact limitation for
the coordinator's already-authorized UI adjustment, without a new worker/approval.

**Verify per session:** sync only relevant config, preserve dirty work and
`/reload-skills` when needed; record actual Skill return/expanded
`${CLAUDE_EFFORT}`, requested level and displayed session setting separately.
Manual Max persists; project medium does not clear it. A loaded skill overrides
session effort for its turn, requiring invocation next turn.
`CLAUDE_CODE_EFFORT_LEVEL` or an organization cap can prevail: inspect only relevant
non-secret effort settings on mismatch. UI alone does not prove an in-flight
request's effort; permissions Auto is not effort automation. No unverified routing
or savings claim. Config: `.claude/agents/`, `.claude/skills/rb-effort-*/SKILL.md`,
`.claude/settings.json`; activation evidence stays in the task, not permanent rules.

**Failure escalation:** classify exact run/job/assertion as product, harness,
baseline or infrastructure. Fix simple causes directly; after two equivalent
inconclusive checks change method. Escalate once for a named complex ambiguity,
with exact attempts and required tests. Do not model-switch or rerun full workflows
to solve a missing artifact, network error or attributed baseline failure.
[Native behavior reference](https://code.claude.com/docs/en/model-config).

## Codex model and effort routing

Delegate only when useful/authorized; verify exposed native availability, set BOTH
parameters with `fork_turns: none`, provide minimum context and keep one writer.

| Independent work | Model alias | Effort |
| --- | --- | --- |
| Exact lookup/receipt | `gpt-6-luna` | low |
| Bounded research, understood change/check | `gpt-6.1-sol` | medium |
| Difficult Core/GPU/JIT/memory/concurrency/ABI review | `gpt-6-astra` | high |

These are Work Mode aliases, not API IDs. Escalate once for a named ambiguity.
The app controls Codex's primary model/effort; never claim to switch them through
project text. No paid service permission is implied. Personal routing points here.

## Standing IPA compilation authorization

**Historical numbered examples below are not new build requests.** The current
common delivered baseline is 732, including XeniOS and S2Arm by the later
maintainer decisions. Use the active task and its current manifest, not 725/803.

**Already approved:** main may review/integrate approved changes, run/recover
Core/macOS CI, package, verify and privately deliver the common IPA without asking
again (3 Nov; reconfirmed 4 Nov). Its ordinary fast-forward commits to
`origin/Claude` are authorized, with `[skip ci]` unless CI is intended. Reconcile
only owned unpushed commits after inspecting remote advances/conflicts.

**Historical separate S2Arm trial (11 Nov):** the 725/801 split, former component
branch and then-current probe restrictions are preserved in the
[immutable prior contract](https://github.com/TarbleFR/RewindBox/blob/058c6fc33a53a13667579b9d4636524f9a644207/docs/AI_TASK_BOARD.md#standing-ipa-compilation-authorization).
They do not request another trial or remove the S2Arm engine from the later delivered
732 baseline. Use the active common-IPA and S2Arm tasks, their manifests and current
ownership. A new separate experiment needs its own explicit current scope.

**Recipe approval `49e4f2e` remains valid:** explicitly reviewed/classified merges
already integrated are accepted; preserve shared history, source/component/package/
signature checks and the ban on post-freeze merges. Do not reopen that approval.
Product changes after freeze belong to the next manifest.

**Permanent single recipe (maintainer,13 November2026):** every common private
IPA uses the same versioned standard recipe. Improve this recipe in place only;
never create a build-specific bypass or remove security/identity/compatibility
checks for speed. An improvement requires relevant executed non-regression tests,
review, preserved final validators and an explicit return to the last validated
recipe if a regression appears. Unknown device behavior is not a passing result.
Optional acceleration must preserve the full-build path when unavailable or invalid.

Use [the standard recipe](standard-delivery-recipe.md), last verified IPA and
declared reviewed delta. Rebuild changed components; authenticate retained ones.
Rerun affected tests and always delivery contracts; reuse only equivalent relevant
source, transitive dependencies, tools/config/inputs. Keep Release/ABI/legal/signing/
payload and source/run/artifact/size/hash bindings. Follow [Core swaps](core-swap-delivery.md),
[delivery speed](delivery-speed.md) and `build-utils/delivery_contract_memo.py`.
A changed host needs a full app build on Xcode/macOS; Windows is not iPhone CI.
The under-40-minute target never removes checks.

After **every** success/failure/interruption, retain/report build/version, source/
Core identities, run/attempt, tests fresh/reused/failed/not-run, result, cause and
next action. Follow the real active run to terminal state; no duplicate dispatch.
Before giving the usable private link, verify the downloaded plaintext IPA against
manifest, component/signing identities and receipt; provide bytes and SHA-256.
Encrypted transport alone is insufficient. Keep recipient keys out of Git and delete
private keys after verified delivery. SideStore supplies Apple provisioning.
State unavailable file/device verification explicitly. No public release/tag/post
or paid-service authorization is implied.

## Diagnose, correct and verify

- Resume existing evidence; reopen only for changed input, contradiction or untested
  path, not a new session. Give each bounded check one question/decision; change
  method after two equivalent inconclusive attempts. Keep independent work moving.
- Apply the priority rule: confirmed defect → fix + executed test; already fixed →
  exact change/build; hypothesis → deciding check; unavailable observation/limit →
  evidence + next action. Diagnostics remain intermediate work.
- Verify real controls/candidates and full dependencies; classify baseline failures.
  Never weaken assertions, skip required tests or call an unexecuted test passed.
- Separate CPU encoding/GPU execution/waits/launch/FPS and source/host/simulator/
  compile/package/device evidence. No unmeasured iPhone FPS/audio/visual gain.
- Use app logs, never request .ips/Jetsam/watchdog reports or block on them.
  Separate build/PID/session/game/mode, cold/warm and duplicate rotations.
  No raw private logs, secrets or recipient keys in instructions/Git.
- Handoff/compaction keeps request/authorization, branch/HEAD/dirty ownership,
  input identities, findings/rejected paths, exact change/tests, blocker and next.

### Command output

For verbose foreground checks use `python3 scripts/ai-output.py run -- <command> <args>`;
for journals use `file <path>`. `run --log-dir <parent> -- ...` selects its parent.
It preserves full binary output/SHA-256/receipt and child exit status, not pipelines
or interactive commands. Exit status first; keywords never prove success. Inspect
the needed full-log range and existing analyzers, retain decisive evidence in its
component location. Wrapper success is not input equivalence.

## Product and delivery requirements

- New product text: RewindBox; preserve NeoStation credits/licenses, IDs, storage/
  preferences, channels and ABI. Follow [rebranding](REBRANDING.md) and relevant
  [component rules](PROJECT_RULES.md).
- Keep KartPad/Mario Kart Pad, Dusklight, Ports playlist and MeloNX external
  StikDebug/Shortcut fallback retired; preserve player files and evidence.
- Preserve reviewed library behavior/exceptions, backups, games/saves/firmware/keys/
  caches/mods/pairing and approved replacement rules. No destructive concealment,
  speculative migration, duplicate hiding or parallel library.
- Preserve canonical sources, generation/ownership, cancellation, late callbacks,
  errors and teardown; check affected first/relaunch/recovery/cross-engine paths.
  Hogwarts remains 1x with equivalent full rendering: no hidden quality/resolution
  reduction, unsafe synchronization or unverified global workaround. Shader
  interpreter remains off unless separately approved.
- Preserve all 12 locales (en/es/ru/zh/zh_Hant/pt/fr/de/it/id/ja/ko) for changed text,
  help/errors/accessibility; verify keys/placeholders/Traditional Chinese.
  English fallback is not a translation; diagnostics stay separate.
- Skins: old packs/IDs/previews/imports/selections remain. Add approved variants
  faithfully in both orientations, verify actual overlay/contours/press/release/
  sticks/Menu/rotation/persistence; preserve portrait-only lock, dual-layout
  rotation and restoration. Document necessary adaptations and unobserved feel.

## Release notes and publication checklist

Main maintains [releases/NEXT.md](releases/NEXT.md), with exact source/evidence and
English user-facing notes from owners. Update after reviewed changes and verified
private IPA: features/fixes/stability/compatibility/limits, with truthful state.
Before public release reconcile ALL approved unannounced content since the actual
public tag against final manifest/receipts; record deferral/exclusion.
After an authorized PUBLIC release archive `releases/<actual-tag>.md` with exact
tag/build/source/URL; start fresh NEXT and carry unshipped/unannounced items.
Private delivery does not reset the public baseline. Supply ready-to-post English
notes, label previews; writing is authorized, public posting separate. NEXT is
communication evidence, not another implementation queue.

## Cross-account coordination

GitHub is the durable transport shared by both accounts. Private Claude session
messages are optional: a `not found` response is not a handoff and must not create
an indefinite wait. This board remains the sole task/ownership contract.

1. At start/resume and before handing over, fetch `origin/Claude`, inspect local
   work, read the relevant task and run `python3 tools/coordination/status.py`.
   Use the existing official `gh` sign-in or `GH_TOKEN`; never put a token in Git.
2. Only `main`, `Claude`, `Backup` are durable remote branches (maintainer, 13 Nov).
   Archived task branches below are historical names, not push targets. Keep local
   worktrees; do not recreate those remote branches automatically. Preserve local
   uncommitted work. Follow [the archive protocol](branch-archive.md) to publish
   an unfinished source under Backup with previous Backup + lot SHA as parents.
3. Use [shared handoff issue #179](https://github.com/TarbleFR/RewindBox/issues/179)
   for exact source/owner/reviewer/dependencies/checks/producer receipts. The receiver
   records `ACK <full SHA>`, then review/integration/Core/pin/IPA evidence separately.
   A source advance requires a fresh review. Backup is archival ancestry only;
   NEVER merge it into Claude/main. Main selects reviewed source commits.
4. One writer per path. Main handles common Core numbering, composition, freeze,
   pin and IPA. Resolve shared test/recipe edits with the component owner before
   changing them; do not revert and reintroduce each other's corrections silently.
5. Before a producer dispatch run `python3 tools/coordination/status.py --source
   <full SHA>`: follow an existing active run, reuse a valid pinned result, or state
   the changed input that needs another run. No push-plus-dispatch duplicate.
6. Classify red results as compile/product, test harness, source/contract or network.
   Preserve source/run/attempt/job identities. Current delivery requires evidence
   from its exact attempt; blindly rerunning failed jobs alone is not a supported
   substitute. For a new delivery request use existing `tests.<group>.mode=reuse`
   only when `reuse_guard` authenticates identical effective tree, commands, recipe
   reads and artifacts. Preflight remains fresh. No compiled-app reuse is claimed.
7. A blocked recipient is handled through issue #179 and this task's exact next action;
   continue independent work. Do not create another competing implementation.

## Active requirements

Snapshot below is an index, not a live CI result. Current Claude/Backup HEADs, issue #179 receipts,
artifacts and receipts take precedence over old statuses. All removed detail,
negative findings and prior decisions remain in the
[immutable pre-cleanup contract](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md).
Do not restart a historical task from that archive.

| Owner | Local work / archived branch name | Responsibility / next action |
| --- | --- | --- |
| Main `012mUAShv9k6pSCnpW7oAF63` | `Claude` | Integration, common Cores, pins, recipe and private delivery; reconcile current handoffs and 733 retries. |
| MeloNX `012mUASkkFGHaPcEUx9dsp8q` | `work/melonx-fps-stability-20261103` | Native/MoltenVK heap, bridge and timing-test owner; review lot 10's native-heap request and hand over exact CI fix. |
| MeloNX lot 10 `01JA5QgKeoGVH5oVjNyhcj3D` | `work/melonx-lot10-20261112` | Six adapters and macOS fixture fixes through d17a29f2 integrated by main as 30ee5beb; main composes/freezes the Core. |
| XeniOS `012mUASiVyxdnhNTUKesGGm7` | `work/playlists-xenios-20261110` | Xbox 360 engine/bridge, legal chain and device follow-ups. |
| S2Arm `012mUASj3EQnvC86WC56AePw` | `work/s2arm-switch2-prototype-20261110` | Switch 2 engine, preparation, playlist and device follow-ups. |
| Skins `012mUASjgVWk8DKKjVbwTD2n` | Local worktree from Claude for any new lot | Preserve reviewed packs/controls; merged branches are not active task queues. |
| Codex coordination | Integration on `Claude`, former work branch archived | Completed branch/archive consolidation, shared handoff, common producer routing and guarded Actions cleanup; see maintenance report and nine refused orphan deletions. |

### Common IPA — main Claude Code / Codex execution authorized 13 Nov

**Goal:** deliver the authorized, reviewed common IPA with exact component identities.
**Delivered:** 732, run `43289133482`, source `77af35c2`, receipt below. RPCS3 934,
MeloNX 743, Xenia c7d6a5c4, S2Arm 9560e56f. Gameplay validation stays separate.
**733 (13 Nov):** S2Arm engine 9ddb304e (patch 0012) + preparation speed lot + MeloNX Core 745
(lot 10) with its live-capture bridge; XeniaCore c7d6a5c4 and RPCS3 934 retained. Earlier requests:
`43312487102` (HTTP 503 downloads, then the fixed 200 ms spinner floor), `43322868775` (flutter-action
hashFiles timeout, cancelled). Recipe `b12dc220`: bounded retries of transient GitHub reads and downloads,
Flutter action pinned by SHA with pub-cache off; contract 119 OK. Owner test files restored/merged
(`d7123113`, `f61b2bde`). Lot 10 `d17a29f2` and `f5abc0ac` acknowledged on #179. Core 745 frozen in
`f4fb22fd` (contract `807edc42`, 104/104 planned gates passed locally on the final preparation, receipts
bound to this tree). **Core CI run `43336528859` failed before compiling:** its first dependency step reads
the engine82 baseline (artifact `12883480724`, `be55d705`), which had 14-day retention and expired on 12 Nov
about 08:20 UTC (HTTP 404; no copy of its bytes exists). Same class: the 614 archive `13141611354` expires
16 Nov, the Core 743 artifact 26 Nov; durable byte copies: 614 in delivery artifacts `13150348411`/`13156638305`,
Core 743 (holding the authenticated engine82 history and LibHac inputs) in `13976632507`.
The reviewed recovery is integrated as `871258fb`; its active replacement run is recorded below.
Checked on `f4fb22fd`: delivery contract and its test pass except the expected pin/contract binding until
Core 745 is pinned; engine concurrency, tidy, consolidation, retirement, S2Arm pinned-engine/legal and XeniOS
review tests OK. Known red outside the recipe: `.github/diagnostics/s2arm/s2arm_delivery_test.py` (old S2Arm
test-IPA launcher, line constants drifted since `fc0c18dd`; it refuses that line until reviewed, not used by 733).
**Current execution (maintainer,13 Nov):** Codex was explicitly asked to launch the next common IPA,
then to apply engine compilation improvements first. Issue179 comment6840690330 records this execution
ownership; do not dispatch a competing Core/IPA. Reviewed recovery and optional host cache are integrated
as `871258fb`; future Xenia compiler cache is `ab0a69c7` (source-only for733, retained engine unchanged).
Engine cache changes are `5451dbb200b1517c13a3be479be55de6c679bf89`: explicit MeloNX request routing,
exact authenticated envelope caches and hashed S2Arm source reuse. Contract
`08e254a3` changes only recipe/test input hashes; all104 gate definitions and runtime/preparation fields
are unchanged.451 contract checks,24 recovery checks and3 focused cache tests passed on the integrated tree;
independent review passed. Also rerun:9 encrypted-host-cache and15 standard-workflow tests, all passed.
[Verification receipt](evidence/engine-build-caches-2026-11-13.json). No macOS speed gain is claimed.
**Core745 execution:** run `43344184896`, attempt1, job`131619413611`, source
`ced57c6de8e99a241610b5c1756d962fb9d0067f` completed successfully. Downloaded artifact
`14004910211` (100703496 bytes, SHA256 `f0d5a52957a9f58652a2ae21829fffa00ecaa95455bd18f984eeb23a9f6c1608`)
passed the unchanged component verifier:104 fresh gates,61 historical scopes and two simulator sessions.
Device binary `2943e064…`, payload fingerprint `b580983d…`; the verified745 pin now replaces743 in the draft.
Measured steps:54min29 gates,4min NativeAOT compilation. No device/gameplay gain is claimed.
[Producer origin and full verification](evidence/melonx-core745/verification.json).
The Xenia/S2Arm producer jobs were skipped as intended.
Private-IPA upload-boundary CI passed on Linux/macOS/Windows (`43344184848`).
**IPA733 launched:** standard delivery run `43353788677`, attempt1, source
`b1955be5f6b80733ab6808a3bf875bad8eb459d0`, after local contract and freeze passed.
The frozen composition includes MeloNX745 and S2Arm patch0012 plus the preparation speed lot;
effective digest `e2b4db5fd0de832fcbdea640d449fd969dc8814c449d9d910baaa71ef7ad5309`.
**Next / Codex:** follow this run, then authenticate and privately deliver the downloaded IPA.
The manifest classifies all product commits (no replay conflicts/unclassified paths,
43 retained inputs verified), defers the future Xenia producer recipe and repository-only
Actions maintenance, and has a fresh recipient key. Maintenance058 is reviewed but source-only:
732 had already deferred its parent script/test versions; no unrelated promotion is needed.
The maintainer explicitly requests733 now; new test-reuse/optimization work comes after733.
That new work remains isolated and is not added to this delivery. The104 Core gates are authenticated
by IPA assembly, not reexecuted; the host integration and final delivery checks remain mandatory.
[Manifest](../build-utils/delivery/733.json) · [recipe](standard-delivery-recipe.md).

### RPCS3 FPS, stability and audio — main Claude Code

Core 934 is in delivered 732 (settings sparse overrides/stretch correction).
The requested thermal/sustained-performance lot was gated on delivery of a common
IPA carrying 934 and the other engine handoffs. Main must explicitly bind its
opening to that delivered manifest/receipt before starting the subsequent version;
this maintenance does not start it. Preserve 1x, fidelity, SPU limits, no FPS cap and
no 60-FPS promise. Retain the private 7,849,784-byte log batch and original prompt.
Priorities: invalid THERMAL931 WFE durations, useful-work heat/energy, BO2 blocking
pipeline compilation, validated per-game/behaviour profiles and shared iOS rules.
[932](rpcs3-core932-lot-armsx3-audit.md) · [933](rpcs3-core933-profil-local.md) ·
[full task/input identities](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md#rpcs3-fps-stability-and-audio--main-claude-code).

### MeloNX FPS, memory, black launch and artifacts — existing owner

**Delivered baseline:** Core 743 in IPA729–732. Core745 is compiled, simulator-validated
and independently authenticated; the733 draft now selects its verified pin.
**Lot 10:** six integrated adapters: Nifm static-event retention,
paced strict syncs (Hogwarts), texture-array dirty epochs, shared sibling pipelines,
collection-thread QoS and stall compaction. Main merged the first six-adapter source
`7040c3e1` as `f733bbf9` and the four later macOS test fixes through `d17a29f2` in
`30ee5beb`; executed fixture run `43331900586` is green. The frozen745 contract
contains104 fresh gates; producer `43344184896` passed and its output is now pinned.
[Detailed handoff and device acceptance](evidence/melonx-lot10/handoff.md).
**Performance journal test (owner, d5c88541):** the stall spinner is checked against the waiter (at least the
waiter's 20 ms ceiling and above its measured time), not a fixed 200 ms floor that failed delivery run 43312487102
attempt 4; melonx-host 43332392305 passed on macOS. Merged for IPA 733.
**Device baseline:** IPA729 Hogwarts 17.7 presented FPS, p50/p95/p99 50/117/200 ms,
footprint up to 4,882 MiB. No post-correction iPhone gain yet.
**Native heap:** original owner has named the large MoltenVK stacks (SPIR-V copies,
Metal libraries, descriptor pools, pipeline states); release/compression changes
remain owned there. Graphics-memory savings and thermal gains are not established.
**Next:** main initially froze745 in `f4fb22fd`; reviewed recipe recovery/cache inputs
now bind contract `08e254a3`, preserving all104 gate definitions and the final preparation.
Core CI `43336528859` stopped on the expired engine82 baseline. Reviewed recovery is integrated;
replacement run`43344184896` from`ced57c6d` passed the gates, compilation and two simulator sessions.
Its authenticated pin is selected; include the live-capture bridge in IPA733,
then compare Hogwarts/Smash closes and 20-minute Hogwarts. Preserve 1x/full draws,
all useful syncs, caches and player data. Further instrumentation is justified only
for a missing deciding measurement; confirmed defects need fixes and executed checks.
[Prior tasks and rejected paths](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md#melonx-fps-memory-black-launch-and-artifacts--existing-owner).

### Skins/orientation, PS2/Switch Pocket and main menu bar — existing owner

Reviewed menu, native-ratio framing, pressed controls and Wii portrait work are
integrated; keep installed-pack IDs, imports, hit targets, rotation, input release
and all player preferences. PR170/171/173, fallback PR178 and update notice PR176
are merged. Decorations/preview decoding PR177 is integrated. No fresh device
result is inferred. Continue only the current maintainer's device report or new
scoped instruction on a fresh branch. Earlier unresolved Delta safe-area/cutout
questions stay in [the archived task](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md#skinsorientation-ps2switch-pocket-and-main-menu-bar--existing-owner).
[Pack record](pocket-originals-2026-11-03.md) · [framing](skins-screen-framing-2026-11-10.md).

### Switch 2 playlist (S2Arm) feasibility prototype — session 04

Common 732 contains engine patch0011. The 733 candidate includes verified engine
pin `9ddb304e`, producer `43308161284` (patch0012: sparse tile layout and valid
zero-byte mappings), plus prepare producer `43304794526` (CommonCrypto parallel
hashing/fewer filesystem walks). Outputs match; preparation speed not measured on
phone. Earlier 732 boot served 57 MB in 0.2 s, then crashed after nnMain; patch0012
is the next device candidate. Preserve saves/import/settings/menu/locales and
existing JIT/helper/NativeAOT isolation rules. No game or key distributed.
Session owns all s2arm paths; common integration/pin/delivery remains main.
[Full evidence](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md#switch-2-playlist-s2arm-feasibility-prototype--session-04).

### Playlists/XeniOS (Xbox 360) — session 03 `012mUASiVyxdnhNTUKesGGm7`

Delivered 732 includes XeniaCore `c7d6a5c4`, profile sign-in, guest dialogs/keyboard,
rumble/all pads and the licence audit. RPCS3/MeloNX Core pins were retained.
Next device checks: START past title, saves/dialogs, rumble, pad loss, edge swipe,
profile-sign-in line, repeated launch. Preserve suppressed microphone/online
behaviour and ABI/lifecycle controls. Converter may ship by the maintainer's
recorded decision; provenance/package-match/re-signing questions remain open,
not an Apple authorization. Original 4.0 beta3 dylib differs from pinned ios4.0.3;
keep strict actual signature/bytes checks and notices.
[Playlist contract](xenios-playlist.md) · [legal evidence](evidence/xenia-metal-shader-converter/)
· [full task](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md#playlistsxenios-xbox-360--session-03-012muasivyxdnhntukesggm7).

### Codex orchestration — Codex

**Goal:** maintainer-authorized coordination/build-recipe cleanup, retaining only
main, Claude and Backup without losing work.
**State:** 35 remote branch refs removed after preservation (7 already integrated,
28 archived); Backup `4e2ec758` includes concurrent MeloNX head `f5abc0ac`.
Fresh-repository retrieval of that deleted-branch commit passed. Backup must never
be merged into product history. AGENTS and archive protocol govern future local
worktrees and exact-source publication. Shared issue #179 carries cross-account
handoffs; the board remains the task contract.
**Recipe:** common XeniOS/S2Arm producers route from Claude with explicit requests
and source-specific concurrency; old pin provenance remains authenticated.
67 scoped tests and 70 rewrite checks passed. The experimental S2Arm 801+ lane
remains archived and is not a valid Claude dispatch route.
**Evidence:** [maintenance report](coordination-cleanup-2026-11-13.md),
[branch receipts](evidence/coordination-cleanup-2026-11-13/branch-results.json),
[handoffs](https://github.com/TarbleFR/RewindBox/issues/179).
**Reviewed dependency recovery:** candidate `d31c07d6ccf06f17c7ed1ca87ef94e6774fd0151` is
preserved in Backup and handed to main in issue179 comment6840460119. It recovers
authenticated Core743/732 history and LibHac plus exact614/615, preserving runtime,
preparation and104 gates.108 real-archive recovery checks and515 DMA contract checks
passed; independent review complete. New Core retention90days; original engine82
ZIP/binaries remain unavailable. [Evidence](https://github.com/TarbleFR/RewindBox/blob/d31c07d6ccf06f17c7ed1ca87ef94e6774fd0151/docs/melonx-dependency-recovery-2026-11-13.md).
**Reviewed incremental recipe:** candidate `4c90eb746c14b1455735df9013abd80c8c9001d0`, also archived
in Backup, adds optional encrypted exact-input DerivedData reuse to the permanent
standard workflow. Xcode, current Core embedding and every final validator remain
mandatory.9 cache and15 existing Workflow tests pass; two guard mutations detected.
Full standard suite interrupted; its pending DMA pin error reproduced on unchanged
32d71b22. No full-suite success, Apple build or speed gain claimed.
[Implementation, activation and rollback](https://github.com/TarbleFR/RewindBox/blob/4c90eb746c14b1455735df9013abd80c8c9001d0/docs/ipa-incremental-build.md).
**Applied on maintainer request (13 Nov):** reviewed recovery and host-cache candidates are integrated
as `871258fb200adb2d4723c183700f83b49838b9e7`. Xenia compiler cache is the separate
`ab0a69c7addcf7357f83f2a0c1632264c002c6b5`, deferred from733's effective product tree so the
retained Xenia payload keeps its original reviewed recipe. Engine cache source is `5451dbb200b1517c13a3be479be55de6c679bf89`. MeloNX now requires an explicit producer request
and reuses only three exact, reauthenticated dependency envelopes. S2Arm reuses and rehashes its pinned
codec sources. RPCS3 already uses Ninja/ccache; its frozen producer is unchanged.
[Implementation and measured limits](engine-build-caches.md). Independent review corrected the native
envelope path and the Bash nounset cold path; root reran451 DMA checks,24 recovery checks,3 cache tests
and Bash syntax successfully.104 Core gates and runtime/preparation contracts remain unchanged.
**Next / owner:** Codex executes the maintainer's new private delivery request, coordinated on issue179,
without a duplicate producer. Draft `dceb3344` already classifies the reviewed host-cache
integration and defers the Xenia-only producer commit. Reconcile subsequent maintenance
commits before733's materialization/freeze. Core745 run`43344184896` from`ced57c6d` is successful,
downloaded and authenticated; freeze and deliver733 before integrating further test-reuse work.
No warm-cache speed measurement or new IPA delivery is claimed. The permanent single-recipe
rule remains active in ca8fa34d.
Dedicated `REWINDBOX_BUILD_CACHE_KEY` is required for optional acceleration; Codex
could not provision it (GitHub connector has no secret-write operation; PC connector
unavailable twice with429). Without a key the normal build remains operational.
No recipient private key or app-embedded credential is reused for this cache.
Earlier S2Arm content/provenance audits remain archived; this cleanup adds no
ownership or legality conclusion.

### Private test IPA protection — Codex

Integrated #174/#175. Keep the immutable plaintext-IPA upload guard on every
new workflow. Historical scan of 2,155 artifacts found no plaintext IPA; encrypted
contents were not decrypted. Do not weaken signature, source, legal, hash or
recipient checks for speed. [Evidence](evidence/private-ipa-protection-2026-11-11.json).

### Actions history cleanup — Codex

**Completed (maintainer request, 13 Nov):** run `43346257896`, source `058c6fc3`,
deleted exactly 360 reviewed runs: 177 failed, 101 successful, 42 cancelled, 40 skipped.
No conflict or already-absent result; zero planned candidates remain. The 1,607-run
snapshot plus four new runs became 1,251. All 1,247 protected snapshot IDs remain,
including Core745, all artifact-bearing/referenced runs and the nine prior403 orphans.
The exact plan, live identity/job checks and newest300 protections were preserved.
Code:37 safety tests passed. Downloaded receipt/API digest verified; independent
postflight passed17 checks against the plan, journal and two matching final inventories.
[Result and receipts](actions-history-triage-2026-11-13.md).
The strict branch lease has ended; the one-off launcher is removed with this record.

The four explicitly obsolete 606/608/609/610 launchers are confirmed
disabled_manually; source YAML remains for historical recipe verification.
History job 131586909223 (run43334427815) completed: 532 reviewed skipped runs
removed, no conflicts, zero remaining planned candidates. Empty jobs/artifacts,
exact run identity and newest300 protections were checked. Receipt and final
absence inventory are archived in the maintenance evidence.
Nine reviewed old empty queued records remain: cancellation was unconfirmed,
and final deletion requests all returned HTTP403 (run43337757433). They are
not counted as deleted; no repeated refused mutation was attempted.
Retain active jobs, artifacts, referenced/protected producers and failure evidence.
Only the explicitly reviewed plan may remove completed, unreferenced runs without
artifacts after its live identity and job checks pass.
The one-off maintenance launchers are removed after completion; plans and receipts
remain in [the maintenance report](coordination-cleanup-2026-11-13.md).
Only main, Claude and Backup remain as remote branches at final verification.
Prior cleanups: [1,311 skipped runs](evidence/github-cleanup-2026-11-10.json)
and [383 skipped runs](evidence/github-cleanup-2026-11-10-followup.json).

### Markdown maintenance — Codex

**Goal (maintainer,13 Nov):** remove obsolete or conflicting active Markdown guidance.
Inventory:588 Markdown files at the reviewed source. Independent reviews identified branch/ownership,
board-writing,745 status and Actions-preservation contradictions. Corrections
consolidate those rules, shorten the obsolete725/801 trial instructions to an immutable
history link, and distinguish current instructions from old release/build notes through
the [documentation index](README.md). Legal notices and historical evidence remain intact.
**Validation:**14 Markdown files corrected, including the final cleanup result; relative
file links and diff checked, independent instruction/navigation reviews passed
(52 anchors also checked). Source/legal notices and evidence were not rewritten.
**Next:** reconcile later producer status before freezing733. Documentation changes
are recipe-only and do not require rebuilding the active Core.

## Delivered baseline

**Last verified common IPA: RewindBox 732**, run `43289133482` attempt1,
source `77af35c2097a418c73a12eeb8997690493ed68d8`, frozen `474862f5`, effective `662f421f`.
329,956,970 bytes, SHA-256 `97952e981eea2eff72bb93f35627a831221aa4bf0ed9abaeb67d48dbb93ade52`.
RPCS3 934, MeloNX 743, XeniaCore c7d6a5c4, S2Arm 9560e56f; 97 images,
46 retained fingerprints, six validators passed offline. Key deleted, privately
sent. No new device performance/thermal claim. Public release remains separate.
[Manifest](../build-utils/delivery/732.json) · [receipt](evidence/rewind732/delivery.json).

## Findings to carry forward

Read only the relevant [archived findings](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md#findings-to-carry-forward)
and direct component evidence. Preserve rejected hypotheses and baseline attribution.

## Update a task in place

Use Goal / State / Evidence / Open or limit / Next. Keep owner, exact source, run,
Core/pin/IPA/device distinctions. Replace stale status, do not append a diary.
Fetch first; reconcile concurrent changes. Archive detail by immutable commit,
never destroy prior evidence. This file is a contract, not an automatic scheduler.

## Evidence by component

| Scope | Evidence |
| --- | --- |
| Architecture | [ARCHITECTURE](../ARCHITECTURE.md), [PROJECT_RULES](PROJECT_RULES.md) |
| Delivery | [standard recipe](standard-delivery-recipe.md), [speed](delivery-speed.md), exact numbered manifests/receipts |
| MeloNX | [lot10 handoff](evidence/melonx-lot10/handoff.md), `build-utils/melonx/dma-core-pin.json`, `moltenvk-rebuild-pin.json` |
| RPCS3 | [932](rpcs3-core932-lot-armsx3-audit.md), [933](rpcs3-core933-profil-local.md), `build-utils/rpcs3/core-pin.json` |
| Skins | [Pocket](pocket-originals-2026-11-03.md), [framing](skins-screen-framing-2026-11-10.md) |
| Rights | [LEGAL](LEGAL_AND_CREDITS.md), [Xenia converter](evidence/xenia-metal-shader-converter/) |
| Historical exact inputs/results | [immutable full contract](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md) |

