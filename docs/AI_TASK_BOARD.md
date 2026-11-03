# RewindBox iOS — AI task board

**Owner of substantive coding and integration: Claude Code.** ChatGPT/Codex coordinates/reviews; Cursor helps with low-risk or non-overlapping tasks only. For roles and billing protections, see [AI_ORCHESTRATION.md](AI_ORCHESTRATION.md). The authoritative repository rules remain in `AGENTS.md`.

This board is *not* an automatic queue. No user feature task has been assigned by creating this file. Only add tasks when asked, and distinguish proposals from approved work.

## Active tasks

| ID | Task | Owner | Status | Exact scope | Latest verified HEAD | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| — | No feature task delegated during orchestrator setup | — | Not started | — | Check actual Git HEAD | Await user's next development request |
| TASK-586 | Private IPA 586: delivered 585 (RPCS3 Core 585) + MeloNX engine `ac16f1c5` + Cheats & Enhancements page and catalogues (maintainer: "tout dedans", 28 Oct 2026) | Claude Code (session 01K9YJtz) | In progress | Recipe `melonxalloc586_*` on top of the `rpcs3cell585_*` recipe; engine files of `6314127f`/`d8cd5f68`/`ac16f1c5`; enhancements files at `c9b42115`. Build number 586 reserved; other agents please do not reuse it. | `2b08899d` | Dispatch after the 585 delivery succeeds |
| TASK-587 | RPCS3 Core 587: MoltenVK asynchronous submits made safe (encode barrier before each acquisition, MetalFX ordering, boot canary), Automatic for God of War III; profile: God of War III async Automatic, Black Ops II relaxed SPU reservations. Shipped by TASK-586 (maintainer: no separate 587 IPA) | Claude Code (session 01BcZDeV) | Core done | Core run 40718679248 green (a8a7ce10, Core c638d4ce…); profile 147af30e; binding module a695ab43; Mac evidence 7c3c48d2. Build number 587 not used for an IPA | `7c3c48d2` | TASK-586 recipe swaps Core 585 for Core 587 |
| TASK-589 | RPCS3 Core 589: Assassin's Creed (BLES00158, BLUS30089) joins texture validation per FIFO batch (559) and scoped revalidation (573); profile: Assassin's Creed relaxed SPU reservations. From the build 585 logs of 28 Oct 2026 | Claude Code (session 01BcZDeV) | Core done | Record `cell589` (three iOS files), `test/rpcs3_cell589_test.py`, Core recipe `rpcs3cell589_core.py`; profile in `lib/services/rpcs3_game_profile_service.dart`. Build number 589 reserved for this Core; no IPA yet (maintainer: no IPA for a lever alone). Core run 40778765122 green (Core 49fed8c0…), binding module 700db78 | `700db785` | Swap Core 589 into the next delivery from the 586 baseline |
| TASK-628-RPCS3 | Put RPCS3 Core 627 into private IPA 628, next to MeloNX Core 628 (maintainer, 3 Nov 2026, 10:52 Paris: "fais rentrer le core dans l'ipa 628") | Claude Code session 01JA5QgK (MeloNX/Hogwarts), integration owner | Done: shipped in private IPA 629 instead (the maintainer chose 629 with both Cores; 628 was not delivered). Both Core 627 artifacts verified offline with rpcs3_core_component.pin_errors and bundle; pinned in `021a15e4`; delivered and recorded (run `41622115556`, IPA `952b2641…`) | Core run `41610162888` attempt 1, source `6891f9a055eff7ee81a491da4aafdb68f1f63ffc`: Core job `125829758140`, artifact `13219702266`, 29336809 bytes, `sha256:3f9459517cd104819d53d25088e22c6009a8e0090457dc7c005423da28a4b912`; Apple host tests job `125829758604`, artifact `13219121710`, 39209 bytes, `sha256:d76cd56132bce75bec9a94fc8c84f7d29b5a009ee2b1cfe821d85dd9841abd27`. Both jobs green. Host sources changed too (`packages/rpcs3_internal_bridge/ios/Classes/`: test page rows). No device result, no FPS claim ([record](rpcs3-core627-2026-11-03.md)) | `021a15e4`, `79d866ef` | None for the pin. The first 629 attempt failed at the RPCS3 install check (canary file renamed by Core 627); recipe fix `79d866ef`. Next: the iPhone canary run of Core 627 (900 frames or a clean stop, OPT587 confirmed=1) |

