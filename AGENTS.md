# RewindBox — simple working rules

These rules replace older orchestration instructions. Follow the user's current
request first. Read only the relevant task and technical requirements in
[docs/AI_TASK_BOARD.md](docs/AI_TASK_BOARD.md), then the needed source/evidence.

1. **Work directly on `Claude` (exact case).** Inspect branch, HEAD and local changes,
   then synchronize safely. Ordinary fast-forward commits/pushes to `origin/Claude`
   are authorized; use `[skip ci]` for documentation-only changes.
2. **No automatic branches, worktrees, issues or PRs.** Create them only when the
   user explicitly requests them. Never recreate deleted issues/branches.
   `main` stays the reference branch; `Backup` preserves existing archives.
   Neither is a routine handoff route. Never merge Backup into a product branch.
3. **Preserve work.** No force-push, destructive reset/clean or unreviewed deletion.
   Stage only owned changes. Before pushing, reconcile newer remote commits.
   Serialize edits to shared paths; use sequential work when ownership conflicts.
4. **Keep coordination light.** The current session executes the requested work.
   Use a helper only for a useful bounded question or explicitly assigned paths;
   no automatic team or isolation. One active executor per Core/IPA delivery:
   follow the existing run instead of launching a duplicate.
5. **Correct → verify → deliver within the approved scope.** Use existing evidence,
   fix the cause, run relevant checks and report the result in French. Preserve
   component requirements, data, signatures and source/artifact validation.
   Existing build authorizations remain valid; use the standard delivery recipe.
   A documentation change alone is not a request to build an IPA.
6. **Record only what helps continuation.** Update the relevant board entry after
   a material result/blocker, preferably with the work's commit. A short state,
   evidence and next action suffice. No mandatory issue, ACK, session lookup,
   model/effort ceremony or standalone bookkeeping commit for routine progress.

If the environment itself forces a session branch or refuses a direct push,
state that exact restriction; do not bypass it or repeatedly ask for an already
granted authorization. Do not publish a `claude/...` branch: its first component
collides with `Claude` on case-insensitive macOS checkouts. Preserve existing work
and use direct `Claude` access only where the environment permits it.
