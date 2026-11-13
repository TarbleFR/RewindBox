# RewindBox — agent entry point

Read the [shared requirements and results](docs/AI_TASK_BOARD.md) before work.
It is the sole working contract for Claude Code, Codex and Cursor, including
permanent rules, current tasks, positive and negative results, input identities,
evidence references and the verified delivered baseline.

Inspect actual branch, HEAD and working diff. Read only the applicable shared
rules and task, then its direct evidence and source. Preserve concurrent work.
Update the shared contract after meaningful results and before ending,
compacting or handing off. Correct a permanent instruction when its meaning
changes. Maintain one record in place and use the existing detailed proofs.

## Branches and cross-account handoff (maintainer, 13 November 2026)

Only `main`, `Claude` and `Backup` are durable remote branches. Do not recreate
archived work branches automatically. Keep uncommitted/local work intact and use
local worktrees for isolation. Before publishing an unfinished lot, preserve its
commit as a parent of a new fast-forward Backup archive commit and record its
owner/source in the archive index and the shared handoff issue #179. Preserve the
previous Backup HEAD as a parent. Never merge Backup into a product branch.

Read `docs/branch-archive.md` and issue #179 before resuming an archived task.
Main owns reviewed integration into Claude. Use exact-SHA handoffs and ACKs on
issue #179; never wait indefinitely for a private session ID unavailable to the
other account. The board remains the task/ownership contract. Deleting a remote
branch never licenses removal of local uncommitted work or a new unarchived head.
