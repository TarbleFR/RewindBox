# RewindBox — task state and technical requirements

**Simplified workflow · 13 November 2026.** [AGENTS.md](../AGENTS.md) defines how
agents work: directly on `Claude`, without automatic issues, PRs, branches or
worktrees. Read only the relevant task and technical requirements below.
Historical issue/session/branch references are evidence, never prerequisites
to continue, recreate a deleted item, or start another delivery.

[IPA authorization](#standing-ipa-compilation-authorization) ·
[Tasks](#active-requirements) · [Delivered baseline](#delivered-baseline) ·
[Evidence](#evidence-by-component)

## Shared working rules

Follow AGENTS.md. Preserve existing product, data and delivery safeguards.
Fix demonstrated defects and run meaningful checks; do not invent gains or
weaken tests. Reuse prior findings and investigate changed inputs or unresolved
questions. Ask only for genuinely missing access, evidence or a new decision.
Use included services; no paid API, billing changes or unauthorized public posts.
Transfer private files only through authorized channels; never put secrets or
raw private logs in Git. A short useful task update is sufficient.

## Adaptive delegation

Work directly by default. A helper may answer one useful independent question
or edit explicitly assigned non-overlapping paths; never create a branch or
worktree for it automatically. Serialize conflicting edits and keep one delivery
executor. Return concise findings, changes, checks and any real blocker.
The existing agent definitions and effort selectors are optional tools, not a
required step on each turn. No repeated effort-setting checks or claimed savings.

## Codex model and effort routing

If delegation is useful, use an available native model/effort suited to the
question. No mandatory routing table or model switching. The application controls
the primary model; repository text does not change it.

## Standing IPA compilation authorization

**Historical numbered examples below are not new build requests.** The current
common delivered baseline is 733, including XeniOS and S2Arm by the later
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

**Delivery priority (maintainer,13 November2026):** waiting thirty minutes after a green
IPA and receiving unusable links is unacceptable. Keep following the authorized run
through private file delivery; do not end at launch and wait for the maintainer to
ask again. While CI runs, prepare the recipient, empty verification directory and
current transfer helpers. On success, retrieve the four final parts concurrently,
authenticate/decrypt them and execute the mandatory final checks once on the exact
file. Preserve the required receipts before deleting the recipient key. Save and
present the verified downloadable file immediately; optional reviews, reports,
repository housekeeping and future optimizations follow delivery. Use the confirmed
native file link; if the user reports it unusable, provide a fresh ZIP attachment
and the exact filename to locate directly. Never claim a client download was tested
unless it was observed. Never trade integrity/signature/source checks for speed.

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

Both accounts work on `Claude` under AGENTS.md. Read the relevant task, inspect
current source and existing CI runs, and avoid concurrent writes to shared paths.
A short board update or the current conversation provides continuity. No issue,
ACK, private session lookup, Backup publication or status script is mandatory.
Before a build, verify the exact source and follow any existing matching run.
Retain the standard recipe's checks and reuse guards. Classify a failure from
its actual job/attempt and correct the cause before retrying.

## Active requirements

Snapshot below is an index, not a live CI result. Current Claude source, live runs,
artifacts and verified receipts take precedence over old statuses. All removed detail,
negative findings and prior decisions remain in the
[immutable pre-cleanup contract](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md).
Do not restart a historical task from that archive.

| Owner | Historical work reference (new work uses Claude) | Responsibility / next action |
| --- | --- | --- |
| Main `012mUAShv9k6pSCnpW7oAF63` | `Claude` | Integration, common Cores, pins, recipe and private delivery; reconcile current handoffs and 733 retries. |
| MeloNX `012mUASkkFGHaPcEUx9dsp8q` | `work/melonx-fps-stability-20261103` | Native/MoltenVK heap, bridge and timing-test owner; review lot 10's native-heap request and hand over exact CI fix. |
| MeloNX lot 10 / heat `01JA5QgKeoGVH5oVjNyhcj3D` | `work/melonx-heat-20261113` (lot 10 integrated as 30ee5beb) | Heat lot `adapt_wait_spin_bound` with gate and Core 747 wiring for main to freeze, build and pin; then the 20-minute before/after protocol. |
| XeniOS `012mUASiVyxdnhNTUKesGGm7` | `work/playlists-xenios-20261110` | Xbox 360 engine/bridge, legal chain and device follow-ups. |
| S2Arm `012mUASj3EQnvC86WC56AePw` | `work/s2arm-switch2-prototype-20261110` | Switch 2 engine, preparation, playlist and device follow-ups. |
| Skins `012mUASjgVWk8DKKjVbwTD2n` | Direct work on Claude | Preserve reviewed packs/controls; merged branches are not active task queues. |
| Codex coordination | Integration on `Claude`, former work branch archived | Completed branch/archive consolidation, shared handoff, common producer routing and guarded Actions cleanup; see maintenance report and nine refused orphan deletions. |

### Common IPA — main Claude Code / Codex execution authorized 13 Nov

**Goal:** deliver the authorized, reviewed common IPA with exact component identities.
**Delivered:** 733, run `43353788677`, source `b1955be5`, receipt below. RPCS3 934,
MeloNX 745, Xenia c7d6a5c4, S2Arm 9ddb304e. Gameplay validation stays separate.
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
**Test delivery 734 (maintainer, 13 Nov, later):** authorized in session `01JA5QgNKffXiA5ZjCm4JEun` with the S2Arm
Mario Kart World lot (engine patches 0013–0015) and the MeloNX heat lot (`work/melonx-heat-20261113` `a0fea59e`,
Core 747). The maintainer chose that session as executor, with fast-forward pushes to `Claude`; ownership is on issue
179, comment 6851399483. **Do not dispatch a competing Core 747 or IPA 734.** That session has no .NET 10.0.100 SDK
(its installation was refused there), so the Core 747 freeze (105 local gates) was asked of the lot's owner session
`01JA5QgKeoGVH5oVjNyhcj3D` on its branch; a 734 without Core 747 is only sent if that freeze cannot be produced, and
says so. Order: S2Arm lot merged and engine requested on `Claude` → engine pin → Core 747 freeze, request, verification,
pin → manifest 734 → `[ipa-delivery:734]` → offline verification and private delivery. Read the live runs, not this line.
**Done so far:** S2Arm lot merged as `2b37878f`; engine from `Claude` by `s2arm-engine.yml` run `43416941344` attempt 1
(both macOS jobs green), artifact `14033191665` (23,931,435 bytes, `6fceef1d…`); pin job run `43418945255` (job
`131863796870`); verified pin `8da9c21b…` committed as `46cd382d` (series 0001–0015, packaged fingerprint `6698e435…`),
artifact downloaded by id and checked with `engine_pin.py verify`. Recipient public key `delivery-734-recipient.pem`
(`8dcc4f87…`). The owner session reported the Core 747 freeze running (105 gates, Linux, .NET 10.0.100, about two
hours). Environment: artifact storage hosts had to be allowed for this session (new personal cloud environment
`rewindbox`, approved by the maintainer) before any artifact could be downloaded and verified.
**Core 747:** the owner froze it at `344666e5` (contract `b89a8124…`, 105/105 local gates, .NET 10.0.100); checked here
(same contract digest, contract test 453 checks, recovery test 24, independent review of the adapter: no definite bug)
and merged with the single request as `16a7a638`. **Core CI run `43423803238` attempt 1 failed in `actions/checkout`,
before any gate or compilation** (job `131880036769`): with `fetch-depth: 0` the macOS runner (case-insensitive file
system) cannot hold `refs/remotes/origin/Claude` next to `refs/remotes/origin/claude/youthful-goldberg-4aphwq`
(“unable to update local ref”, three tries). Class: repository state, not product. That session branch has no commit
of its own (its head `50924021` is in `Claude`); its remote deletion was refused to the executing session by its
environment's protection, the maintainer deletes it. **Rule to keep: no remote branch may differ from `Claude` only by
case in its first path component (`claude/…`), or every full-history macOS checkout fails, the five of
`standard-delivery.yml` included.** Next: the same run is rerun once the branch is gone, then verification and pin.
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
**IPA733 delivered and verified:** standard delivery run `43353788677`, attempt1, source
`b1955be5f6b80733ab6808a3bf875bad8eb459d0`, after local contract and freeze passed.
The frozen composition includes MeloNX745 and S2Arm patch0012 plus the preparation speed lot;
effective digest `e2b4db5fd0de832fcbdea640d449fd969dc8814c449d9d910baaa71ef7ad5309`.
All five jobs succeeded. Downloaded plaintext IPA passed all six offline validators,97 image
identities and10 bundle versions. The eight decrypted receipts were retained before key deletion.
**Next / Codex:** resume the isolated test-reuse improvements for a later delivery; no new IPA requested.
The manifest classifies all product commits (no replay conflicts/unclassified paths,
43 retained inputs verified), defers the future Xenia producer recipe and repository-only
Actions maintenance. The private recipient key was deleted after verification and delivery.
Maintenance058 is reviewed but source-only:
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

**Delivered baseline:** Core745 in IPA733, compiled, simulator-validated and independently
authenticated in the downloaded IPA. Gameplay measurements remain pending.
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
**Heat (13 Nov, IPA 733 journals):** Hogwarts CPU 2.06 W, 150,000 system calls/s; 46-48 % of the busiest
threads' samples spin before a wait (44 % of all samples in the spin's yield: guest scheduler and threaded-renderer
events). `adapt_wait_spin_bound` (every title) keeps the spin only for events whose waits end inside it; gate 42
checks, macOS arm64 run `43367431612`: -48 to -54 % CPU per handoff on long waits, short handoffs kept. Branch
`work/melonx-heat-20261113`; **Core 747 frozen** at `344666e5` for the S2Arm 734 delivery (its request, #179): 105/105 gates on the final preparation (Linux, .NET 10.0.100), contract `b89a8124`, contract test 517 checks; build request left to that session. No iPhone result.
[Heat handoff and protocol](evidence/melonx-heat/handoff.md).
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
scoped instruction directly on Claude. Earlier unresolved Delta safe-area/cutout
questions stay in [the archived task](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md#skinsorientation-ps2switch-pocket-and-main-menu-bar--existing-owner).
[Pack record](pocket-originals-2026-11-03.md) · [framing](skins-screen-framing-2026-11-10.md).

### Switch 2 playlist (S2Arm) feasibility prototype — session 04

Common732 contained engine patch0011. Delivered733 includes verified engine
pin `9ddb304e`, producer `43308161284` (patch0012: sparse tile layout and valid
zero-byte mappings), plus prepare producer `43304794526` (CommonCrypto parallel
hashing/fewer filesystem walks). Outputs match; preparation speed not measured on
phone. Earlier 732 boot served 57 MB in 0.2 s, then crashed after nnMain; patch0012
is the next device candidate. Preserve saves/import/settings/menu/locales and
existing JIT/helper/NativeAOT isolation rules. No game or key distributed.
Session owns all s2arm paths; common integration/pin/delivery remains main.
**Mario Kart World launch lot (maintainer request 13 Nov, session `01JA5QgNKffXiA5ZjCm4JEun`, lot branch
`claude/youthful-goldberg-4aphwq` `50924021`, merged into `Claude` for test delivery 734; see the Common IPA task).**
Input: IPA733 engine log of iPhone17,2 (`host.log` SHA-256 `ed432b17…`, diagnostics ZIP `d1eee787…`, preparation
journal `4c50a97a…`; private, not in Git). Finding: the window cannot hold the standard layout (75958 MB asked, hole
64512 MB), so 3 GiB stay to the host and every NVN virtual pool (`vpool_reserve` → `mmap(NULL)`) and every host stack
of a game thread (tail allocator has no range in that layout) is taken there: host hole 1717 → 5 MB, reservations
halved then refused (errno 12), 219 MapVirtual refusals, `pthread_create` rc=35, code 134, 0 frames.
Changes (engine patches, S2Arm pin `6b6a5715` unchanged): **0013** window gives up 2 GiB for the tail allocator and a
16 GiB virtual-pool arena below its base (`runtime/src/rb_vparena.c`; host 3 GiB, per-pool reservation and failure
paths unchanged); **0014** RomFS index written at first start with S2Arm's writer and a tree stamp (the 69 s directory
build of 205,058 files was paid at every launch); **0015** four later S2Arm commits taken unmodified after an audit of
its history up to `6bd0f402`: `240603b6` Switch 2 pool buffer address = storage CPU address (#351 crash before first
frame), `09e80022` host answers `nn::oe::SetGraphicsTargetFrameRate` (#679 abort after first frame), `81f8e8bd` +
`26465c45` GPU-time gate counts exclusive time and stops only on 3 frames over 1 s within 10 s (#647).
Checks executed: series 0001–0015 applies on the pin; arena compiled from the patch and run, 38 checks under
gcc/clang/ASan+UBSan; `s2arm_vp_arena_test` 34, `s2arm_romfs_index_test` 20, `s2arm_upstream_switch2_fixes_test` 17
checks (0015 equals the four commits line for line), 7/7 mutations detected; 13 other S2Arm tests and
`delivery_contract_memo_test` green; independent `rb-core-review` of 0013 found no definite bug (its release-length
hardening applied). **Compiled for iOS:** `s2arm-engine.yml` run `43365543093` attempt 1 on source `2a37382b`
(patches 0001–0015) succeeded on macos-26 and macos-15 with its entry-point and blocking licence-inventory checks;
framework artifact `14010462973` (`s2arm-engine-framework-2a373820…`, 23,931,392 bytes, digest `f076cd9f…`, expires
13 Dec). Earlier run `43364611467` (0013/0014, `7f81e84f`) also green; `s2arm-bridge-ios.yml` `43365546359` green on
the final source (the three new tests run on macOS). **Device: nothing observed; a green build does not show that the
game starts.**
Examined, no change: 16 GB written in 50 s = guest memory file backing (auto on, pool 9216 MB > 6128 MB room); the
rate (about 3.3 GB per 10 s) is constant from nnMain to the end in both sessions, the engine issues no sync and no
write at SetHeapSize (mprotect only), anonymous memory would exceed the process limit; whether it continues after
loading needs a device log. Nine `nn::codec` video decoder imports are not intercepted (only relevant if a movie
blocks after the first frame). Findings left to their owners: the engine reports the pin commit as build identity for
every patch level (`S2ACommit`, checked by `s2arm-engine.yml`), so logs do not name the patch level and the direct-mode
safety net's failure count carries over engine updates (2 now, prompt page at 3); the 12 Nov 21:06 session had XeniOS
threads alive in the process, an 8 GiB smaller hole and about 800 MB more footprint — only MeloNX is refused before a
Switch 2 launch. Rejected: upstream #783 learned-span window alone (span recorded only after 300 presents); `85da99de`
and `3fbde57c` (larger than a start needs).
Next: test delivery 734 with the pinned engine `8da9c21b…` (run `43416941344`) → from a cold app start the device
log must show `the window gives up 18432 MB`, `in the virtual pool arena`, no `errno 12`, frames > 0, and at the second
start `RewindBox: RomFS index read`.
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
worktrees and exact-source publication at that time. The former issue #179
handoff protocol is superseded by AGENTS.md; its old references are evidence only.
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
**Next / owner:** Codex executes the maintainer's new private delivery request, directly on Claude,
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

**Current maintainer request (13 Nov, later):** workflow simplified in AGENTS.md:
direct Claude work, no automatic issues/PRs/branches/worktrees, optional helpers,
short useful state updates. Removed mandatory issue179/ACK/Backup handoffs and
rb-code worktree isolation. Technical safeguards and existing delivery ownership
remain. Prior cleanup below is historical evidence, not an active procedure.

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

**Last verified common IPA: RewindBox733**, run `43353788677` attempt1,
source `b1955be5f6b80733ab6808a3bf875bad8eb459d0`, frozen `a4de734b`, effective `e2b4db5f`.
330,032,921 bytes, SHA-256 `e8e387fe5af258fbcbb44dfb21820ebcfaf697fa4694aa91e50c99ec20d66211`.
RPCS3 934, MeloNX745, XeniaCore c7d6a5c4, S2Arm9ddb304e;97 images,10 bundles,
six validators passed offline. Contract,Flutter and native host tests fresh;Core proofs reused.
Recipient key deleted after preserving12 proof files; private file delivered.
No new device performance/thermal claim. Public release remains separate.
[Manifest](../build-utils/delivery/733.json) · [receipt](evidence/rewind733/delivery.json).

## Findings to carry forward

Read only the relevant [archived findings](https://github.com/TarbleFR/RewindBox/blob/30ee5beb204a9c972f85c5e9cd249aa341887283/docs/AI_TASK_BOARD.md#findings-to-carry-forward)
and direct component evidence. Preserve rejected hypotheses and baseline attribution.

## Update a task in place

After a material result or blocker, keep a brief current state, evidence and next
action in the relevant entry. Preserve exact build/source identities when needed.
Read the latest version before writing and preserve others' updates. Do not append
a diary or require an issue/ACK. Historical evidence stays available in Git.

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

