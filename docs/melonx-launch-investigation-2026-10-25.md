# RewindBox MeloNX launch investigation — 25 October 2026

## Supplied evidence

The supplied `app (1).log` has 973 lines. Five launches of the same local XCI
start at lines 355, 471, 606, 766 and 909. The file is readable and has
3,992,977,408 bytes. The private dependencies and NativeAOT initialize, the
program code/data preflight succeeds and firmware 22.5.0 is recognized. Every
attempt selects the external JIT method. Each attempt contains a second
file/keys preflight sequence and then a new application-start boundary.

The early HeaderKey failure at line 241 precedes the key imports at lines
266–267. It is not evidence that the later successful content checks have the
same error. The rejected add-on inspections at lines 334–339 and SQLite folder
uniqueness errors are separate observations. No personal files are changed by
this candidate.

These observations do **not** identify the exact native termination mechanism.
The native Core retains events in a 64-entry memory ring; Swift polls it every
300 ms and sends the snapshot through asynchronous main-queue/Flutter calls.
The timestamps in `app.log` are generated during this relay. Consequently the
last relayed `keys/begin` event does not prove that key loading was the fatal
operation. A later native or JIT event can be lost with the process.

The exact delivered LibHac package was independently downloaded from engine
artifact 12538566496, run 40038087907. Artifact ZIP SHA-256:
`79e77ac4edfcf71d07161c20eca7abc02dadb29a4a757793436112c114e2f2a2`.
The NuGet package matches the established SHA-256
`b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9`.
Thirty consecutive real-reader reloads on a 512 KiB .NET worker stack passed
using synthetic values with the existing 190 supported / eight unknown /
33 wrong-sized prod-key shape and 19 synthetic title entries. This does not
reproduce an iPhone crash and does not establish personal-key correctness.

## Candidate changes

- The native serial launch worker performs the sole full content preflight.
  Dart no longer performs the same key reload, game inspection and firmware
  discovery immediately before native launch performs them again. The native
  preflight remains mandatory before executable-arena setup, donor acquisition,
  presentation or guest creation. For the built-in method, helper preparation
  now precedes this sole preflight; failure cancels the helper transaction.
- Both native journals append directly to the actual application log path
  supplied by `ConfigService`, before relaying events to Flutter. Core records
  retain their original sequence, timestamp, PID and redacted diagnostics.
  Writes use O_APPEND, coexist with the frontend logger and respect its 5 MiB
  size ceiling. Failed diagnostic I/O does not refuse a launch. No hard-coded
  data directory is used.
- A separate synchronous `jitProbe/begin` milestone surrounds the host's
  executable-mapping check. A process termination there can no longer leave
  only a delayed earlier key event as the last available evidence.

Removing repeated preflight work fixes a demonstrated pipeline defect. It is
**not yet a demonstrated fix for the reported iPhone termination**. The
candidate also repairs the demonstrated loss of native diagnostic evidence.
No key value, firmware or game payload is requested, logged or bundled. The
selected JIT method, mappings, helper protocol and other emulator sources stay
unchanged.

## Validation and remaining work

Completed locally on Linux / .NET 10.0.100:

- 13 production preflight, real-LibHac schema and journal assertions passed.
- Production managed-journal regression reproduced the old lost-event behavior
  with an abruptly terminated child. The corrected journal retained its final
  milestone. Two independent native writers plus a frontend-like append writer
  retained 601 complete native records and all 301 frontend lines; redaction,
  the bounded ring, full-file ceiling and failed-I/O isolation passed.
- The targeted Python runners compile and `git diff --check` passes.

The Swift journal test and updated production Flutter launch-flow tests are
prepared but have not run locally: this host has neither the Apple SDK nor a
Flutter installation. The NativeAOT engine must be rebuilt for the additive
content operation 9 and synchronous Core journal. Its existing focused workflow
now reuses unchanged key/personal proofs and executes the changed diagnostic
tests; the actual ARM64 smoke also checks operation 9 and persisted errors.

No push, GitHub Actions run, IPA, tag, main update or public release is claimed
by this local preparation. After the focused Apple/Flutter checks, an identified
test IPA and a physical launch are still required to establish whether the
reported termination is resolved or to read the actual synchronous failing
milestone. Do not present the candidate as a confirmed device repair.
