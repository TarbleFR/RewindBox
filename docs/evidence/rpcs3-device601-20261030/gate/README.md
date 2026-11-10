# Targeted source gate after device601 logs

Only `rpcs3/Emu/RSX/rsx_cache.h` changes. The contract authenticates all 325
postimages against the compiled Core source `378509e8`, preserving 324; the
one-file inverse delta recovers the exact old weak cache. All physical codegen
inputs, the ABI30/88-export surface, sampler/worker headers and the compiler
recipe remain exact. The manifest permits only the recorded policy-note suffix.

`source-only.json` and `source-only-negative-controls.json` were executed on the
freshly materialized `RPCS3-verify` source. The latter rejects nine mutations:
canonical bytes, native postimage, omitted change set, runner, build shell,
dispatch route, historical receipt, codegen evidence and inverse delta. No
compiler, native suite, Apple job, Core, IPA or release ran in these checks.

The unchanged runtime592 workflow and build shell now route this source lot to
an isolated follow-up module. A future authorized Apple build executes four
jobs only: tiny cache plain, tiny cache ASan/UBSan (candidate iOS only), and the
affected divided-range suite in plain and ASan/UBSan modes. Ordinary tiny-cache
controls include the old iOS and unchanged desktop variants. Their pre-existing
unaligned loads are not presented as full sanitizer-validated code.

The original 28 Apple modes at `378509e8` retain their historical scope. The
source-only contract authenticates their committed summary receipt, **not**
unavailable raw Apple archives. Native preflight requires and authenticates
the exact original core and diagnostic archives, reports and captured compiler
inputs before compiling the new jobs. Missing or changed archives fail closed.
Those receipts never validate new weak-cache paths; the affected range programs
are explicitly executed again. No replay of the other historical native modes
is scheduled. The new future-native path has not itself run on Apple here.

Reproduce locally (no CI dispatch):

```sh
python .github/diagnostics/rpcs3runtime_device601_core.py --source /path/to/prepared-rpcs3 --source-only
python test/rpcs3_device601_gate_test.py --source /path/to/prepared-rpcs3 --report /tmp/device601-gate.json
```

The future native preflight preserves assertion checks, exact sanitizer modes,
selected LLVM22 Apple ARM64 compiler observations, emitted harness snapshots,
input closures, historical provenance and actual Core binary/ABI/codegen checks.
It cannot establish gameplay rendering or FPS improvements on an iPhone.


## Additional reboot, decrementer and feedback source lot

Current scope: eight native paths, 326 postimages. The existing gate evolves
in place and retains the single historical Core reference `378509e8`. Neither
the validation workflow nor the compiler shell is changed. The earlier
325-postimage source-only reports above remain historical; the additional
checks belong to `reboot-timer-feedback/` and are never relabeled as Apple jobs.

The decrementer has a separate compiler-free proof in
`../cpu/decrementer-codegen.json`. Restoring exactly the full-queue owner body
and timer callback recovers the complete old `SPUThread.cpp`; the enclosing
timer layout is checked independently. Forty physical identity inputs are
read. The unchanged external LLVM backend retains its previously authenticated
digest. Six existing aliases remain exact; one new exact-file alias preserves
the ordered PPU/SPU identities. Unknown hashes and wrong paths remain unaliased.
No CMake/LLVM object emission or physical cache replay is claimed.

The bounded savestate-completion header is an independent affected native
suite, included directly with exceptions disabled and real mutexes/threads.
Its callback-lifetime and registration/finish races complement the UIKit/Core
adapters in the process-switch integration fixture; they do not execute UIKit.

Future authorized Apple validation selects twelve affected jobs: tiny-cache,
vertex-range, decrementer, continuous-boot worker, savestate completion and color-feedback, each in
plain and ASan/UBSan modes. The tiny sanitizer job selects only the corrected
iOS variant. The original 28 Apple modes retain their historical scope and
are not replayed. Their historical receipt does not validate changed host
bodies or the rendering helper; no new Apple execution is claimed here.

The small baseline comprises canonical postimages, their exact inverse delta,
and only two extra upstream headers required by the decrementer fixture.
Those headers and the newly canonical `sys_process.cpp` preimage are bound to
the pinned upstream Git tree. No full extra checkout is copied. Future native
preflight still fails closed without the exact historical archive pair and
reports, then executes affected jobs and observes actual compiler inputs.

The final JSON reports in `reboot-timer-feedback/` state which checks actually
ran. Source authentication and adapted host scenarios establish neither the
reported games' visual correctness nor a resolved iPhone freeze or added FPS.
