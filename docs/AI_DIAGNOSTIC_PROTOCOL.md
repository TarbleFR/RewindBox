# RewindBox — diagnose once, advance on evidence

This protocol supplements AGENTS.md. It does not authorize builds, pushes,
payments, releases, other agents or changes outside the user's request.

## Resume without restarting the investigation

1. Inspect branch, HEAD, dirty paths and current user intent. Preserve ownership.
2. Use AI_EVIDENCE_INDEX.md to find the latest relevant component record. Read
   its findings and direct evidence, not every historical report it links.
3. Compare the build/log/source identities. Carry forward established findings
   and rejected hypotheses only within the conditions that actually proved them.
4. State a short working decision: known fact, what changed, next patch or check.
   If enough evidence exists, implement the authorized correction now.

## A reason is required to reopen a finding

Valid reasons include a new installed build, changed relevant source or inputs,
a new log contradicting the finding, a different game mode/region, or an untested
caller/lifecycle path. "New session" or "might be worth checking again" is not
new evidence. An inconclusive result remains inconclusive; it is not a rejection.

For each command, identify the question, expected evidence and resulting action.
Use file discovery and narrow searches before broad reads. Read bounded journal
windows with their run boundaries; retain the original file/identity. Keep full
output in the existing evidence location when necessary and summarize only the
decisive lines. Do not hide failures by truncating the only retained output.

After two attempts that fail to distinguish the same hypotheses, change the
method or identify the missing input. Do not add speculative patches to make
an unmeasured outcome look complete. Missing downloads/toolchains block their
dependent step, not unrelated code review or useful local checks. Never retry an
approval refusal through another route to defeat it.

## Keep the existing component record actionable

After a meaningful result, update the relevant record in place. Do not generate
a second diary with conflicting status or rewrite another session's live notes.
Use a compact section like this; expand only where the evidence needs it:

| Field | Required information |
| --- | --- |
| Input identity | Exact source/build; game ID/region/revision and mode when relevant; log name/digest and run boundary |
| Finding and confidence | Confirmed / rejected / hypothesis / inconclusive, with direct evidence reference |
| Conditions and rejected attempts | Where the result applies; what failed and why it should not be repeated unchanged |
| Correction | Exact changed paths/commit and connection to the observed cause |
| Verification | Command, result, tested input/tool/dependency identities; fresh / reused / not run |
| Next action or blocker | One concrete step; exact missing prerequisite and condition for retry |

Do not store credentials, recipient private keys or full private player logs in
instruction files. Link to an appropriately handled evidence file instead.
Only a genuine handoff request updates AI_HANDOFF.md; this protocol does not
turn its historical entry or the task board into an automatic work queue.

## Preserve progress across compaction

Save the decisive result to its component record before a long pause. Preserve
the current objective, permissions, file ownership and next action in the compact
summary. On resume, verify what changed since that checkpoint; do not replay all
commands. End with changed behavior, verification, remaining uncertainty and the
next concrete action, not a transcript of the investigation.

## Configuration boundaries

CLAUDE.md is session-start guidance. The diagnostic rule in `.claude/rules/`
is path-scoped so documentation-only work need not load its code-work details.
These files guide Claude; they do not enforce a token cap or guarantee compliance.
No subscription, model, thinking budget, global memory or account setting is
changed by this configuration. After syncing this branch, start a new Claude Code
session in the checkout and use `/memory` to check its loaded instructions. Use
`/usage` to observe actual usage; no percentage saving is claimed from file size.

References checked 3 November 2026:
- https://code.claude.com/docs/en/memory
- https://code.claude.com/docs/en/costs
