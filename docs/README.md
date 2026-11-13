# RewindBox documentation

Start with the document for the question you need to answer. The only active working instructions are in AGENTS.md; dated reports preserve their original
evidence and are not additional instructions to build, publish or restore a feature.

## Active entry points

| Question | Authoritative entry |
| --- | --- |
| Working instructions and preserved technical evidence | [AGENTS.md](../AGENTS.md) → [preserved evidence](AI_TASK_BOARD.md) |
| Current public release and its exact source | [Public README](../README.md#build-from-source), then its linked manifest and receipt |
| Common private IPA preparation, freeze and delivery | [Standard delivery recipe](standard-delivery-recipe.md) |
| Component behavior and constraints | [Component rules](PROJECT_RULES.md), then the active task's direct evidence |
| Three branches and recovery of historical work | [Historical branch archive](https://github.com/TarbleFR/RewindBox/blob/1a734455b8162ed70c7cf8e7a7fc76f85e5af69e/docs/branch-archive.md) |
| Engine build acceleration | [Producer caches](engine-build-caches.md) |
| Optional app build acceleration | [Encrypted host cache](ipa-incremental-build.md) |
| Current Actions history triage | [Reviewed cleanup scope](actions-history-triage-2026-11-13.md) |

Producer caches accelerate the engine workflows that supply verified components;
the encrypted host cache accelerates the standard IPA recipe. Both preserve their
existing verification boundaries and final delivery checks.

## Historical records

| Record | How to use it |
| --- | --- |
| [Instruction snapshots and index](history/README.md) | Read the dated decision and its exact source; active instructions remain in AGENTS.md; historical results are evidence only. |
| `build*.md`, `rpcs3-core*.md`, `melonx-*.md` and delivery receipts under `evidence/` | Treat build numbers, “pending”, “current” and next actions as statements at that source/date. Follow them only when the active task explicitly selects that work. |
| [606 delivery recipe](rewind606-delivery-recipe.md) | Historical producer verification; do not trigger an old launcher for a new common IPA. |
| [NeoPlay prototype](neoplay/README.md) and [Build397](neoplay/BUILD397.md) | Historical prototype/branch instructions, not a current remote-branch or build request. |
| [Source-access record](SOURCE_CODE_ACCESS.md) and [legal/credits record](LEGAL_AND_CREDITS.md) | Their version labels describe older releases. Use the public README's exact release manifest for current source identity; preserve all applicable attribution and license obligations. |
| [RELEASE_NEXT](RELEASE_NEXT.md) and [its license review](RELEASE_NEXT_LICENSE_REVIEW.md) | Already historical release snapshots despite the filenames; they do not define the next private IPA. |

Preserve source/legal notices, failed-attempt evidence and hash-bound records.
Do not delete or move them merely because their build is old. Correct active
navigation and conflicting instructions in place, without rewriting past results.
