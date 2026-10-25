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

## Validation and private delivery

The candidate is delivered as RewindBox Build 529. The completed delivery is
source `3473995858e4893c8c2a8f4a19a9239d8b23048c`, workflow source
`5b8f2bd13fec4a7977620b4d10e595191e060e3b`, run `40147724203` (success).
The complete output IPA is 186,302,256 bytes, SHA-256:
`33b98a43792b3ba62a8e5e015d8d61ada0262d6f681a959a54ed572f6bdb1437`.

The native bootstrap and retained Dolphin resources now come from the last
published valid IPA, Build 527 in release 0.0.9. Its full archive hash is
`884a44dea6e627fc9cd774d296dc2abf1ef683ca01572651d5c0e3425bd9756e`.
The older delivery recipe still referenced the retired Build 350 donor; it is
not used by this delivery. The current main delivery workflow uses this exact
corrected candidate. Historical frozen workflows are not a source for new
assemblies: select the latest validated IPA and independently validated Cores.

RPCS3 uses the successfully compiled **Core 528**, source
`17ee65469c39e560c91fdb6d55604ab590992f59`, run `40142369420`.
Its original binary SHA-256 is
`0ad782b8ee49508165dfb694d19c9400f18c659c5584482228215bfdfc316dcb`.
All 140 required source identities match the candidate; the final signed
binary has the same compiled payload fingerprint as that artifact.

MeloNX uses engine source `329d9de706a647481e9d192aee890e92bb0b56ef`,
run `40144482367`, with actual iPhone binary SHA-256
`2e8979b263f3fa7b45389b4ea17a8f706116b232a53be90316bb3c5acb3e6073`.
That compilation run failed its original smoke assertion: the test searched
for `keysMissing` in a journal that intentionally records stage/status.
Corrected run `40145060306`, source
`291439626dd6bc10ecd918e16f29e8fda5f111ed`, passed against the exact compiled
engine. It executed two original unencrypted homebrew sessions on the actual
ARM64 iOS simulator runtime, including durable Core journal configuration.
This is not an iPhone or commercial-title gameplay test. All 30 adaptation
source hashes match the packaged iPhone engine.

Other completed checks:

- 13 production preflight and real-LibHac schema assertions; abrupt-process
  journal persistence, 601 concurrent native records, frontend coexistence,
  redaction, size bounds and failed-I/O isolation.
- Focused Flutter launch-flow, UIKit host/SDK and display/persistence checks.
- Full iPhone Release compilation, final ZIP structural/dependency checks,
  and strict deep ad hoc signature verification on extracted IPA bytes.
- Independent verification after downloading: all four transport ZIP digests,
  encrypted-payload hashes, source receipts, RPCS3/Dolphin payload fingerprints,
  journal launch contract, absence of KartPad/Dusklight and 87 signed images'
  CodeDirectory page hashes. No personal keys, firmware or games are bundled.

The existing CPU eligibility guard and private MeloNX helper additions are
now normalized exactly by historical JIT comparisons; all other historical
JIT state-machine and verifier bytes remain checked. Build 529's launch IPA
validator requires `configureLaunchJournal` and rejects the removed duplicate
Dart `contentPreflight` marker. The mandatory native preflight remains tested.
A sealed encrypted recovery snapshot is preserved before final validators so
a later assertion failure does not discard an already compiled IPA.

The output requires the user's usual Apple re-signing before installation.
The reported termination is **not yet confirmed resolved on the physical
phone**. If it persists, synchronous milestones now survive process loss and
can identify the operation reached. No tag, main change or public release was
created. Detailed receipts: `docs/evidence/melonx-launch529-delivery.json`.
