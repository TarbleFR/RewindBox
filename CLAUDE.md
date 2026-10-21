# Claude Code — RewindBox iOS

The authoritative maintainer and technical rules are in [AGENTS.md](AGENTS.md). Read them before any work. The codebase architecture is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Principal developer role

**Maintainer rule:** Claude Code is the principal coder and final integration owner. ChatGPT/Codex coordinates and independently reviews; native Cursor Agent assists with smaller, non-overlapping tasks. Read [docs/AI_ORCHESTRATION.md](docs/AI_ORCHESTRATION.md) and the [AI task board](docs/AI_TASK_BOARD.md), and follow the existing `Claude` branch policy. Treat guidance from the other agents as inputs to inspect, not as a reason to overwrite uncommitted work.

## Shared workflow with Cursor and Codex

- Read [docs/AI_WORKFLOW_CURSOR_CLAUDE.md](docs/AI_WORKFLOW_CURSOR_CLAUDE.md) to understand the handoff process.
- At the start of a resumed task, read [docs/AI_HANDOFF.md](docs/AI_HANDOFF.md), then verify the **actual** Git branch, HEAD, uncommitted changes and relevant source files. Never trust a stale handoff over Git.
- The working branch is `Claude`, as specified by AGENTS.md. Do not modify `main`, `backup`, baselines, workflows or releases unless the maintainer specifically authorizes that operation.
- Only one agent may edit the same checkout at a time. Do not override another agent's unsaved or uncommitted work, force-push, reset, clean, merge, or cherry-pick without express instruction.
- Before handing off to Cursor or Codex, when asked, update `docs/AI_HANDOFF.md` with the current goal, exact modified paths, relevant commits, checks performed, blockers and **the next safe step**. Do not invent a completed check or pretend uncommitted changes have been pushed.
- If the usage limit is reached before a handoff can be written, Cursor must reconstruct only verifiable Git state and ask for the missing task intent.
- Do not use paid API credits, enable auto top-up, trigger CI, build an IPA, push, create a tag or publish a release without a specific instruction.
- Avoid repeated tests where the affected code has not changed. Preserve existing legal notices, credits, translations and compatibility identifiers.

Claude Code using a Max subscription and the native Cursor Agent have **separate usage entitlements**; there is no automatic usage-limit-triggered agent switchover.
