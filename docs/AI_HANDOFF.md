# RewindBox iOS — AI task handoff

This is the shared, **human-readable** task handoff for Claude Code, ChatGPT/Codex and the native Cursor Agent. It is not a chat transcript or a replacement for `AGENTS.md`. Update **only when a handoff is requested**; the author must distinguish verified results from assumptions.

## Current handoff

| Field | Accurate current information |
| --- | --- |
| Date/time | 2026-10-28 ~13:20 UTC |
| Outgoing / incoming agent | Claude Code → not assigned (session ended at the maintainer's request) |
| Task and desired outcome | Continuous RPCS3 optimization on iOS (God of War III, Dragon Ball Z, Black Ops II); private IPAs only, no release. |
| Current branch and exact HEAD | `Claude` at the commit that adds this handoff (`docs(rpcs3): record the delivered private 583`, after `cb59a784`); verify at takeover |
| Local changes and modified file paths | None in the repository (clean). |
| Commits pushed to GitHub (if any) | `8ebca287` Core 583 (texture pre-validation pacing, God of War III only); `e6374d49` private 583 recipe on the delivered 582 tree; `3df41250` Write Color Buffers lead and the commit adding this handoff (583 delivery receipt `docs/evidence/rpcs3-cell583-delivery.json`). Other agents pushed `dcc0f5a4`/`ecad3c40`/`6314127f` (MeloNX 582) and `23a847d6`/`1c1d1f7f` (enhancements catalogue) on the same branch; untouched. |
| Uncommitted or unpushed work (if any) | None. |
| Last verified working state | Private IPA 0.0.8 (583) built by run `40686712890` (188,117,202 bytes, SHA-256 `f7671888…05b3`, artifact `12818262071` encrypted for `build-utils/delivery-583-recipient.pem`; private key outside Git), all validators passed, decrypted and inspected; Core 583 run `40683438937` (Core `9aa3c7ee…57f4`). It is the delivered 582 product (MeloNX engine `e55ca25`, Switch discovery fix) with only the RPCS3 Core swapped. See `AGENTS.md` (Core 583 section) and `docs/rpcs3-cell583.md`. |
| Tests completed and tests **not** run | Host (GCC/Clang, ASan/UBSan, TSan) and Mac CI tests of Core 583 passed; delivery validators passed. **Not run:** anything on an iPhone. No FPS gain of 583 is measured. |
| Risks, license constraints, unknowns | The host model of 583 is noisy in steady state (six GCC runs: 581 median 81.3 %, 583 median 84.1 %; one Clang run had 581 ahead); the clear model gain is the tight loop (RSX ahead of the worker). The 583 Core driver lists `COREPROF OPT583` twice and not `OPT581` (copy slip, compensated by the Mac evidence and the IPA validator; fixing it changes the Core inputs, so only with the next Core). |
| Next **single safe action** | With the maintainer's 583 logs: God of War III `COREPROF OPT581`/`OPT583` (hits vs misses, `worker_passed`, `worker_refills`), `JITMEM texture_hash_ticks - worker_ms`, `RSXFRAME551 texture_ms`, FPS in the same scenes as 581; Black Ops II `texture_prehash=0`. |
| Actions requiring maintainer approval | (1) Zero-build experiment proposed to the maintainer: God of War III per-game "Write color buffers" off. The GameDB sets it on; with it, each frame's 1280×720 colour target is locked and read back on a CPU fault (`READBACK555 fault_read`: one 3.69 MB read per frame, 2.1–7.2 ms per frame, 737–948 ms per 5 s window in 581 session 5). The MLAA bypass is active (`mlaa_bypass=1`), so the reader may be gone; visual errors are possible. (2) The authorized isolated MoltenVK asynchronous submit trial on God of War III is not implemented (no code). Plan: a Core setting that overrides the profile's explicit `Disabled` for God of War III only, with a boot canary that falls back to synchronous submits when a boot with them does not reach N presented frames; God of War III spends 475–583 ms per 5 s window in `vkQueueSubmit` (581 session 5, about 1,500 submits). |

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
