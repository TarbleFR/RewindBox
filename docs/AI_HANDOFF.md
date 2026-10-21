# RewindBox iOS — AI task handoff

This is the shared, **human-readable** task handoff for Claude Code, ChatGPT/Codex and the native Cursor Agent. It is not a chat transcript or a replacement for `AGENTS.md`. Update **only when a handoff is requested**; the author must distinguish verified results from assumptions.

## Current handoff

- **State:** Setup only — no active feature task was handed off during initial configuration (2026-10-21).
- **Incoming agent:** Not assigned.
- **Branch:** `Claude` (verify at the moment of takeover).
- **HEAD:** Not pinned; run `git rev-parse HEAD` at takeover.
- **User's objective:** Not specified for a feature task yet.
- **Last completed work:** Added cross-agent instructions and handoff documentation only.
- **Changed code files:** None for this setup.
- **Local uncommitted changes:** Unknown until the local checkout is inspected.
- **Validation/tests:** No Flutter or iOS tests run; documentation-only setup.
- **Known blockers:** Cursor subscription activation may still be pending; the Claude Code extension uses the Claude Max quota and cannot bypass its limits.
- **Next safe action:** Read `AGENTS.md`, run `scripts/ai-context.ps1` on Windows if available, review Git diffs, then ask the user for the specific feature or bug to resume.

## Replace this section during each real handoff

Copy/fill the following fields under `Current handoff`; do not erase history or claim an unverified test passed.

| Field | Accurate current information |
| --- | --- |
| Date/time | YYYY-MM-DD HH:mm timezone |
| Outgoing / incoming agent | Claude Code / Cursor Agent / ChatGPT-Codex, outgoing → incoming |
| Task and desired outcome | ... |
| Current branch and exact HEAD | ... |
| Local changes and modified file paths | ... |
| Commits pushed to GitHub (if any) | ... |
| Uncommitted or unpushed work (if any) | ... |
| Last verified working state | ... |
| Tests completed and tests **not** run | ... |
| Risks, license constraints, unknowns | ... |
| Next **single safe action** | ... |
| Actions requiring maintainer approval | ... |

## Handoff checklist

1. **Outgoing agent:** Stop editing. Record the task state and exact file/commit references. Do not push or build without authorization.
2. **Incoming agent:** Read `AGENTS.md`, this file and the working diff. Run `git status --short`, `git branch --show-current` and `git log -3 --oneline`. Do not assume GitHub contains local uncommitted work.
3. **Before edits:** Compare the last stated HEAD to the current one and identify overlap with another agent. If the handoff is incomplete because Claude hit a usage limit, reconstruct verifiable changes and ask the user for the missing original request.
4. **Finish:** Record what changed, what was tested, what remains, and whether anything was pushed or built. Never claim that a Git commit produced an IPA.
