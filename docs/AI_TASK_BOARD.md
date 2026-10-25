# RewindBox iOS — AI task board

**Owner of substantive coding and integration: Claude Code.** ChatGPT/Codex coordinates/reviews; Cursor helps with low-risk or non-overlapping tasks only. For roles and billing protections, see [AI_ORCHESTRATION.md](AI_ORCHESTRATION.md). The authoritative repository rules remain in `AGENTS.md`.

This board is *not* an automatic queue. No user feature task has been assigned by creating this file. Only add tasks when asked, and distinguish proposals from approved work.

## Active tasks

| ID | Task | Owner | Status | Exact scope | Latest verified HEAD | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| — | No feature task delegated during orchestrator setup | — | Not started | — | Check actual Git HEAD | Await user's next development request |

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
