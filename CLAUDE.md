# Claude Code — RewindBox iOS

The authoritative maintainer and technical rules are in [AGENTS.md](AGENTS.md). Read them before work in a new session; reread changed sections when their revision changes. Use only the relevant section of [ARCHITECTURE.md](ARCHITECTURE.md) when navigating an unfamiliar component.

## Work efficiently: evidence, correction, verification

- Start with the current user objective and actual Git state. Find the component
  in [the evidence index](docs/AI_EVIDENCE_INDEX.md), then read its latest relevant
  record and the source it describes. The index is a locator, not a task queue.
- Do not load the whole documentation/history/log tree or repeatedly reread
  unchanged instructions. Search names/symbols with `rg --files` / `rg -n`, then
  read bounded sections. Batch independent reads and preserve useful results.
- Before reopening a diagnosis, name the new evidence: a changed source/build,
  new log, contradicted result or previously untested path. With none, use the
  recorded finding and implement the next authorized correction or verification.
- Give each diagnostic command one question and a decision it will enable.
  After two inconclusive attempts at the same question, change the hypothesis,
  inspect the direct caller/callee or state the exact blocker; do not loop through
  equivalent commands. This limits repetition, not the investigation of complex bugs.
- Keep a short record in the existing component document: input identity,
  confirmed/rejected finding, patch, tested source, command/result and next step.
  Use [the diagnostic protocol](docs/AI_DIAGNOSTIC_PROTOCOL.md) when debugging.
  Update that record after a meaningful result, not after every tool call.
- Move from established cause to the smallest supported correction. Run affected
  behavioral checks; reuse successful checks only when all their inputs still
  match. Token savings never justify skipping a necessary test or inventing gains.
- Use one coding agent by default. Do not start teams, repeated full audits,
  quota polling or automatic external research for routine local changes.
  Preserve the existing coordination and spending permissions below.
- Report the outcome, evidence, limitation and next step concisely in French.
  Distinguish source changed, compiled, delivered and observed on an iPhone.

## Compact instructions

When compacting, preserve the active user request and permissions, branch/HEAD,
owned dirty files, relevant record paths, exact input/build/log identities,
confirmed and rejected hypotheses, patch status, test results with their inputs,
environment blockers and the next concrete action. Drop raw repetitive output
and old narrative; never drop unresolved failures or safety constraints.

## Principal developer role

**Maintainer rule:** Claude Code is the principal coder and final integration owner. ChatGPT/Codex coordinates and independently reviews; native Cursor Agent assists with smaller, non-overlapping tasks. Read the relevant role/approval sections of [docs/AI_ORCHESTRATION.md](docs/AI_ORCHESTRATION.md) and only the [task-board entry](docs/AI_TASK_BOARD.md) for the current request; follow the existing `Claude` branch policy. Treat guidance from the other agents as inputs to inspect, not as a reason to overwrite uncommitted work.

## Shared workflow with Cursor and Codex

- Read [docs/AI_WORKFLOW_CURSOR_CLAUDE.md](docs/AI_WORKFLOW_CURSOR_CLAUDE.md) when performing a handoff, rather than loading that procedure for every code change.
- At the start of a resumed task, read [docs/AI_HANDOFF.md](docs/AI_HANDOFF.md), then verify the **actual** Git branch, HEAD, uncommitted changes and relevant source files. Never trust a stale handoff over Git.
- The working branch is `Claude`, as specified by AGENTS.md. Do not modify `main`, `backup`, baselines, workflows or releases unless the maintainer specifically authorizes that operation.
- Only one agent may edit the same checkout at a time. Do not override another agent's unsaved or uncommitted work, force-push, reset, clean, merge, or cherry-pick without express instruction.
- Before handing off to Cursor or Codex, when asked, update `docs/AI_HANDOFF.md` with the current goal, exact modified paths, relevant commits, checks performed, blockers and **the next safe step**. Do not invent a completed check or pretend uncommitted changes have been pushed.
- If the usage limit is reached before a handoff can be written, Cursor must reconstruct only verifiable Git state and ask for the missing task intent.
- Do not use paid API credits, enable auto top-up, trigger CI, build an IPA, push, create a tag or publish a release without a specific instruction.
- **Standing push authorization (maintainer decision, 1 November 2026):** Claude Code does not ask again before pushing its own commits from `Claude` to `origin/Claude`. Push only as a fast-forward: if the remote moved, first rebase only your own unpushed commits onto `origin/Claude`, then run `git push -u origin Claude`. Never force-push and never push another branch. Commits keep `[skip ci]` unless the maintainer asks for a CI run. This covers nothing else: CI runs, IPA builds, tags, releases, `main` and `backup` still need a specific instruction. It is the explicit authorization that the push hard stop in [docs/AI_ORCHESTRATION.md](docs/AI_ORCHESTRATION.md) asks for, and it applies to Claude Code only. The session's own permission checks still apply: if one refuses the push, report it instead of working around it.
- Avoid repeated tests where the affected code has not changed. Preserve existing legal notices, credits, translations and compatibility identifiers.

Claude Code using a Max subscription and the native Cursor Agent have **separate usage entitlements**; there is no automatic usage-limit-triggered agent switchover.
