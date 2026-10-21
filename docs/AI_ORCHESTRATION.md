# RewindBox iOS — three-assistant coordination

**Maintainer's non-negotiable decision (2026-10-21): Claude Code remains the principal coder.**

This process coordinates **Claude Code (Claude Max 20x)**, **OpenAI Codex / ChatGPT (ChatGPT subscription)**, and the **native Cursor Agent (Cursor subscription)**. It does not change the repository's authoritative `AGENTS.md` rules or grant autonomy to initiate payments, release builds or pushes.

## Roles, in priority order

| Agent | Primary responsibility | Coding permissions |
| --- | --- | --- |
| **Claude Code — principal coder** | Software architecture, native emulators (RPCS3, ARMSX2, Dolphin, MeloNX, Libretro), nontrivial Flutter implementation, integration and complex debugging | First choice for substantive code changes and final integration |
| **ChatGPT / Codex — coordinator and independent reviewer** | Break down tasks, compare strategies, inspect licenses, prepare prompts, reason about logs, review diffs, identify regressions and propose targeted tests | Read-only by default; focused fixes only when the maintainer explicitly delegates them |
| **Cursor Agent — lightweight helper and fallback** | Search the codebase, summarize files, translate/document, inspect tests and safely work on isolated small changes when requested | Small scoped edits only on explicit instruction; pause for Claude review on complex code |

**The maintainer remains the final authority.** ChatGPT can propose a plan and use connected GitHub tools, but cannot automatically invoke Claude Code or Cursor Agent using their subscription allotments. An IDE extension or manual launch is required for each agent. No agent is permitted to bypass a usage limit with an API key.

## Work routing: minimize resource use

1. **No agent required:** Answer short questions from existing evidence, do lightweight documentation planning, and reuse already validated results.
2. **ChatGPT first (planning/research):** Scope a request, search sources, compare licenses, read logs, produce a concise implementation brief and identify exact relevant files. Codex may independently review changes if appropriate.
3. **Cursor native Agent (low/medium effort):** Locate symbols, summarize code, prepare translations or small independent changes, provided its included plan quota allows the chosen model. Prefer a Cursor-included non-Claude/non-GPT model; don't use third-party models that consume prepaid credit.
4. **Claude Code (principal coding):** Assign actual feature work, emulator/native integration, delicate refactors, performance work, and final application-level integration to Claude. Give it the scoped brief rather than asking it to rediscover everything.
5. **Codex / ChatGPT final check:** Review diffs and relevant tests independently, and return findings to Claude for correction. Don't have a second agent rewrite the same in-progress implementation.
6. **If Claude is rate-limited:** Pause the complex coding task. Cursor or Codex may help with *non-overlapping* analysis, tests or narrowly approved low-risk edits; when Claude resumes, it remains implementation lead.

Start with **one agent** unless an independent review is justified. Two or three parallel reasoning agents can cost *more* quota than one; parallelize only truly independent read-only tasks.

## Subscription and cost protection

- **Claude Code**: use the official Anthropic extension and **Sign in with Claude Max**, not an `ANTHROPIC_API_KEY`. Its usage is part of Claude Max's included limit.
- **OpenAI Codex**: use the official `OpenAI.chatgpt` extension and **Sign in with ChatGPT**, not **Use API Key**. Its usage is part of the ChatGPT subscription's applicable Codex limits.
- **Cursor native Agent**: use its included Cursor models (e.g., a Grok/Composer option available in the plan), *not* a Claude or GPT third-party model unless the maintainer explicitly accepts possible prepaid credit usage.
- Keep additional usage credits and auto-top-up **off**. Do not create API keys, add payment methods, raise payment limits or enroll in pay-as-you-go.
- Subscriptions still have their own usage quotas. **No automatic switching at a quota threshold** is implemented or claimed.

## Task tracking and approvals

Use [AI_TASK_BOARD.md](AI_TASK_BOARD.md) to record specific tasks *only when requested*. A task entry identifies owner, scope, files, acceptance criteria, status and handoff references. The task board is a coordination record, not an autonomous scheduler.

When moving a task from one agent to another:
1. Read `AGENTS.md`, `ARCHITECTURE.md`, [AI_HANDOFF.md](AI_HANDOFF.md), this document and the actual `git status`/`HEAD`/diff.
2. Stop writes from the previous agent. Record uncommitted work accurately; do not assume GitHub has local edits.
3. Ensure the next agent works against the *same actual branch* (`Claude`). Do **not** invent additional AI work branches: the maintainer's existing rule takes precedence.
4. Assign one narrowly scoped action. Avoid simultaneous writes to a shared working tree, the same file, or the handoff record.
5. Once finished, provide exact changed paths, tested/not-tested status, commit SHA (if any) and remaining action. Route meaningful application integration back to Claude.

## Hard stops

- No change to `main`, `backup` or baseline refs without explicit authorization.
- No automatic `git push`, merge, force push, `reset --hard`, `clean`, IPA/CI build, release or tag.
- Reuse validated tests where unaffected; run targeted checks for changed components.
- Preserve notices, legal attribution, localization in the application's supported languages and stable iOS compatibility identifiers.
- On Windows, do not claim iOS IPA build success. Use an approved macOS/Xcode or GitHub Actions job *only on explicit request*.

## Useful prompts

**ChatGPT coordination**

> You are coordinating RewindBox iOS. Claude Code is the principal coder. Read the project rules and actual Git state. Split my request into: research/review for ChatGPT, simple safe tasks for Cursor if needed, and the main implementation for Claude. Return exact file scope, dependencies, acceptance checks and handoff steps. Do not launch or bill other agents without my approval.

**Claude Code principal development**

> You are the principal coder for RewindBox iOS. Read AGENTS.md, CLAUDE.md, docs/AI_ORCHESTRATION.md, docs/AI_TASK_BOARD.md, docs/AI_HANDOFF.md and the current Git diff. Review the scope and do the main implementation only for the user-approved task, preserving prior work and branch policy.

**Cursor light assistance**

> Read AGENTS.md, docs/AI_ORCHESTRATION.md, docs/AI_HANDOFF.md and Git status. Claude remains principal coder. Identify only lightweight independent work that will not overlap Claude's files. Analyze before editing; do not push, build, or use paid model credits.

**Codex independent audit**

> Read AGENTS.md and docs/AI_ORCHESTRATION.md, inspect current Git diff, and independently review the active feature for correctness, regression risk and missing targeted checks. Return findings for Claude; do not modify code or start a build.
