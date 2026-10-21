# RewindBox iOS — Claude Max 20x ↔ Cursor workflow

## Purpose

Use **Claude Code** as the primary coding assistant and **Cursor's native Agent** as an independent fallback when Claude's included usage is exhausted. Both agents operate against the **same RewindBox checkout**, on the existing `Claude` branch. This is a *manual* handoff: neither product automatically transfers chat history or switches agents when usage is exhausted.

## Accounts and usage

- Install the **official Anthropic Claude Code** VS Code/Cursor extension (`Anthropic.claude-code`). Sign in with the maintainer's **Claude Max** account; an Anthropic API key is not required. The Claude Code extension usage shares the Claude Max allowance.
- When Claude reaches its limit, **switch to Cursor's built-in Agent**, with an available **non-Claude model** from Cursor's own model picker. That Agent consumes the Cursor account's separate included quota or its applicable pay-as-you-go billing rules; verify account status before relying on paid features.
- Selecting a Claude model inside native Cursor Agent is *not* the same as logging into the Claude Code extension with Claude Max. Do not assume Claude Max grants usage in Cursor's model picker.
- Do not configure an Anthropic API key, extra Claude credits, payment method or auto-top-up for this fallback unless separately requested.

## One local workspace on Windows

1. Open Cursor and clone `https://github.com/TarbleFR/RewindBox.git` to an accessible local directory if it is not already cloned. If it is, use **File → Open Folder**.
2. Use the existing `Claude` branch, **only when the checkout is clean or local changes have been reviewed**:

   ```powershell
   git fetch origin
   git status --short
   git branch --show-current
   git switch Claude
   git pull --ff-only origin Claude
   ```

   Do not run `git switch` or pull over a dirty checkout without examining changes; never reset, force push or create another AI branch to bypass a conflict.
3. Cursor reads `AGENTS.md` and `.cursor/rules/rewindbox-handoff.mdc`. Claude Code reads `CLAUDE.md`. Both should read `docs/AI_HANDOFF.md` when taking over an existing task.
4. For a concise, **read-only** Git summary on Windows, run `powershell -ExecutionPolicy Bypass -File scripts/ai-context.ps1` from the repository root. This does not transfer a chat transcript or publish anything.

## Transfer Claude → Cursor when Claude is limited

1. Stop Claude's active edits. If possible, ask Claude to write an accurate handoff in `docs/AI_HANDOFF.md` before its session ends. If Claude is already blocked, preserve the last user task and let Cursor reconstruct *verifiable* local state.
2. In the **native Cursor Agent**, choose an available non-Claude model. Start in read-only/Ask mode: `Read AGENTS.md, ARCHITECTURE.md, docs/AI_HANDOFF.md, and the working Git diff; summarize the current task and next safe action. Do not edit, commit, push or build yet.`
3. Verify the summary and authorize the limited task. Switch to Agent mode to implement. Do not run both agents against the same files at the same time.
4. When finished, update the handoff with file changes and tests. Ask for explicit approval before push, CI build, or release publication.

## Transfer Cursor → Claude

1. Stop Cursor's edits and update the same handoff file with the current task, changed files, local-only work, validated tests and pending steps.
2. Open Claude Code in the **same checkout** once its usage resets, and prompt it to read `AGENTS.md`, `CLAUDE.md`, `docs/AI_HANDOFF.md` and the working diff before continuing.
3. Never use `git reset --hard`, `git clean`, force push, silent cherry-picks, or merges to resolve a mixed agent workspace.

## iOS builds and release safety

Windows is suitable for navigation, code edits and available Flutter checks. Actual signed/unsigned iOS IPA compilation requires Xcode on macOS (e.g. an approved GitHub Actions macOS runner). Do not trigger a build, publish an IPA, change branch protections, or create a GitHub Release as part of a handoff unless the maintainer asks.

## Quick prompts

**Cursor takeover:**

> I'm continuing RewindBox after Claude Code reached its quota. Read AGENTS.md, ARCHITECTURE.md, docs/AI_HANDOFF.md, and inspect the local Git diff, branch and last three commits. Identify verified progress, uncommitted work and the smallest next step. Start read-only; do not edit or push until I give the specific task.

**Claude takeover:**

> I'm resuming RewindBox after Cursor Agent. Read AGENTS.md, CLAUDE.md, docs/AI_HANDOFF.md and the local Git changes. Reconcile the current branch and files with the handoff. Explain what is already complete and the next safe step before modifying anything.