| TASK-631-MELONX | Private IPA 631: Hogwarts Legacy at 1x, draw encoding CPU time 30-40 % lower at equal rendering, from the 629 logs (maintainer, 3 Nov 2026). Build number 631 reserved for this MeloNX Core and its IPA; other agents please do not reuse it (630 is the RPCS3 Core) | Claude Code session 012mUAShcohnGpWDhRJYNT6Q | In progress: sources, tests and plan written (`EncodingPolicy`: template scratch sized by binding, texture arrays written by changed range; four gates rerun on the final source); not frozen, no Core CI, no IPA (.NET SDK, NuGet and artifact storage still refused at 13:28 UTC). Next limit after 631 analysed in `docs/melonx-629-encoding-2026-11-03.md`: MoltenVK 1.4.0 walks the 524 288-element arrays per encoder on iOS. Maintainer's agreement (3 Nov, 14:40): MoltenVK 1.4.0 rebuilt from Khronos source with the RewindBox argument buffer usage patch (`docs/melonx-moltenvk-rebuild-2026-11-03.md`, patch and build script pushed; its workflow awaits the maintainer's go-ahead, the first push being refused by the session's permission check); not compiled, not packaged, not measured | `build-utils/melonx/adapt_host_qos_pipeline_budget.py`, `adapt_hogwarts_dma_copies.py`, `dma-core-plan.json`, `verify_dma_core.py`, the DMA, scalar-texture, fallback-scratch, single-resource, bounded-snapshot tests, `test/melonx_array_descriptor_ranges*`, `tools/melonx/frame_report.py` ([record](melonx-629-encoding-2026-11-03.md)) | the commit that adds this row | Blocked here: no NuGet, .NET SDK or Actions artifact access in this session. With access: local gate run, freeze, Core CI, pin (with `FRESH_GATES = 10` in the component verifier), delivery 631 |

## Task entry template

### TASK-XXX — concise feature/bug title

- **User approval and objective:** Exact requested outcome; what is not authorized.
- **Owner:** Claude Code (main coding) / ChatGPT (research or review) / Cursor Agent (safe auxiliary task).
- **Complexity / quota routing:** No agent / Lightweight / Claude required; why.
- **Files and ownership:** Concrete paths; no concurrent editors of same files.
- **Starting point:** Verified branch `Claude` and exact HEAD, with local/uncommitted status.
- **Dependencies:** Prior task, permissions or assets.
- **Definition of done:** Observable behavior and acceptance checks.
- **Tests:** What was run and what remains; don't rerun unaffected suites.
- **Progress:** Proposed / Approved / In progress / Blocked / Review / Done.
- **Handoff:** Link to `docs/AI_HANDOFF.md`, changed paths, commit SHA if actually committed, next safe step.
- **Build/release:** Explicit user authorization required; never automatic.

## Routing examples (illustrative, not assigned tasks)

- Examine a new HD texture source and attribution: **ChatGPT research** → **Claude Code implementation**.
- Locate where a Flutter label is translated: **Cursor lightweight research** → **Claude Code or narrowly authorized Cursor change**.
- Investigate a reproducible RPCS3 crash: **ChatGPT diagnosis from internal logs** → **Claude Code native fix** → **Codex independent review**.
- Release build: **Claude owns source readiness**, separate user authorization for GitHub Actions; no release unless requested.
