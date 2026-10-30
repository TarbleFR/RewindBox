# Current application identity — RewindBox (21 October 2026)

The maintainer renamed this independent fork to **RewindBox**. Use that name in all new user-facing text, releases and output files. Repository: `TarbleFR/RewindBox`. Preserve upstream NeoStation attribution, copyrights, original license files, historical evidence and stable compatibility identifiers. Do not rename bundle IDs, storage paths, preference keys, method channels or native ABI symbols as a cosmetic change. See `docs/REBRANDING.md`. No new release or IPA is authorized by the rebranding task.

## Private IPA597 — compiled, verified and privately delivered

The maintainer requested a new IPA with the newly compiled RPCS3 Core.
Build 597 succeeds in run 40985625413, job 123835845426, attempt1, source
6ce5097737701afb4dc371013889bacdcef15140. Delivered 596 is the baseline.
RPCS3 uses source 88cdc5e3 / run 40981514937 / artifact 12946200694;
MeloNX Core 87 remains source 07f35048 / run 40949501203 / artifact 12931177865.
Neither engine nor unchanged native suites were rebuilt. The new NeoSwap
Store.cpp, SHA256 87df68227cf9e113af51ec2ea8968d8af88170834611d560ce711cf168f1ca46,
was verified in CocoaPods sources and compiled into the application. The other
five product roots remain identical to delivered 596.

The actual downloaded IPA is 188329029 bytes, SHA256
b9e97907210458dfafe76fe471a3cde58fa18564488324e9adfd04dc7a7bb57d.
Independent verification passes: ZIP CRC, exact compiled payloads of both cores,
88 Mach-O images, 85 thin-image preservation fingerprints, three mono-ARM64 fat
containers and eight app/extension versions 0.0.8 (597). Apple CI verified 88 ad hoc
signing targets; independent Linux verification does not claim codesign.
Job 1069 s, Xcode467.726s, signing/export50.046s; one application compilation.

The private file was saved and the ephemeral private recipient key deleted.
Re-sign with SideStore; minimum iOS 18. No public release/tag or physical-device,
gameplay or FPS result is claimed. Do not reuse build 597. These documentary
receipts do not require another build. See docs/rewind597-test-ipa.md and
 docs/evidence/rewind597-delivery.json.

## RPCS3 continuation Core compiled and independently verified — 30 October 2026

The maintainer requested the new RPCS3 Core. The complete source lot
`c0d5bc7cd271445fcb10f5fdda4f1eea9798b101` is now on Claude and compiled from
`88cdc5e3e115a0b8587711d77147467baf38128b` in successful run `40981514937`
(job `123822448947`). The original `rpcs3-runtime592-core.yml` workflow and
`build_rpcs3_embedded_core.sh` are byte-identical to the successful historical
recipe. Two Darwin/Clang host-test preamble adaptations are isolated in the
continuation validator; production sources and frozen fixtures are unchanged.

All 24 affected Apple modes pass: 16 authenticated results reused from the
two preserved failed preflight attempts, eight remaining modes executed in the
successful run. Eleven unchanged historical Apple modes retain their scoped
evidence. Both failed runs stopped before Core compilation. The actual Core
compile took 717 seconds; the successful job took 904 seconds.

Core artifact `12946200694` is 29,139,881 bytes, ZIP SHA256
`18f76b5e28187cf28c46047ad8b4b13a631420412bb6efad2e9a5e5c19aae989`.
The downloaded archive was independently checked against GitHub's digest.
Its `libRPCS3Core.dylib` is 77,270,224 bytes, SHA256
`cc7362544f922aebdc021b5dbe6ca68d9c0bfb15d79145606f71af584509edd1`,
iOS ARM64, ABI 30, exactly 88 exports. All 319 canonical postimages and the
continuation patch `099651cae54c7bc567ff325735acde0cf3e931ed6e25b2b5bbcc14e5f5ecf33b`
match. PPU `a987639e9f838d1c` and SPU `477a3fa442d27917` are retained.
Receipt: `docs/evidence/rpcs3-continuation-20261030/apple-core.json`.

The native NeoSwap Store checks passed, but that host component is not packaged
by this Core-only build. No new IPA, release, physical-device test or FPS result
is claimed. Delivered IPA596 remains the application baseline.

## RPCS3 source continuation after IPA596 — 30 October 2026

Based on Claude `de8169848ecfa9c95946fc957861263a9fd1b879`, rechecked through
the GitHub branch API again at 00:02:36 UTC on 30 October. The source lot changes
eight canonical Core files and the native NeoSwap Store, preserving the other
311 canonical postimages. DMA empty-list/zero-byte/MMIO fixes, late shader
invalidation, successful-wait resource retirement, owned DMA fence reuse,
retired image pressure release, bounded complete-atlas clear elision, texture
depth/64-bit coverage arithmetic and bulk Store victim selection are included.

The exact host-only SPUThread.cpp compatibility mapping preserves PPU
`a987639e9f838d1c` and SPU `477a3fa442d27917`; its source/relocation justification
supersedes the preliminary CPU report's no-alias recommendation. Do not extend
that mapping to unknown hashes or older reservation implementations.

Canonical patch SHA256:
`099651cae54c7bc567ff325735acde0cf3e931ed6e25b2b5bbcc14e5f5ecf33b`.
Fresh materialization verifies all 319 postimages and host-loaded exports.
The continuation contract verifies 89 frozen repository/evidence inputs,
reconstructs the previous files and regenerates ten harness jobs plus NeoSwap
without recompiling unchanged programs. Affected production-extracted host
checks and the full POSIX Store suite have recorded normal/sanitizer results;
GPU-wait and DMA-ownership candidate checks have sanitizer receipts only.
See `docs/rpcs3-continuation-2026-10-30.md` and
`test/rpcs3_continuation_contract_test.py` for scope and reproduction.

No Apple Core/IPA build, push, CI dispatch, release, iPhone FPS gain or resolution
of the BO2/AC visual defects or GOW3 scene freeze is claimed. Existing delivery
and deep-audit Apple receipts describe their original source; a later authorized
Core build must account for these new inputs rather than relabel old receipts.

## Private IPA596 — compiled, verified and privately delivered

The maintainer explicitly requested a new IPA containing the latest compiled
RPCS3 and MeloNX cores. Build596 succeeds in run40968162236, job123777850588,
attempt1, source d5c5f107f7b514980033d1b95218aa9d2f640609. Reuse the established
private assembly recipe: neither engine was rebuilt for this delivery. RPCS3
comes from e97137b1 / run40963062736 / artifact12937551950, retaining both
543996ad and a363d923 and the deep-audit changes. MeloNX Core87 comes from
07f35048 / run40949501203 / artifact12931177865. The current NeoSwap Store.cpp,
SHA256 a812b0834df8c7301d59ac780b84a4ecc7c306b7b55f7ab02178e5705dca8571,
was compiled into the host. Other application product roots retain delivered595.

The actual downloaded IPA is 188327690 bytes, SHA256
b8d665ab4503fc4f3492b80bb46ed582dcfed71e99982f82a8c2a8a04a842d07.
Its independent verification passes: ZIP CRC, both real core payloads,
88 Mach-O images, 85 thin-image preservation fingerprints, three mono-ARM64
fat containers, and the eight application/extension versions 0.0.8 (596).
Apple CI verified 88 ad hoc signing targets; Linux did not repeat codesign.
Job915s, Xcode353.822921s, signing/export52.201335s; one application build.
The private file was saved for the maintainer and the ephemeral private
recipient key deleted. Re-sign with SideStore; minimum iOS18. No public
release/tag or physical iPhone/gameplay/FPS validation is claimed. Do not
reuse build596. These documentary receipts do not require another build.
See docs/rewind596-test-ipa.md and docs/evidence/rewind596-delivery.json.

## RPCS3 deep audit after device595 — 29 October 2026

This source phase follows local a363d923, preserving its three changes and the
preceding 543996ad lot. Remote Claude was rechecked through the GitHub branch API
at c0df3394d81d957eb7b28c85802278b69cc0f71b before and after this phase. No push.
The new canonical patch SHA256 is
5ba1424bcd40afc96f3263e236d84ed643cb7aac15cbcd1fb513e85d24e27ec8:
319 postimages, 308 historical postimages unchanged, eleven Core files changed.
The twelfth production input is native/neoswap-storage/Store.cpp.

Retained changes: correct SNR old count, re-arm restored deferred MFC work,
publish LLVM barrier tags, use the blocking helper on a full LLVM MFC queue,
and resume the current WRCH after an interrupt before its acceptance. Fix native
view invalidation, temporary-pool depth/mips/format-class matching, depth format
classification, requested image usages and vertex-read barrier scopes. Avoid
clears only for fully covered color cube/volume copies; avoid small copy-source
set allocations. Reduce shader formatter scanning/callback allocations, merge
JIT free ranges directly, avoid repeated NeoSwap RAM totals, and create streaming
synchronization objects on first use while preserving their reuse distance.

The compiler-free deep contract passes on a freshly materialized candidate:
21 recorded host modes authenticated (17 final, four intermediate MFC stages),
plus both complete POSIX Store suites. Exact source/extracted-program hashes,
inverse delta, source/recipe/ABI and exports pass. Barrier-mask validation is
plain only; other retained harnesses have plain and ASan/UBSan results. LSan,
actual LLVM compilation, Apple/GPU and iPhone execution are not claimed. The
final MFC harness repeats intermediate tag/full-queue scenarios with IRQ/IRET.

PPU codegen identity remains a987639e9f838d1c; SPU changes normally from
d070cb361bdef607 to 477a3fa442d27917. No compatibility alias was added: first-use
SPU cache compilation may increase startup pauses. LLVM GPR materialization may
reduce store elimination. Small-copy specialization may duplicate the GPU body;
the measured +955 bytes covers bookkeeping only, not Apple code size. Retain
negative timing cases (including nine distinct copy inputs +8.7%). Three raw
shader cache experiments were withdrawn; final rsx_cache.h matches baseline.

38 JSON investigation entries plus CPU/MFC reviews cover the requested domains.
They are not 38 independent speedups. Existing BO2/AC stutters include windows
without shader compilation. GOW3's missing label producer remains unidentified.
The five SPU protocol defects and rendering reproductions do not prove that
the three reported iPhone scenes are fixed. No new FPS claim, telemetry, Core,
IPA or release. Historical delivery pins still describe IPA595/Core f42573af,
not these unbuilt sources. First affected Apple validation and same-scene device
measurements remain necessary. Reuse recorded native proofs while exact inputs
match. See docs/rpcs3-deep-audit-2026-10-29.md and its evidence directory.

## RPCS3 device595 follow-up sources — 29 October 2026

After local 543996ad, three additional iOS changes are retained: reselect the
current remap on Vulkan temporary-image cache hits; retain the SPU decrementer
worker's expiry scratch between wakeups; pack surface coverage into one bit per
guest byte. Claude remote was rechecked at c0df3394. Canonical patch SHA256:
037d620eb0148b7311da74d711dd2099d06e1285ad6f3079df9586a920a1a0e0.
314 postimages, five changed, 309 unchanged relative to 543996ad.

Six new GCC Linux modes pass, plain and ASan/UBSan. Remap: 373,248 requests,
373,230 wrong selections before and zero after, unchanged image-copy counts.
Timer: stable allocations 128 to 1 and variable allocations 768 to 4, same
publication/wait order and failure semantics. Surface marker: 4,194,308 to
524,296 bytes for a 4 MiB span; 391,754 row checks and 10,128 geometry cases.
Keep all timing results: four timer and one surface case regress on this host.
No iPhone FPS or device visual/freeze fix is established. GOW3's missing label
producer remains unproved; no forced label or barrier removal is retained.

One CMake script authenticates all 41 codegen inputs (40 physical, unchanged
external LLVM digest), preserving PPU a987639e9f838d1c / SPU d070cb361bdef607.
The compiler-free follow-up contract authenticates six new native results and
reuses six exact unchanged previous results. Do not replay unaffected suites.
No push, Apple/Core/IPA build or release. Existing delivery pins stay historical;
the latest two source lots still require their first affected Apple validation
for a future explicitly requested Core. No diagnostics or telemetry are added.
See docs/rpcs3-device595-followup-2026-10-29.md and its linked raw evidence.

## RPCS3 source optimizations after device595 feedback — 29 October 2026

Based on Claude c0df3394, rechecked during the task, in an isolated checkout.
Three iOS-only paths change: simple_array transfers heap ownership in mixed
inline/heap swaps; temporary texture entries retain only encoded identity and
invalidation range; unique/missing texture addresses avoid a second binary search.
Canonical delta 33320812eccaf55ce7e834fe9a3a01da004e8323f0ad149cbf424a2ac3dcef9c:
314 postimages, 311 historical postimages unchanged, two changed, one new.
Six targeted Linux modes pass (three plain, three ASan/UBSan); no Apple/native
Core/IPA build or release. LSan was unavailable under ptrace and is not claimed.
Array checks: 726,336 comparisons, tracked ownership/lifetimes; temporary cache:
12,422 checks; address lifecycle: 22,753 queries and 8,618 mutations per mode.
The compiler-free device595 delta test authenticates these exact source inputs
and generated harnesses. Reuse existing results while their inputs match.

The maintainer reports improved BO2 with remaining weapon/forearm artifacts and
stutters, unchanged GOW3 with a repeatable freeze, and AC torch flicker/roughly
27 FPS. Existing logs confirm a persistent GOW3 RSX label wait (expected 0x6F0E,
observed 0x6F0D); its producer cause is unproved. These source optimizations do
not establish a visual fix, resolved freeze or added iPhone FPS. The inactive
AMD primitive-restart scratch experiment was withdrawn, as was an unsafe
unlocked exact-cache shortcut. All runtime settings, existing delivery recipes,
Core pins, unrelated engines and other checkouts stay untouched. A future
explicitly requested Core requires Apple validation of these changed inputs;
its proof must not reuse the old binary receipt as if these sources were built.
See docs/rpcs3-device595-optimization-2026-10-29.md and
 docs/evidence/rpcs3-device595-20261029/.

## MeloNX new GPU core compilation authorized — 29 October 2026

The maintainer requested compilation of the new MeloNX Core. The new frozen
GPU contract authenticates 102 preparation inputs and 139 adapted members,
runs only the fifteen new Apple ARM64 fixtures, retains fourteen Core85
historical receipts without replay, and compiles both iOS and simulator
NativeAOT libraries before the real simulator lifecycle smoke. Core85's
original verifier and evidence remain unchanged. LibHac and all ten native
framework binaries are authenticated and reused. No IPA or public release
is authorized by this request. Build success is pending actual CI evidence.

## MeloNX descriptor/cache source continuation — 29 October 2026

Five more guarded adapters follow local 55fdfeb: identical scalar descriptors
keep their clean state, exceptional descriptor updates use bounded stack spans,
private constant-buffer snapshots are reused at exact length, first-containing
buffer queries use a bounded allocation-free traversal, and allocator splits/
coalescing update intervals in place. All fifteen new adapters across these
continuations now change twenty-two engine files. Preparation has 102 inputs,
139 members; 133 of the previous 137 prepared members remain identical.

Five affected host fixtures pass. They preserve descriptor usage/barriers and
explicit invalidation, test full cache behavior/alias/failure cases, tree/range
lookup order and sparse/write effects, and allocator arithmetic/first-fit/locks.
Counts and allocation probes are evidence; some bounded fallback and small
allocator timing rows regress and remain recorded. No universal CPU/FPS claim.

Two experiments are rejected, not product changes: Auto single-parent storage
saved 32 B but slowed other hot paths; pool binding purge could expose a stale
graphics manager reference after compute evicted its pool. Do not retry that
purge alone. It needs safe disposed texture/sampler pool acquisition and a real
compute-to-graphics transition proof first. Old pool lifetime behavior remains.

The final combined managed Release Library passes Linux SDK 10.0.100. No Apple
NativeAOT core, IPA, build number, public tag or release is produced. Existing
successful suites are reused only within their unchanged scope; fixed Core85
Apple input contracts deliberately refuse this newer preparation set.
Details: docs/melonx-descriptor-cache-2026-10-29.md and its evidence directory.

## MeloNX additional steady-state source candidate — 29 October 2026

Four further adapters follow local 8399607: lazy virtual-buffer readback with
one callback per invocation and clamped copies; stable Vulkan barrier batch
compaction; bounded exact-length GAL snapshots; and oversized uniform spans.
No FIFO/shadow shortcut is extended. Ten adapters across both lots now change
sixteen engine files. Preparation has 97 inputs and 137 members: 128 of the
first lot's 133 members are unchanged, five change and four more are included.
Earlier receipts retain their scope.

Four new affected host fixtures pass, including complete production classes,
30,000 concurrent snapshot commands, covariance, pin lifetime, out-of-window
dirty ranges, wrap/sentinel/reentrant uniform state and full Vulkan barrier
traces. Clean 32 KiB readback/200 operations: 6,648,000→89,600 allocated bytes.
Warm snapshots of 2/8/256/4096 entries: 40/88/2072/32792→0 B per command in the
controlled test. The pool retains at most 512 KiB reference slots plus overhead;
burst exhaustion can still allocate. Interleaved barriers improve markedly on
the host; same-flag timing regressions remain recorded. No iPhone FPS/RSS claim.

The final combined Release Library builds on Linux SDK 10.0.100; no Apple core,
IPA, new build number, release or tag is produced. A later Apple build must
cover changed code and reuse only authenticated unchanged evidence; the old
fixed Core85 contract intentionally refuses changed preparation inputs.
Details: docs/melonx-steady-state-2026-10-29.md and its evidence directory.

## MeloNX GPU execution and warm-up source candidate — 29 October 2026

The maintainer requested further concrete MeloNX optimization, starting from
Claude c0df3394 after Core85/IPA595. Six guarded adapters change twelve engine
files: speculative vertex-stride parity, closure-free attachment queries,
scalar threaded bindings, buffer range/migration ownership, render-target
snapshot cleanup, and key-only conversion without shader-stage allocations.
Preparation now authenticates 93 inputs; 121 of Core85's 129 prepared members
remain identical, eight change and four additional sources are included.

Six targeted host suites pass with functional equivalence/ownership checks.
Warm allocations: attachment queries 88→0 B, scalar bindings 32→0 B, a current-sync
buffer snapshot 152→0 B, pipeline keys 32→0 B plus native 240→0 B per lookup. These
are isolated workloads, not resident RAM or iPhone FPS measurements. The fresh
binding stride oracle has 1,200→0 key divergences over 5,766 states. Historical
unused-buffer alignment is outside that claim. Real command-ring stride stays 80 B.

Full managed Release Library passes SDK 10.0.100 Linux, then the changed pipeline
code passes incremental integration; no Apple NativeAOT build, iPhone gameplay,
new IPA, build number, tag or release is claimed. Reuse unchanged historical
results only with matching inputs; the frozen Core85 Apple contract correctly
rejects the new preparation set and needs an updated contract for a later
authorized Core build. Preserve all earlier proof and delivered595.
Details: docs/melonx-gpu-runtime-2026-10-29.md and its evidence directory.

## Private IPA 595 — compiled, independently verified and privately saved, 29 October 2026

The maintainer explicitly requested a private IPA with the latest RPCS3/MeloNX.
Version 0.0.8 (595) passes corrected run 40928805790, job 123641427943,
attempt 1, source d2e5029f8d7ca33eec279546d64a7f908285e804.
Encrypted artifact 12921794075 is 188,666,269 bytes, SHA256
9bbda35701fe6da477d95e9a043935096270ecf5aaa9158b4c0af20532341a35.
The actual downloaded IPA is 188,331,345 bytes, SHA256
cfc1079249e4168349896a69f34a150ddbc68e318aafbb954a06cb019b00374e.

It embeds verified RPCS3 f42573af / artifact 12917652510 and MeloNX Core85
3c0997d9 / artifact 12912462226. Exact 349 RPCS3 validation inputs, 92 Core
build inputs and 87 MeloNX preparation inputs match. Core85 includes Core84's
twelve fixes plus the reviewed timer/sync/bitmap follow-up. No engine is rebuilt
and no unchanged native suite is replayed for packaging. The host Store.cpp
optimization, SHA256 9a951454d7e5124bea4ca1ee5589b1e4429df637dc4377b6c7e3775fcb1c99e4,
is actually compiled into this application; CocoaPods source equality is checked.
Other product scopes preserve delivered594. Keep compatibility identifiers.

Independent downloaded-file verification passes with the original committed
signed-core validators, 522 authenticated source files and actual core archives.
ZIP: 5,350 members, CRC valid. There are 88 Mach-O files: 85 thin ARM64 images
with exact before/after-signing code/data/ABI fingerprints, and three mono-ARM64
fat containers (App, objective_c, sqlite3) covered by strict post-signing identity,
structure and CI signatures. Do not claim before/after fingerprints for those
three. Apple CI verifies 88 ad hoc signing targets; Linux does not cryptographically
reverify codesign. Main application and seven extensions are all 0.0.8 (595).

Preserve failed run40926266201/source929b6443: a recipe build-number replacement
also changed Dolphin's immutable SHA. The legal guard correctly stopped delivery
after application compilation; no recoverable IPA was retained. The recipe now
restores the exact Dolphin pin and authenticates nine pins before compilation. Two application builds
were needed: Xcode378.903s then427.782s; successful job1017s, signing/export58.788s.
The initial independent checker also wrongly rejected the three fat containers;
its original script/failure and narrow correction remain in the verification proof.
No product binary or committed signed-core validator changes for that correction.

RewindBox-Build595.ipa is saved as a private maintainer download and the ephemeral
recipient private key was deleted after saving. SideStore re-signing is required;
the package declares iOS18.0 minimum. No public release/tag, physical-device launch,
Hogwarts FPS/RSS gain or prolonged gameplay result is established. Do not reuse595.
Preserve delivery source tree67de75286e052332304f49b10b4f1cdff6750f0b and the exact
product roots in docs/evidence/rewind595-delivery.json; native root is now
13f00cb5070d4bb08928be628c273ec21210b8e6. Documentary commits do not require builds.
Details: docs/rewind595-test-ipa.md and docs/evidence/rewind595/.

## RPCS3 refinement Core compiled and independently verified — 29 October 2026

The requested retry is complete: source f42573afc25842ca9a0068f4ad505bbfe5342623
passes run 40917423708, job 123601264700, attempt 1. Artifact 12917652510 is
29,118,830 bytes, ZIP SHA256
4956f76388cbe2da7eeb87f45980a91391d05e3f71af16fdb163668efe3e2cad.
The downloaded actual ARM64/iOS Core is 77,268,488 bytes, SHA256
05459149444fe5be32ffb8218ada79dd6a3b531377bd3d19e1bf34294dd0fbb8.
ABI30, 88 real exports, PPU a987639e9f838d1c and SPU d070cb361bdef607 pass.

The maintainer explicitly requested resuming failed run 40914849302, source
5796e165, job 123592224611. Seven Apple modes passed before the isolated lookup
harness failed Clang -Werror on min_bytes, max_sequence and lookahead; Core
compilation was skipped. Preserve that failure and artifact 12914878675.

Only the copied lookup test header gains three exact [[maybe_unused]] annotations.
The 313 native postimages, 97 supplements, workflow and Core recipe are unchanged.
GCC with the explicit equivalent unused-constant diagnostic reproduces all three
old errors; corrected lookup plain and ASan/UBSan pass for both versions. No
unchanged native test or CMake is replayed. The partial-resume contract binds 349
inputs, seven exact passed Apple programs and their original report/output bytes;
36 corrupt-evidence controls are rejected. The original failure stays a failure.
The retry executed only lookup and RSX sampler plain/ASan, then built the Core.
The separate 17 global and 16 older unchanged Apple modes remain historical.
All three downloaded ZIPs, actual Mach-O, 349 validation inputs, 92 Core inputs,
313 postimages, 97 supplements and all eleven reports pass independent checks.
Full receipt verification relocates only the fixed final --report directory
for four command comparisons; original sources, proof and report bytes stay exact.
Preflight79s, Core compilation574s, final checks12s, whole job779s (12m59).
Reuse this artifact for a later authorized IPA while its exact inputs match;
do not rebuild or replay unchanged suites for these documentary updates.

All eighteen Apple timing cases are retained, including five slower medians.
Lookup key/epoch misses improve in the host microbenchmark; descriptors retain
slower graphics-hit/alternating cases. No iPhone FPS or GPU claim follows.
The log retains 500 ranlib LLVM22/AppleLLVM17 warnings and eight iOS17.4
availability warnings; minos16.3 metadata does not establish 16.3–17.3 support.
Runner/NeoSwap require17.4. Passive loading is a static direct-branch check,
not device execution. No IPA or release was produced. The previous 5b2a5614
Core and all failures remain historical. Details and raw evidence:
docs/rpcs3-runtime-refinement-core-2026-10-29.md and
docs/evidence/rpcs3-runtime-refinement-20261029/apple-core/success-f42573af/.

## RPCS3 runtime refinements after the verified Core — 29 October 2026

The maintainer explicitly requested concrete engine optimization after 5b2a5614.
Starting at Claude 140f35c1, three runtime paths change: direct one/two-handle
descriptor comparisons/copies, one timer delay conversion after the stable
expiry sweep, and prehash key/epoch misses before payload/sequence loads.
Four canonical files change including the exact SPU compatibility alias;
309 postimages remain identical. Layouts, offsets, epoch/bypass semantics,
nonblocking publication, order, callbacks and allocations stay preserved.
The MFC branch experiment was withdrawn: its Linux gain was marginal and
ARM64 acquired an extra branch. The verified production MFC mask is unchanged.

Eleven affected Linux modes pass: five plain, five ASan/UBSan, one unsuppressed
TSan. Additional timer coverage includes 1,792 arithmetic/overflow/order cases.
One CMake script authenticates all 41 codegen inputs and keeps PPU
a987639e9f838d1c / SPU d070cb361bdef607, rejecting unknown future edits/paths.
The compiler-free contract authenticates 330 inputs and rejects 14 corrupt
reports. Reuse the 17 unchanged global Apple modes and the separate 16 older
Apple modes. Nine changed modes are superseded; a future explicitly requested
Core runs only 11 affected/new Apple modes. No unchanged native suite or CMake
should be replayed for packaging or documentary changes.

All 33 new GCC timing cases are retained, including 11 regressing medians.
Descriptor graphics/compute alternation and some partly expired timer batches
cost more on this host. Cross-compiled ARM64 Clang22 removes descriptor libc
calls; it is not Apple runtime or iPhone evidence. No added FPS, fixed BO2/AC
visuals, solved GOW3 freeze, Core rebuild, IPA, delivery number or release is
established by this source lot. Preserve verified 5b2a5614 as a historical
binary, all prior receipts, concurrent MeloNX and private IPA594.
Details: docs/rpcs3-runtime-refinement-2026-10-29.md and
docs/evidence/rpcs3-runtime-refinement-20261029/.

## RPCS3 global Core compiled and independently verified — 29 October 2026

The maintainer explicitly requested this Core rebuild. Source
`5b2a5614f634221ea896607b4686ad2afdd5ada3` passes run `40903365466`, job
`123551374331`, attempt 1. Core artifact `12912380338` is 29,114,064 bytes,
ZIP SHA256 `76e1e34b95882c5d91ca65fb8b85aa2a5ad130a3418035ba1bd53535b2a216d1`.
The actual downloaded ARM64/iOS dylib is 77,268,488 bytes, SHA256
`a45a9de84c7b3b82a43dc091a999da32316389f575a0afd8c983d69bd8a1f276`.
ABI 30, 88 actual exports and PPU/SPU identities remain unchanged. The source-only
statements below describe the earlier source lots; this Core now includes them.

All 26 candidate Apple modes pass: 12 executed in the successful run, 14 reused
from authenticated partial checkpoints (4 from 40897672646, 10 from 40900528171).
Those two runs remain failures before Core compilation. Only the unordered-set
rank assumption and an unused iOS-only mock constant required test corrections;
no native source or build recipe changed during these retries. Sixteen older
unchanged Apple modes remain separately reused. Do not replay unchanged suites.

All three downloaded ZIPs, actual Mach-O, 269 validation inputs, 92 build inputs,
313 native postimages and 97 supplements pass independent checks. Full receipt
revalidation uses the original verifier with only the fixed Apple --report output
directory adapted for command comparison; every other argv and all report bytes
stay exact. Preserve the original local path-mismatch failure and portable receipt.
No native test or CMake was executed during this download validation. Core
compilation took 696 seconds; preflight 174; final Apple checks 15; whole job 1022.

Apple microbenchmarks have tradeoffs: all four isolated MFC mask medians regress
with the real cntvct_el0 clock, pure descriptor hits/changing handles cost more,
and some no-expiry timer/distinct-hash medians regress. Preserve all 44 measured
cases and 12 regressing medians. Timer expiry batches and repeated hashes improve
locally; none establishes iPhone FPS. Store.cpp's NeoSwap optimization is host
application code, not part of this dylib, and needs a later application build.

The dylib declares minos 16.3 but uses os_sync_* APIs requiring 17.4; Runner and
NeoSwap already require 17.4. Do not advertise isolated Core support for 16.3–17.3.
The build has ranlib LLVM 22/Apple LLVM 17 bitcode warnings despite successful linking.
Passive loading checks are static direct B/BL reachability to depth 16, not an
iPhone dlopen. No device gameplay, FPS, prolonged stability, new IPA or release
result exists. Reuse this artifact for a subsequently requested IPA while its
inputs match, without rebuilding for documentation-only commits. Evidence and
details: docs/rpcs3-global-core-2026-10-29.md,
docs/rpcs3-global-apple-measurements-2026-10-29.md and
docs/evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/.
Preserve private IPA594 and the concurrent MeloNX Core84 evidence.

## MeloNX additional runtime candidate — 29 October 2026

The maintainer supplied the extended Hogwarts log (SHA256 3aaa4bbc...e8a99b3b)
and then explicitly asked for more improvements. The candidate preserves Core84
and adds stable linear cancellation for multiple timer arms, FIFO sync retirement,
flush callbacks allocated only on real requests, and shared bitmap page bounds.
Three production paths differ from Core84; 126 other adapted members match.
There are 87 preparation inputs and 129 adapted archive members. The two new
host gates compile whole changed classes: timer 195 scenarios/103,769 assertions
per variant, sync/bitmap 219 scenarios/120,566 assertions per variant. Timers
include the exact Core84 control. Preserve measured slower small cases.

The Apple recipe authenticates twelve unchanged Core84 receipts and reruns only
the affected timer and new sync gates before both NativeAOT builds and the
two-session SVC smoke. Nine negative controls cover receipt reuse; no historical
suite is replayed. No iPhone FPS/RSS gain or new IPA is established by host tests.
Current source evidence: docs/melonx-hogwarts-timer-2026-10-29.md and
docs/evidence/melonx-hogwarts-timer-20261029/. RPCS3 work remains separate.

## RPCS3 global runtime optimization follow-up — 29 October 2026

The maintainer expanded the task to global runtime performance, then asked
to resume. Baseline is Claude 3e4fcfa1, including the device594 source fixes.
Five new runtime optimizations modify six canonical native files plus host
native/neoswap-storage/Store.cpp: skip the MFC timestamp when its bits cannot
affect the mask; stable linear SPU decrementer expiry compaction; independent
iOS descriptor caches keyed by bind point, exact layout, count and handles;
reuse eligible synchronous texture hashes in the existing epoch table with
one nonblocking publication CAS; skip Store retirement scans with no pending
discard. Retained pins/jobs/busy entries keep the mutex-protected scan flag.

No emitted PPU/SPU instructions or layouts change. The exact reviewed
SPUThread.cpp alias is updated, with all 41 codegen inputs authenticated and
one real CMake script invocation checking baseline, candidate, absent alias,
unknown future source and wrong path. PPU a987639e9f838d1c and SPU
d070cb361bdef607 remain valid. Unknown edits still invalidate normally.

Seven optimized, seven ASan/UBSan and two TSan host modes pass on Linux
x86_64, with no TSan suppressions. Viewport and scoped-write programs really
changed and their four modes were rerun. Seven other successful Apple
programs retain exact executable hashes (16 modes reused). The five
device594 programs remain exact (ten Apple modes still pending). The new
Apple gate therefore runs 26 modes on the next explicitly requested build.
Do not rerun unchanged suites or CMake. Receipt authentication does neither.

The hash benefit is conditional: 96 same-range validations use 12 hashes;
distinct ranges still hash and some host timing medians regress. Preserve
all measurements and their scope. Prehash Automatic remains GOW3 only.
Existing prehash hit counters can now include synchronous producers and
must not be attributed entirely to the worker. Descriptor state costs 48
extra bytes per host-modeled iOS command buffer, with no new allocation.

No Core/IPA/release or physical iPhone result exists for these source lots.
Do not claim added FPS, fixed weapon/torch rendering or the GOW3 freeze.
Preserve WCB, readbacks, guest labels, prior NEON/LLVM fixes and the measured
Budokai early-submit optimization. See docs/rpcs3-global-optimization-2026-10-29.md,
docs/evidence/rpcs3-global-20261029/ and docs/evidence/rpcs3-rsx-bind-20261029/.
The global source contract and 19 invalid-receipt controls supersede only
their new paths; all old delivery evidence remains historical and intact.

## RPCS3 source follow-up after device594 — 29 October 2026

The maintainer supplied BO2, Assassin's Creed and GOW3 logs after delivered
IPA594 and requested actual fixes without a release. Five native files in the
single canonical delta change: explicit FIFO_EMPTY on incomplete pending
reads; retry the header when its first argument is unpublished; retire
resource-less texture ranges before retag/clear; remove address-index entries
by ordered key and eliminate the redundant insertion scan; wait for safe
uploads at TRANSFER/VERTEX/FRAGMENT on iOS; refresh views/filtering and shared
fragment conversion state across BX2 and texture-reference changes.

The complete BX2 XOR deliberately leaves dormant units dirty without upload.
Recompute fragment state on any texture-reference-mask change: removal of the
last non-BX2 software-converted unit otherwise retains FORMAT_CONVERT in the
actual normalized shader key and GLSL conversion property. No new cache
format, field, player setting, telemetry or forced guest label is introduced.
The private range invalidation method has a narrow owning-block friend under
iOS; the compiled regression preserves the private access check.

The earlier uncommitted scratch candidate was lost after interruption. Use
only the reconstructed source hashes and newly executed reports in
`docs/evidence/rpcs3-device594-20261029/`, not the lost test counts or timings.
Five optimized and five ASan/UBSan host modes cover the changed production
paths. The new Apple gate authenticates 20 unchanged successful modes from
Core594, supersedes four old texture modes and schedules only ten new modes
for the next explicitly requested Apple build. Reuse historical exact program
hashes and PPU/SPU source proof instead of replaying unaffected tests/CMake.
PPU a987639e9f838d1c, SPU d070cb361bdef607, ABI30 and 88 exports remain fixed.

Selected build594/PID49019 guest-render intervals are BO2 23.08 FPS, AC27.09
with no graphics compilation, restored GOW3 16.67. These are not candidate
improvements. The only new captured freeze is BO2 during pipeline creation;
the user-reported GOW3 freeze remains open. GOW3 has zero fallback queue drains
but substantial texture hashing and CPU-fault readbacks. Preserve WCB and
established compatibility settings. See `docs/rpcs3-device594-followup-2026-10-29.md`.
No new Core, IPA, delivery number, release or physical-device result exists.
Preserve the 594 delivery and concurrent MeloNX evidence below.

## Private IPA 594 — compiled and independently verified, 29 October 2026

The maintainer requested the new RPCS3 Core with the latest MeloNX fixes.
Private version 0.0.8 (594) passes run `40848076659` on attempt 1, source
`97365ce57f17499101e88d50019b6c63be554b83`, artifact `12887185554`.
IPA: 188,316,921 bytes, SHA256
`714021770922547c532e1439466d5725b4f8eb17c18ca629fe996d985124fe63`.
The real downloaded IPA passes independent payload checks against RPCS3 Core
`fe587e27` / artifact `12883027017` and MeloNX engine82 `ebcee352` /
artifact `12883480724`. Preserve MeloNX's original failed first smoke and its
separate successful runtime validation `40841402428`; the engine was unchanged.
All 85 Mach-O payloads retain code/data and ABI through signing; 88 ad hoc
signature records pass on the Apple runner. The app and its seven extensions
are version 0.0.8 (594). Job: 840 s; Xcode: 320.895 s; signing/export: 52.616 s.
One application build; no engine rebuild or native-suite replay during packaging.
StikJIT cache reused. No public release/tag or physical-device/FPS result.

The verified IPA is available as a conversation workspace download; persistent
private-file saving is still pending explicit maintainer authorization. Do not
claim that persistent saving or recipient-key cleanup has completed. Re-sign
with SideStore before installation. Preserve the verified 594 product tree
`1d43bbac26b3146d5d24afff0553d0c18d5bc20e` and its exact input contract for
subsequent work. Do not reuse build 594. Evidence:
`docs/evidence/rewind594-delivery.json` and `docs/evidence/rewind594/`.
Full 13 RPCS3 + 16 MeloNX inventory: `docs/rewind594-changelog-fr.md`.

## MeloNX Hogwarts additional memory and CPU candidate — 29 October 2026

The maintainer requested deeper investigation and additional fixes. Twelve new
guarded adapters are integrated locally on Claude at base
`c609b0d05a583d2d39f636f328830a6256439807` / engine82: tracking snapshots,
MultiRange slices, texture callbacks and region cursors, retired texture
dependencies, inline Auto ownership, missing converted-cache lookups, indirect
conversion-key invalidation, dedicated allocator tracking/failure cleanup,
kernel wait references, pooled IPC references and timer wrappers.

All twelve targeted production-code host gates pass. Fresh preparation binds
86 inputs and changes 17 source paths (16 modified, one added); all 4,096 final
source/project files match the managed build workspace. Release Library build
passes with zero errors. Initial full compilation has 27 warnings in unchanged
files; final incremental completion passes separately. Preserve its incomplete
prior output instead of treating that partial attempt as a success. Exact
receipts, build logs, postimages and independent reviews:
`docs/melonx-hogwarts-followup-2026-10-29.md` and
`docs/evidence/melonx-hogwarts-followup-20261029/`.

Retire old texture links only after every replacement inherits; pending GPU
actions and DeferredCopy must keep their required owners alive. The allocator
has explicit tradeoffs: slower 32-block host case and +4096 bytes peak in one
mixed-pool case; no universal CPU/native-memory gain is claimed. The timer list
uses 24 additional bytes per reserved slot while eliminating per-arm objects.
Host allocated-byte counts are not game RSS or iPhone FPS measurements.

The earlier local eleven-adapter batch was unavailable after the workspace
changed and was absent from this remote base. This candidate and its exported
patch contain only the twelve new adapters; do not claim a combined 23-adapter
validation. Recover and review the previous patch before cumulative integration.
The source batch was pushed to Claude as `7ffdbaae` with [skip ci], reusing the
passed Linux checks. The maintainer then explicitly requested the corrected
Core ("Push et apporte les correctifs au core"). The Apple recipe now runs
the twelve new gates and one affected fragmented-upload/Slice composition,
builds both NativeAOT libraries, verifies the ABI and runs the corrected
two-session runtime smoke on the new simulator binary. Engine82's verified
envelope authenticates the unchanged LibHac package and historical evidence;
old results stay separate and are not claimed as tests of newly changed code.
Do not replay unchanged historical suites or rebuild native dependencies.
The reviewed 86-input/source contract fails closed on a later source change.
No IPA, release or iPhone performance result is authorized or implied by this
Core build. Preserve RPCS3 and delivered private IPA594.

## MeloNX Core84 compiled and independently verified — 29 October 2026

The requested corrected Core is complete. Source
`5045889ff9f1a872d238435293c50cacd7c127b5` passes run `40895446303`, job
`123523168026`, attempt 1. Artifact `12907831125` is 87,444,668 bytes, ZIP SHA256
`03d98461351141dbc32a407591081a775c4c5298ab1df7ae8b72f39e6cf20493`.
Both actual NativeAOT ARM64 dylibs and their 47 required exports pass:
iOS 37,585,128 bytes, SHA256
`a19229b27a949225dd6aebc03c6737b466f26f355ee0ec5f8418ec7857bfc6a4`;
simulator 37,911,912 bytes, SHA256
`a171296956d22e57d242b918ea262ac84fa0113591c46e69ce169cb200a10248`.

Thirteen fresh Apple gates pass in 94 seconds. NativeAOT/ABI takes 254 seconds,
the new runtime smoke 241 seconds, and the job 702 seconds. Two separate guest
SVC sessions close and release their backing. Offline independent verification
authenticates both actual Mach-O images, 86 preparation inputs, 127 adapted
source members (17 reviewed changes, 110 unchanged), 13 receipts and their
inputs, LibHac and the native-framework reuse proof. Historical suites and
unchanged native dependencies were not rebuilt or replayed.

Apple host timings retain tradeoffs: middle/late fragmented Slice and the
4096-handle snapshot case can be slower despite lower allocation; timer slots
grow 8 to 32 bytes; the mixed allocator peak is 4096 bytes higher. These are
JIT host measurements with native boundaries doubled, not iPhone FPS/RSS.
The runtime smoke is non-graphical simulator homebrew. No physical device,
Hogwarts gameplay, IPA or release result exists for this Core.

Reuse this verified Core for the next requested IPA if its exact 86 inputs and
build contract still match; do not recompile it or repeat successful suites for
packaging. This updates the current MeloNX selection after delivered IPA594;
the engine82 proofs and the original private594 payload remain historical.
See `docs/melonx-hogwarts-core-2026-10-29.md` and
`docs/evidence/melonx-hogwarts-core-20261029/apple-core.json`.

## RPCS3 Core compiled and verified — 29 October 2026

The maintainer explicitly requested the Core build. Immutable source
`fe587e27fcefadaa36315a3ddc7dc1edba17b825` passes Apple run `40839976736`
on attempt 1: all 24 pending modes (10 plain, 10 ASan/UBSan, 4 TSan),
then the real iPhone ARM64 Core and its ABI30/88-export, codegen and static
passive-dlopen checks. Artifact `12883027017` is the verified Core to reuse
for the next requested IPA when its 190 exact inputs remain unchanged.
Binary: 77,251,592 bytes, SHA256
`13b4c505434a7a0291abad47fa157ce0c9e20741e297f24dc2575e760e0e691b`.

The downloaded ZIP and dylib were independently authenticated against the
source identity, 24 report/output digests, 313 native postimages and 42
supplements. PPU `a987639e9f838d1c` and SPU `d070cb361bdef607` remain
unchanged. Reuse the already passed historical suites; do not rebuild this
unchanged Core for packaging. The cumulative inventory contains 13 runtime
changes in 23 distinct native/recipe files since delivered IPA593:
`docs/rpcs3-core-followup-2026-10-29.md`. Durable receipt and identities:
`docs/evidence/rpcs3-bo2-exact-20261029/apple-core.json` and `apple-core/`.

Apple host measurements confirm both dense-lookup gains and slower misses,
first slots or recycling in some paths. No iPhone FPS, runtime-loading or
GoW3 freeze fix is claimed. No IPA or public release was produced. Preserve
the concurrent validated MeloNX engine82 artifact `12883480724` and its
separate runtime-validation proof when the next IPA is requested.

## RPCS3 exact texture lookup and framebuffer keys — 29 October 2026

After warm source `64ca0a0` and receipt `6d80aaa`, two native paths change:
uncompressed exact hits use the existing address index under the cache reader
lock, and framebuffer cache keys initialize all 64 bits. Blocks up to sixteen
slots retain the old lookup body. On failed exact validation, preserve each
invalidated slot's original position before `simple_array::erase_if`: it swaps
with the tail, so dropping dirty entries early changes merge/validation order.
`find_cached_texture` and the unlocked presentation specialization stay unchanged.

Final Clang 22 and GCC ASan/UBSan checks pass: 13,492 texture queries, 3,365
debug cases and 4,036 mutations; 103,936 FBO-key constructions per version and
1,026 real cache-body queries. Dense exact hits cost less on the host; misses
and first-slot hits can cost more. FBO padding variation is reproduced with
Clang but can be masked by GCC optimization. No iPhone FPS/cache-miss claim.
Record `runtime_bo2_exact_20261029`; details/evidence:
`docs/rpcs3-bo2-exact-2026-10-29.md` and `docs/evidence/rpcs3-bo2-exact-20261029/`.
Source `df0300f` passes the committed contract: 190 exact inputs, 313 native
postimages, 42 native supplements, four final host reports and nine preserved
earlier programs. Recording the receipt executes no compiler or native suite.
The canonical delta has 313 postimages, 311 previous ones unchanged. Invert
the exact fixture before warm and older fixtures. Preserve the old extracted
test programs, PPU/SPU identities, ABI30/88 exports, IPA593 and MeloNX engine81.
The shared future Apple gate has 24 pending modes; no Core, IPA, release,
new telemetry or player setting is introduced by this source cycle.

## RPCS3 BO2 recurring-cost follow-up — 29 October 2026

After `66b81952`, eight reviewed source paths reduce recurring RSX work:
an exact-address index for compressed texture lookups in blocks above sixteen
slots; bit-exact viewport/scissor reuse through all four Vulkan writers; and
completion wakes only when the winning CAS advances the EID. Texture checks,
candidate order, pipeline invalidations, explicit drains, fences and submissions
remain authoritative. The presentation specialization `check_unlocked=true`
must stay on its historical linear walk: its local locking does not establish
safe concurrent reads of the new vector. Resource-less retags and clear must
remove old index entries. No new field or layout change in texture sections.

The six targeted host reports pass: three plain Clang 22 runs, viewport
Clang ASan/UBSan, texture GCC 13 ASan/UBSan and completion GCC 13 TSan.
Texture: 22,753 queries / 8,618 mutations; identical first matches and validation
order. Dense-block lookup costs fall in the host model, but first-slot hits,
recycling and index memory cost more; do not turn those measurements into an
iPhone gain. The 593 logs lack block/hit distributions and viewport/scissor
counts. Completion wake counts do not explain time inside vkQueueSubmit.

Record `runtime_bo2_warm_20261029`, fixture
`test/fixtures/rpcs3_bo2_warm_20261029.diff`; details and exact evidence:
`docs/rpcs3-bo2-warm-2026-10-29.md`,
`docs/evidence/rpcs3-bo2-warm-20261029/`. The canonical delta has 312 paths:
304 prior postimages unchanged, seven changed, and existing upstream
VKOverlays.cpp newly covered. Reverse this delta before the overlapping older
fixtures. Previous CPU-write/sampler/packet harness bodies remain identical.
The contract binds 182 inputs and 37 native supplements, reusing the earlier
170-input receipt and PPU/SPU proof. The next requested Apple gate has twenty
modes: fourteen still-pending follow-up modes and six new modes. No historical
delivered suite, CMake, Core or IPA build is replayed to record the source proof.
Preserve private IPA 593, the validated MeloNX engine 81 artifact, prior BO2
shader/admission corrections, ABI30/88 exports and JIT cache identities.
No delivery number, player setting, telemetry, release or device FPS claim.

## MeloNX SSBU startup continuation — 29 October 2026

The recent SSBU log measures 19.399 seconds from selection to first Metal
presentation, including 11.411 seconds loading 2,743 cached shader programs.
Its old prefix is excluded. No app/engine identity or menu-ready marker is
present; the older SSBU interval is not a controlled comparison.

On verified engine 81, cached Vulkan programs now use the existing background
scheduler even with gameplay async shaders disabled. Modules still validate;
only optional initial pipeline warm-up leaves link readiness. Required draws
and dispatches remain synchronous unless both async and skip flags allow it.
The first fatal warm-up failure is retained per renderer and propagated even
for an unused program. Cleanup joins remaining demand tasks in finally.
The threaded transport removes CommandHelper's silent catch, publishes failures
before waking waits and does not replay a partially consumed queue. Shader
translation workers are joined in finally before failed startup can return.
GPU readiness has terminal failure/cancellation states; an active initializer
must unwind before guest threads leave through KThread.Exit without CPU work.
Guest stop still precedes GPU disposal.
Launch preflight also removes its duplicate firmware scan; the version reader
still performs one fresh scan with the same version/error behavior.

Evidence and status: `docs/melonx-startup-2026-10-29.md` and
`docs/evidence/melonx-startup-20261029/`. All five targeted host checks and the
complete managed library build pass. Fifteen of 4,095 generated source/project
files change; 74 preparation inputs are bound by hash. Apple engine 82, source
`ebcee352`, passes all five new host gates, both NativeAOT library builds and
the exported ABI in run `40837997888`. That run remains failed overall: its
smoke requested Stop after two seconds, before the first cold GPU startup
completed, then correctly rejected that cancelled session's missing guest SVC.
Both sessions closed cleanly; only the warmer second session executed the SVC.
The test-only correction waits for a new per-session SVC before Stop and keeps
two distinct proofs, memory lifetime checks and explicit deadlines. Focused
runtime validation `40841402428` passes on attempt 1, test source `e46ace78`:
two real guest SVCs (sequences 39 and 56), two clean closes and two released
memory-backing sessions. It authenticates original artifact `12882675844`,
both libraries, 74 preparation inputs, four recipe inputs and the Swift hosts.
Reuse validated artifact `12883480724` from that runtime-validation run:
its binaries retain engine source `ebcee352`, and its envelope retains the
original failure plus the corrected proof. ZIP SHA-256 is
`be55d705ea93ae27c1756c29c3ec7a16ec51c60b9ace10556dcc751a00f5af45`.
Do not rebuild these successful binaries or replay unchanged host suites for
the next authorized packaging. A blocked
speculative worker in the 2,743-program test proves readiness independence,
not seconds saved on iPhone. Workers are bounded; the pending queue is not.
Preserve concurrent RPCS3 work merged in `fe587e27` and delivered private IPA593.
No new IPA, release, player setting, persistent cache format or telemetry is
part of this engine work. A device run is still needed for launch-time/FPS
claims. Do not rebuild unchanged successful engines when packaging the next IPA.

## RPCS3 BO2 stutter follow-up — 29 October 2026

After verified source `7d1ca65c`, synchronized with concurrent MeloNX engine 81
receipt `cfba697b`: protect host compiler-ticket release with the existing
admission mutex; normalize only provably unused fragment-input properties in
the private cache key; clone a new FP key under the writer lock before parallel
lookups can observe it. Three canonical paths change, 308 remain byte-identical,
including all thirteen device593 corrections. No PPU/SPU codegen, ABI or player
setting changes. Record/fixture: `runtime_bo2_followup_20261029` and
`test/fixtures/rpcs3_bo2_20261029.diff`. Details and exact evidence:
`docs/rpcs3-bo2-followup-2026-10-29.md`, `docs/evidence/rpcs3-bo2-20261029/`.

Source `a732853d` passes the committed contract: 170 exact inputs, 311 canonical
postimages, 27 native supplements and eight existing host reports bound to
the reconstructed test programs. The evidence-only follow-up preserves these
inputs. No native suite, compiler or CMake runs to record that final receipt.

Input analysis is lazy, skipped for neutral properties and cached until
`fragment_program_ucode_dirty`; conservative results are cached too. The
historical common analyzer and RSXThread remain unchanged. Do not restore the
rejected eager per-instruction analysis without new cost evidence. Preserve
TXD's three operands, conservative malformed/flow/indirect fallbacks, original
guest properties and compilation outside the key publication lock.

The 593 BO2 logs show 32 long graphics creations totaling 19.926181 s and
15.750841 s of fragment-library work; they do not run this candidate or 7d1.
Windows 19–20 have 111 new FP programs, 8 FS compilations and 115 FS cache hits;
these independent counters do not prove 103 of 111 were individual cache hits.
Host equivalence and concurrency checks do not prove extra iPhone FPS or
elimination of the 32 cold calls. Reuse previous receipts; the future Apple
gate runs the eight still-pending device593 modes and six new BO2 modes,
without replaying historical native suites or CMake identity calculations.
No Core/IPA/release, telemetry or new delivery number is part of this work.
Preserve private IPA 593 and the validated MeloNX engine 81 artifact.

## MeloNX rendering CPU follow-up — 29 October 2026

Five additional guarded adapters follow engine 80: geometrically growing
pipeline tables and order-sensitive pipeline hashes; complete bindless key
hashes; clean descriptors for unchanged buffer assignments; a bounded
memory-tracking locality shortcut; and linear texture-region intersection for
valid contiguous mappings. Six production files change. Equality, resource
ownership, dirty/protection signals, descriptor invalidations and fragmented
texture fallbacks remain authoritative. The short-mapping and overflowing
texture-layout cases found in review are covered, including immediate matches.
Final targeted production-code checks and complete managed library build pass.
Apple engine 81, source `9dd570ee`, passes run `40827952992` on attempt 1:
five new gates on macOS ARM64, iOS/simulator NativeAOT libraries, exported ABI
and two ARM64 simulator homebrew sessions. Artifact `12878071074` is the exact
verified engine to reuse for the next IPA; do not rebuild unchanged sources.
Evidence: `docs/melonx-fps-followup-2026-10-29.md` and
`docs/evidence/melonx-fps-20261029/`.
Host timings/allocations are controlled workloads, not measured Hogwarts
iPhone FPS or resident RAM savings. Preserve the concurrent RPCS3 follow-up
through `7d1ca65c`, private IPA 593 and its delivered identity. This work does
not deliver a new IPA, public release, runtime setting or telemetry.

## RPCS3 follow-up from delivered IPA 593 device logs — 29 October 2026

Source candidate after `571dbc08`, synchronized with concurrent MeloNX
`a33eee84` and its Apple receipt `58809ae6`: correct NV308A/NV0039/NV3089 CPU-write texture invalidation and the
already-bound sampler bypass; select the exact MoltenVK presentation queue
instead of falling back to a full drain whenever two queues exist; reduce JIT
object-read probes/seeks with bounded positional reads; pair queue-packet `new`
with `delete`. Thirteen source files change; 298 previous canonical postimages
remain identical and three existing upstream NV47 files enter the delta.
Record/fixture: `runtime_device593_followup_20261029`,
`test/fixtures/rpcs3_device593_20261029.diff`. Details and exact source-bound
evidence: `docs/rpcs3-device593-followup-2026-10-29.md` and
`docs/evidence/rpcs3-device593-20261029/`.

Source commit `cf85c52e` passes the complete committed contract: 160 exact
recipe/test/dependency inputs, 311 canonical postimages, unchanged source ABI
header/88 export declarations and authenticated delivered reference. The final
evidence-only commit preserves those inputs; no additional native suite, CMake,
Core or IPA compilation was run to record the proof.

The new process is build593/PID47785/A18Pro. Do not count the first 3,488 lines
of `performance.1` (build588/Bladestorm), duplicated diagnostics or old-prefix
milestones as fresh observations. BO2 has separate cache-read and first-use
Metal-pipeline stalls. AC's stable interval is 2,262 frames / 82.778834 s
(27.325826 FPS), with no SPU/shader compilation; submission durations can overlap
RSX offloader work. GoW3 has 973 drains / 973 frames before the freeze, not a
proven causal connection to it. The freeze at label60300510 still contains
69,872 successful PUTLLC and 3,609 completed SPU event waits over 15.178217 s
without rendering. Its missing guest label producer is unresolved. Never force
the label, skip the wait, or describe this candidate as a demonstrated freeze
fix. Neither old/new restored GoW3 intervals nor rotated-away BO2 counters
support an A/B FPS claim. NeoSwap has no new mapping failure or donor loss in
the available AC interval.

The JIT edit changes only three I/O bodies, not emission/linking/relocations.
Its exact compatibility alias retains PPU `a987639e9f838d1c` and SPU
`d070cb361bdef607`; future/wrong-path hashes are not aliased. Reuse verified
history and rerun only changed production paths. The device593 route in the
existing runtime Core gate requires native GCD when later run on macOS and
authenticates the delivered c143be63 receipt without recursive historical tests.
No new Core/IPA/build number/release, runtime telemetry or manual player setting
change is part of this source work. Host checks do not establish disappearance
of weapon/torch artifacts or any additional iPhone FPS. IPA593 remains the
delivered application baseline; preserve the concurrent MeloNX candidate.

## MeloNX Hogwarts memory candidate — 29 October 2026

On `571dbc08`, after delivered IPA 593: correct per-slot texture pool ownership
and obsolete texture expiry, remove redundant bindless reference arrays while
preserving queued command snapshots, and reuse Vulkan array storage sets with
barriers and descriptor invalidation intact. Three guarded adapters are wired
into prepare_embedded and the engine workflow. Targeted production-code host
tests and the complete managed library build pass. Apple NativeAOT candidate
`a33eee84` passes run `40822941790` (engine 80) on its first attempt, including
two ARM64 iOS simulator sessions; artifact `12875966763`. Reuse that exact
engine artifact when preparing the next IPA instead of rebuilding it unchanged.
Evidence and limitations:
`docs/melonx-hogwarts-memory-2026-10-29.md` and its evidence directory.
The supplied log shows a 2.6 FPS median in the final slow phase, high background
GC activity and renderer congestion; it has no explicit application/engine
identity. Host allocation reductions are not measured iPhone FPS or resident
RAM savings. Keep private IPA 593 and its delivered tree as the application
baseline; this source candidate does not change its contents or delivery ID.

## Private IPA 593 — delivered with latest RPCS3 and MeloNX, 29 October 2026

The maintainer explicitly authorized this new IPA. Private version 0.0.8 (593)
was built from `b13dc115`, successful run `40818195216`, artifact `12873597603`.
IPA: 188,304,666 bytes; SHA256
`6d8fe2635ef793ac24a34d760771d726174313b22f2485b1b154698c79881806`.
RPCS3 candidate `c143be63` / run `40814736023` and MeloNX `2f535c3` /
run `40811657940` are reused, with their original identities and signed payloads
verified again on the downloaded IPA. All 85 Mach-O payloads retain code/data
and ABI through signing; 88 signature records pass. The application and its
seven extensions are version 0.0.8 (593). No physical-device/FPS result.
One application build; no engine rebuild or native-suite replay. StikJIT cache
reused. Job: 937 s; Xcode: 385.55 s; signing/export: 46.46 s. No rerun.
Private file saved for the maintainer; ephemeral recipient private key deleted.
No public release or tag. Re-sign with SideStore before installation.
The next delivery baseline is the delivered 593 tree
`bb3c99e15e52ac109d5eaf827c80cb8e5c7759c6`, recorded in
`docs/evidence/rewind593/host-tree593.json`. Do not reuse build 593.
Evidence: `docs/evidence/rewind593-delivery.json`; details:
`docs/rewind593-test-ipa.md`. Preserve the candidate Core identity verbatim;
use its specific adapter and exact host/Core ABI/header compatibility checks.

## MeloNX runtime optimization, second cycle — 29 October 2026

On `075d84a4` / delivered588 engine7be: targeted JIT dataflow; cold primary
upload arrays expire with linear compaction; texture comparison snapshots and
fragmented conversion inputs are reused; dedicated lazy16MiB texture staging
with fences/OOM fallback; corrected nonzero-offset copy bounds; retiring worker
pipeline work and valid checkpoints preserved when eligible. No new setting,
telemetry, GC knob, application build number or release. Details and exact
host proofs: `docs/melonx-runtime-cycle2-2026-10-29.md` and its evidence folder.
The new log has two Hogwarts v1.0.5 sessions but no build/engine identity;
do not claim it proves an IPA588 regression. Host allocation/codegen results
are not physical iPhone FPS or whole-process memory measurements. Preserve
the delivered588 application and RPCS3 Core592 when packaging this engine.

## RPCS3 runtime follow-up on delivered 588 / Core 592 — 29 October 2026

Source candidate on `075d84a4`: avoid ineligible speculative texture hashes,
reuse exact completed-shader entries, retain only Vulkan states declared
dynamic by the next pipeline, and skip occupied VM allocation intervals with
the original scan retained for intervals that reject only one candidate.
Nine canonical files change; the other 299 postimages and the PPU/SPU codegen
inputs remain identical. The first VM version was corrected after a targeted
benchmark exposed a dense-small-allocation regression; do not restore it.
Details, limits and commands: `docs/rpcs3-runtime-log-followup-2026-10-29.md`.
Record/fixture: `runtime_log_followup_20261029` in the canonical manifest and
`test/fixtures/rpcs3_runtime_log_followup_20261029.diff`.
Host production-body tests and source integration are recorded with exact
hashes; historical tests are reused only after generated-code identity checks.
Authorized Apple candidate `c143be63`, successful run `40814736023`: eight
targeted ARM64 modes pass, then one Core compilation (11m40s); actual arm64
iOS binary, ABI30, 88 exports, PPU/SPU identities and static passive-load analysis verified.
Core SHA256 `0966c03dcd264fdbcf813f9a7af320434c5dac0f555c1460c917358394b1f0ac`.
Receipt: `docs/evidence/rpcs3-runtime-20261029b/apple-core.json`. The earlier
run stopped before Core compilation on a test-only enum-range defect; its
correction leaves the canonical patch unchanged. No IPA, new delivery number,
physical-device result or release. Delivered588/Core592 remains the application
baseline; the dense VM timing limitation still requires device measurement.

## Private IPA 588 / RPCS3 Core 592 — delivered, 29 October 2026

The maintainer explicitly authorized pushing on `Claude` and delivering a test
IPA with the latest MeloNX fixes. Private 0.0.8 (588) delivered from `4a20e8e9`,
successful run `40803513166`, artifact `12867282283`; IPA 188,291,408 bytes,
SHA-256 `dfa8aa7a1d60e29226dbaa260cd12bf44a9a91510d4e25805ec6aaa0a1af9b70`.
Core592 `27b5cc99`, run `40800626294`, contains the six runtime optimizations
of `c4d59884` / `9938d918`; three new Apple ARM64 suites pass normally and
under ASan/UBSan. The linked Core also bypasses both UDIV on its 1 GHz paths.
MeloNX Apple engine `7be2a83b`, run `40794453036`, artifact `12864051465`, is
reused. Its 57 compiled inputs and signed payload are verified. Code, data,
ABI and signatures of the final 85 Mach-O images pass; both changed engines
were independently compared with their verified raw artifacts after handoff.
Delivery: 601 s (10.02 min), Xcode 218.46 s (3.64 min), signature/export 36.10 s.
The first assembly stopped before Xcode on two nonexistent JSON receipts;
the guard now authenticates the actual successful stdout-only step.
Evidence: `docs/evidence/rewind588-delivery.json`; details:
`docs/rewind588-test-ipa.md`. The baseline of the next delivery is the delivered
588 tree `81db3172b5ffb79e724c5ff6f944a61898fb7252` (`host-tree588.json`).
Do not reuse build 588 or Core592. No public release, iPhone gameplay test or
FPS gain is claimed. Re-signing with SideStore is still required.


## RPCS3 runtime optimization candidate — 29 October 2026

Source only, on Core 591: early exact texture selection with one-pass merge
fallback, private Vulkan dynamic-state key normalization and a bounded exact
recent-pipeline lookup. Four canonical files change; other engines and PPU/SPU
codegen identities remain. See `docs/rpcs3-hotpaths-2026-10-29.md`, manifest record
`runtime_20261029` and `test/rpcs3_hotpaths_test.py`. Native host correctness,
ASan/UBSan and TSan pass; canonical materialization reproduces all 305 postimages.
No Apple SDK/Core build, IPA, iPhone FPS gain, new telemetry or release is claimed.
The delivered 587/Core 591 baseline remains until a new build is authorized.

Followup on `c4d59884`, also source only: exact 1 GHz clock conversion, typed
descriptor pools reserved on first use at their original full capacity, and
coalesced descriptor flush notifications under the existing manager mutex.
Three additional upstream files enter the canonical delta (308 postimages);
the previous four optimized postimages stay identical. Record:
`runtime_followup_20261029`; details and exact evidence:
`docs/rpcs3-clock-descriptors-2026-10-29.md`. GCC, Clang 22, ASan/UBSan
and descriptor TSan checks pass with assertions enabled. Freestanding LLVM 22/A18
assembly executes zero UDIV on each specialized 1 GHz path instead of two;
the 24 MHz fallback retains its arithmetic and adds the frequency check.
This is neither a linked Apple SDK build nor a device timing result. No new
telemetry, IPA, build number or release. PPU/SPU codegen identities are unchanged.

## MeloNX engine optimization candidate — 29 October 2026

On the delivered 587 engine: paired NEON context transfers, linear JIT block
partition, two-page decoder reader, stable Vulkan texel-buffer views, generation-based
pipeline snapshots, pooled bookkeeping/FIFO ownership, fewer GPU PTE reads,
atomic controller snapshots, stack rumble packets, bounded program-queue waits
and cancellation of undemanded shader warm-ups before renderer teardown.
Details and exact host evidence: `docs/melonx-engine-optimization-2026-10-29.md`
and `docs/evidence/melonx-engine-optimization-2026-10-29/`.
The real embedded library compiles in Release on Linux (.NET 10.0.100;
test-only managed/Linux settings); generated ARM64 has not been executed.
No iPhone FPS/footprint result, new IPA number or public release is claimed.
Preserve the 587 baseline, other engines and existing caches/ownership.

## Delivery baseline: verify and rebuild only what changed — maintainer rule, 28 October 2026

The maintainer found the deliveries far too long: build 586 (run
`40744757151`) spent 85 minutes on the macOS runner, about 6 of them in the
Xcode and Flutter compile; the rest re-proved the history of every earlier
private build. From now on:

1. **Baseline.** The last private IPA delivered by a green delivery run is
   the baseline of the next delivery (585 when this rule was set, then each
   delivered build in turn). Its own delivery already proved its tree,
   recipe and receipts; a later delivery does not prove them again.
2. **Delta only.** A new delivery recipe starts from the baseline's recorded
   product tree and adds only the files of the new commits, each from the
   commit that validated it. It does not re-pin or re-verify the trees,
   recipes, nested views or receipts of earlier builds (558 up to the
   baseline), and does not re-embed or re-verify receipts of features
   unchanged since the baseline.
3. **Still checked:** the new commits (sources, tests, adaptations), each
   new or changed component (engine or Core run, by ID and digest), the
   legal and license bundle, and the final signed IPA (build number,
   signatures, compiled markers of the new changes, unchanged components by
   digest).
4. **One computation per job.** A shared contract is computed once per job
   (`build-utils/delivery_contract_memo.py`); a step that recomputes it is a
   defect to fix, not a cost to accept. The 586 recipe keeps file modes so
   the memo records (`contract_keeping_modes`, `0aede035`): the 579 view
   dropped the executable bit of `test/rpcs3_cell579_test.py`, so every step
   recomputed the whole contract (8 to 15 minutes each).
5. **Time.** Report each delivery's duration and its longest steps; aim for
   under 40 minutes end to end.


## Private build 587: MeloNX engine b2a28de, RPCS3 Core 591, durable per-game graphics — 29 October 2026

- Maintainer request (28 October): push the MeloNX fixes from the 586
  Hogwarts Legacy log with the latest RPCS3 fixes, and build once the
  bindless fix is ready.
- Hogwarts Legacy build 586 log (28 October, 22:19-22:32, one 12.7-minute
  session): the 90 s at 7 % or less device memory (kern.memorystatus_level)
  ran at a median 4-6 FPS, the 640 s at 8 % or more at a median 30 FPS (a
  correlation, not a measured cause); footprint 3.2 to 4.9 GiB of a
  6,143 MiB limit; upstream TrimCaches ignored both memory warnings (headroom
  over 768 MiB). About 400 bindless accesses still unbound, their handle IR
  named by the 586 diagnostic. The per-game resolution 0.75 set under 585 was
  1.0 right after the update and the first launch failed with
  localGameRequired (library path of the previous container). Lifecycle
  memory figures read "[redacted key entry]". asyncShaders off everywhere.
- Contents, on the delivered 586 tree (`20c69d8`):
  - MeloNX engine `b2a28de` (engine run `40788062624`, artifact
    `12861340590`): `adapt_device_memory.py` (`983f301`: GPU caches trimmed
    when the device has 7 % or less available, polled once a second, at most
    every 10 s; an Info line every 30 s with footprint, headroom, device share,
    texture/buffer caches and managed heap) and `adapt_bindless_sources.py`
    (`b2a28de`: nested constant-buffer phis and spilled constant-buffer
    handles bind exactly; OR of storage-buffer/input/local-memory loads and
    constants through the whole pool, except image stores and atomics, which
    would mark every pool texture modified; one log line per access bound
    this way; host shader cache version `7353 + 0x5242_0002`, one slower first
    boot per game). Synthetic Maxwell reproduction with ShaderTools: the
    cube/2D/3D forms bind, controls translate identically.
  - RPCS3 Core 591 (`12dd45b`, Core run `40782533853`, SHA-256
    `08903af6…`) with the Core 589 Assassin's Creed profile (`99a57a6`),
    bound through `rpcs3cell591_delivery_core.py` (RPCS3 session).
  - App and host: per-game graphics also kept in
    `Documents/MeloNX/rewindbox-graphics.json`; a game path under a previous
    container's Documents resolves under the current one (`c42012b`); the
    lifecycle detail is "memory <footprint>/<headroom>/<device %>/<donors>"
    (`59e65a2`).
- Recipe: `rewind587-baseline-delivery.yml` (generated from the 586 one;
  dispatch only). `rewind587_baseline.json.gz` holds the delivered 586 index
  and the 587 delta (37 files, 12 commits; the RPCS3 591 commits made from the
  maintainer's account are accepted by author); `rewind587_engine.py` applies
  every 586 engine check to the 587 engine; validators
  `validate_melonx_engine587_ipa.py`, `validate_rpcs3_core591_ipa.py`.
- Delivery: run `40789729450` (head `cd7ed1e`), artifact `12861577770`, IPA
  0.0.8 (587) SHA-256 `06c3f59f…0180`, 5,352 entries; decrypted with the
  private 587 key, equal to SHA256SUMS; 13 validators passed; receipts
  `MeloNX-engine587-identity.json`, `RPCS3-core591-identity.json`,
  `RewindBox-enhancements586-identity.json`. Evidence:
  `docs/evidence/rewind587-delivery.json`.
- Durations: 18 min end to end (macOS job 18.05 min with a 6.2-minute Xcode
  build, checks 8.3 min at the same time).
- Baseline of the next delivery: the delivered 587 index, tree `fed8b77`
  (`host-tree587.json` of the delivery, reproduced locally at `cd7ed1e`).
  Not tested on an iPhone; no FPS, frame time or memory gain is claimed.

## Private build 586: MeloNX engine 75a13f7, RPCS3 Core 587, Cheats & Enhancements — 28 October 2026

- Contents, on the delivered 585 tree (RPCS3 Core 585 on the 583 tree):
  - MeloNX engine `75a13f7` (commits `6314127`, `d8cd5f6`, `ac16f1c`,
    `6edcd57`, `75a13f7`; engine run `40734346962`, artifact `12838535262`), replacing
    the 582 engine `e55ca25`: GPU-thread allocations
    (`adapt_gpu_allocations.py`), blocking program waits and the depth-only
    warm-up key (`adapt_shader_waits.py`), misaligned JIT unit guards
    (`adapt_jit_decoder.py`), and `adapt_deferred_flush.py`: a texture
    write-back the GPU thread queues to the render thread is skipped when its
    guest memory was unmapped since (Hogwarts build 582 crash of 28 October,
    InvalidMemoryRegionException in the HostTracked fault handler on
    NeoStation.MeloNX.Render; one occurrence, not reproduced on a host), and
    `adapt_bindless.py`: bindless texture handles read through SHFL (Mesa's
    manual textureGrad, SAM/RAM) bind to the sampler array or the pool
    instead of reading 0 (Hogwarts black sky and background areas; the four
    textureCube failures of the log reproduced with the real translator and
    bound after the change); the host shader cache version changes, so each
    game's shaders are translated again once.
  - RPCS3 Core 587 (`a8a7ce1`, Core run `40718679248`, session 01BcZDeV):
    MoltenVK asynchronous submits behind an encode barrier, MetalFX ordering,
    boot canary; profile commit `147af30` (God of War III asynchronous
    submits Automatic, Black Ops II relaxed SPU reservations). Bound through
    `.github/diagnostics/rpcs3cell587_delivery_core.py`.
  - Cheats & Enhancements page and catalogues (session 01JA5QgP, commits
    `b451b10` to `d0f27cc`) with the 28 October withdrawal of the unlicensed
    60 FPS programs and the origin publication v2 (`68e28dd`; tests `4a19415`, `e017be1`; plugin registration `d0f27cc`): the
    app bundles `native/cheats/catalogue/v2/manifest.json.gz` (same games and
    chunk SHA-256 as the hosted v1 index) and downloads the codes of
    unhosted sources from their source (`resolveOriginPack`). From build 586
    the unified cheats validator binds the bundled index to
    `v2/VALIDATION.json` and the hosted v1 index to
    `docs/evidence/source-rights-withdrawal-fps478.json`.
  - Host journal: lifecycle transitions and `mem=footprint/headroom/device
    %/donors` (MeloNXMetalSessionViewController, MeloNXPerfJournal), to tell
    a system kill from a native abort (Hogwarts build 582 session that ended
    silently one second after returning from the Control Center).
- Hogwarts Legacy build 582 log (28 October, three sessions, 2-9 min): no
  "JIT Cache exhausted" (four on 27 October with builds 576-581, each about
  30 s in); median 30 FPS in two sessions; the recorded cutscene ran at
  1-11 FPS with the .NET background GC at 20-64 % of a core (what the 586
  allocation and shader-wait changes target; not measured on a device).
  Multi-second stalls (`{Nv}` WaitOnSyncpoint > 1000 ms, 17 today): the GPU
  thread waits on the render thread, which waits on pipeline compiles
  serialized by MeloNX's PipelineCreationLock (Metal compiles out of
  process); no fix justified without data — next test: the same scenes with
  "Shaders asynchrones" on. Black sky and background areas: `adapt_bindless.py`
  above (cyan areas not attributed).
- Recipe: `rewind586-baseline-delivery.yml` (dispatch only), the first
  recipe under the delivery baseline rule. `rewind586_baseline.json.gz`
  holds the delivered 585 index (6,904 paths, tree `37157ea`, derived once by
  the 586 recipe of `rewind586_tree.py`, which proved it against 558-585)
  and the 586 delta (1,132 files from 15 commits); `rewind586_baseline.py`
  pins baseline + delta + the recipe files of HEAD in one read-tree and
  checks each delta file against its commit; `rewind586_baseline_delivery.py`
  checks the 586 engine and iPhone host runs, the 587 Core run and receipt,
  downloads the engine and host proofs, and binds the engine evidence;
  `validate_melonx_engine586_ipa.py` and `validate_rpcs3_core587_ipa.py` check
  the signed engine and Core; the other validators of the signed IPA are the
  585 ones. Removed: receipts and checks of features unchanged since 585,
  earlier engines, logger proofs. The earlier recipe (`rewind586-delivery.yml`,
  run `40744757151`: 85 minutes on the macOS runner, stopped at the legal
  bundle) stays in the repository, unused.
- Delivery: run `40774769488` (head `ef909b8`), artifact `12854612274`
  (digest `abab575b…18ed`), IPA 0.0.8 (586) SHA-256 `d0f86d93…3b25`,
  5,352 entries; decrypted with the private 586 key, equal to SHA256SUMS;
  receipts `MeloNX-alloc586-identity.json`, `RPCS3-core587-identity.json`,
  `RewindBox-enhancements586-identity.json`; every validator passed.
  Evidence: `docs/evidence/rewind586-delivery.json`.
- Durations: 12 min end to end (macOS job 12.1 min, checks 6.75 min at the
  same time; compile 3.4 min). The earlier recipe spent 85 min on the
  macOS job after 14 min of checks (run `40744757151`); the first baseline
  run took 8.9 + 22.2 min (run `40769640791`, stopped at an engine
  validator call split across two lines). `rewind586_fast.py` batches the
  ~3,400 existence checks the 559-586 tree modules run on import.
- Baseline of the next delivery: the delivered 586 index, tree `20c69d8`
  (`host-tree586.json` of the delivery, reproduced locally at `ef909b8`).
  Not tested on an iPhone; no FPS, frame time or memory gain is claimed.

## Cheats & Enhancements catalogue — 28 October 2026 (source only, no build)

- Maintainer request: one catalogue of cheats, FPS, ultrawide, graphics,
  performance patches and HD textures for every embedded engine, activated
  in a few interactions. Full design, formats, sources and limits:
  `docs/ENHANCEMENTS.md`.
- Flutter page `lib/screens/enhancements/` (Game settings › Manage, first
  row; Settings › Tools, fifth iOS tool), service and adapters
  `lib/services/enhancements/`, strings `lib/l10n/enhancements_locale.dart`
  (12 languages), builder `tools/enhancements/`, data
  `native/enhancements/catalogue/` (index also bundled as
  `assets/data/enhancements_index.json.gz`; shards downloaded on demand from
  the `Claude` branch, SHA-256 checked).
- Adapters write only formats the engines already read at boot; no core or
  bridge source changed (ARMSX2 layout as of the third pass below): MeloNX Atmosphere cheats in
  `Documents/MeloNX/mods/contents/<tid>/RewindBox/cheats/` + `enabled.txt`
  (player cheats preserved), RPCS3 pending records in the bridge's own
  `Data/NeoStationUnifiedCheats/state.json` (tagged
  `source: rewindbox-enhancements`; published entries withdrawn so
  `managedTitleFile` keeps accepting the title), ARMSX2 `patches/<SERIAL>_<CRC>.pnach`
  + `[Patches] Enable =` in `gamesettings/`, Dolphin `$name` lines in
  `User/GameSettings/<GAMEID>.ini`. Every write is recorded in
  `Application Support/RewindBox/Enhancements/state.json`; restore is exact.
- The Tools row count changed from 4 to 5 on iOS (index 4): the contracts in
  `test/jit_backend_preference_service_test.dart`,
  `test/libretro_bios_checker_screen_test.dart`,
  `test/storage_tools_row_test.dart`, `test/storage_contract_test.py` and
  `test/neoplay_build397_integration_test.py` were updated accordingly.
- Checks run on Linux with Flutter 3.47.2, after rebasing on `e55ca25`: the Dart tests (new suites and the
  updated Tools contracts) and `test/enhancement_catalog_data_test.py` pass;
  `flutter analyze` reports no error and nothing in the changed files. The
  pre-existing failures of `neoplay_build397_integration_test.py`,
  `storage_contract_test.py` and the `build486/492` targeted runners need
  history absent from a shallow clone and are identical before this change.
  No device test, no IPA, no CI run, no release.
- Same day, second pass (rights review + expansion, `docs/ENHANCEMENTS.md`
  "Sources"/"Rights"): 17 pinned sources, 57,841 entries. 194 Switch titles
  whose authors restrict distribution are excluded from every Switch cheat
  source (fail closed, `RESTRICTED` in the builder); RPCS3 data declared
  CC BY-SA 4.0 (browser confirmation pending); NOTICE.md lists every source.
  Added: gbatemp-matias3ds and titledb Atmosphere cheats, KeatonTheBot and
  Fl4sh9174 exefs `.pchtxt` mods (MeloNX adapter writes
  `RewindBox/exefs/` while on), Gabominated, PeterDelta, CookiePLMonster and
  AeroWidescreen pnach groups merged into one SERIAL_CRC file, upstream
  Dolphin/Ishiiruka/Slippi/MPN/Admentus64 codes written with their bodies,
  RPCS3 duplicate PPU keys merged as yaml-cpp does. 64 Dart tests and the
  data test pass; no device test, no IPA, no CI.
- Same day, third pass (maintainer: keep only what can be integrated and
  respects copyright): 10 sources, 10,204 entries. Removed every source
  without a licence (switch-cheats-db, matias, titledb, KeatonTheBot,
  Fl4sh9174, Gabominated, PeterDelta, pcsx2_patches bodies): the MeloNX
  catalogue is empty (adapter kept, tested on made-up records). ARMSX2 now
  references the engine's own `patches.zip` (ARMSX2 `9d989ca9`) by name only
  (`[Patches] Enable =`, nothing in `patches/`, which would hide the zip) and
  writes the MIT CookiePLMonster/AeroWidescreen groups to
  `cheats/<SERIAL>_<CRC>_rewindbox.pnach` with their notices, enabled by
  `[Cheats] Enable =` and per-game `[EmuCore] EnableCheats` (previous value
  restored). Pnach files of the earlier layout are removed at the next
  change. Independent follow-up on 28 October: the RPCS3 Wiki General
  disclaimer and Help:Game Patches footer were directly browser-verified
  as CC BY-SA 4.0, except where otherwise noted; see
  `docs/licenses/rpcs3-wiki-2026-10-28.md`. The pre-existing unified cheat
  catalogue (`native/cheats/`) remains a separate unresolved rights review.
  Its current manifest has no active Switch source, but still lists
  `pcsx2_fps478` and `gabominated_fps478`. The confirmation does not clear
  those inputs. No history rewrite is implied by the documentation update.

- Unified cheat catalogue (`native/cheats/`), 28 October: 910 programs
  withheld by `tools/cheats/withdraw_fps478.py`, run once against index
  `095cf728`:
  - pcsx2_fps478, gabominated_fps478, nethersx2_fps478 and nds_fps478 (no
    licence);
  - 3 illusion0001 programs that differ from the official patch.yml. The
    other 280 are relabelled CC BY-SA 4.0.

  14 of the 874 packs were replaced. The importers are disabled, and
  `NeoUnifiedCheatCatalog.m` refuses these programs from old caches. The
  per-source register is
  `docs/evidence/cheat-source-decision-register-2026-10-28.json`. Maintainer
  decision, same day: keep every active source published (repositories
  without a licence are treated as free to use). The evidence search is in
  the register. See
  `docs/SOURCE_RIGHTS_FOLLOWUP_2026-10-28.md`. No history rewrite without
  explicit authorisation.

- Origin download, 28 October (maintainer: do not host codes, change
  nothing for the player). A source without a licence is listed by name
  and pointer only. The app downloads its original file at a pinned
  revision (`EnhancementCatalog._fromOrigin`, `EnhancementOrigin`), checks
  the SHA-256, then installs as before.
  - First source: switch-cheats-db, 36,980 Switch entries, back in the
    Cheats & Enhancements page; the 194 restricted titles are still
    excluded.
  - Licensed sources stay hosted.
  - The unified cheat catalogue (`native/cheats/`, Objective-C) is the
    next step. It needs a native port of the parsers and a macOS
    validation run that only the maintainer can authorise.

- Unified cheat catalogue, origin publication (v2), 28 October
  (maintainer: do not host unlicensed codes, change nothing for the player,
  do not break installed data). See `docs/CHEAT_ORIGIN_PUBLICATION.md`.
  - `native/cheats/catalogue/v2/` has the same games and chunk SHA-256 as
    v1. Programs of unhosted sources keep a recipe (byte ranges in the
    source's pinned file) instead of their code.
  - The app bundles v2 and refreshes from the v2 URL. Native
    `installPack` hands origin packs to the Dart `OriginResolver` (plugin
    channel `resolveOriginPack`), then verifies each chunk as before.
    Flutter registers the Dart handler before `main` (pubspec
    `dartPluginClass: NeoCheatCatalog`); `lib/main.dart` stays the Build
    419 reference. The plugin passes the origin cache folder (Application
    Support/RewindBox/Cheats/Origin).
  - Tools: `tools/cheats/origin/` (locate, recipe, skeleton, sources).
  - Tests:
    - `test/cheat_canonical_json_test.dart`
    - `test/cheat_origin_resolver_test.dart`
    - `test/cheat_origin_publication_test.dart` (needs `ORIGIN_DIR`)
    - `test/cheat_origin_v2_test.py`
    - `test/unified_catalog_origin_native.m` (macOS, through
      `test/unified_catalog_runtime_test.py`)
  - v1 stays hosted for older builds until the maintainer removes it.

## RPCS3 levers for every newly tested game — maintainer rule, 27 October 2026

Apply this rule to every PS3 game the maintainer tests from now on. Use only
the existing counters of `RPCS3-diagnostic.log` / `RPCS3-performance.log`;
add no new diagnostic. Never claim an iPhone gain without device logs.

1. **Already Automatic for every title (keep):** RSX thread priority (567),
   iOS QoS kept (569), passive-lock fairness (571), persistent SPU object
   cache, NEON paths, RSX idle park (Core 579; FIFO idle wait Yield only).
   Never narrow them to a title list.
2. **RSX idle park** (565) became Automatic for every title in Core 579. Its
   condition (FIFO empty for 1 ms) is title-independent; DBZ and GoW3 ran it
   since 565 and Bladestorm since 575 with no reported regression. With an
   older Core, add each new title whose RSX thread uses >= 0.5 core for a
   FIFO busy <= 50 % (DBZ 0.73/44 %, Bladestorm 0.68/31 %).
3. **Promote to every title after device logs of the 575 (GoW3, BO2,
   Bladestorm) show no stale or wrong texture:** texture validation per FIFO
   batch (559), scoped revalidation (573), texture residency cap (573, acts
   only above 768 MB of live textures). Until then, add a title to the two
   validation levers when its `RSXFRAME551 texture_ms` is >= 5 ms per frame
   (GoW3 8.1, Bladestorm 7.3, BO2 9-16; DBZ 0.5, Two Worlds II 2.4), and to
   the cap when `JITMEM gpu_textures_requested` exceeds 768 MB.
4. **Per title only, on the signature in its logs:**
   - no-op PUTLLC (565), when `SPUWAIT551 putllc_fail` is >= 1 M per 5 s
     window with accurate reservations on (DBZ 8-14 M, BO2 5.3 M; GoW3
     0.02 M, Bladestorm 0.04 M). It departs from hardware reservation loss,
     so it is never global.
   - deferred FBO write-back (560) and early submission (561), only on DBZ's
     pattern: a GPU wait on framebuffer commits or on a render-target
     readback every frame.
5. **Not a lever case:** freezes on the first launch of a game or mode
   (`SPUPROF obj_hits=0`, PPU modules compiled at boot, `SHADERSTALL538_EVENT`
   bursts). The caches are written; ask for a second launch of the same mode
   and check `obj_hits` and the stall count before changing anything. The
   shader interpreter and the deferred SPU compile stay off (maintainer
   decisions 551 and 436, confirmed 27 October 2026).
6. **Recording:** each title added goes to `rpcs3/ios/IOSTitleLevers.h` with
   its serials and the log values that justify it, in the Core's own record
   and doc. Enabled and Disabled stay unchanged; Disabled restores the
   previous behaviour.
7. **Promotion to every title** needs all three: a title-independent
   mechanism that acts only when its condition occurs, device logs on at
   least two titles without regression, and an unchanged Disabled path.
8. **No setting for the player** (maintainer, 28 October 2026): the player
   has as few settings as possible and is never asked to change one (the
   maintainer removed Write Color Buffers from the user settings on
   purpose); optimizations are automatic, in the Core or the title profile.

## RPCS3 Core 591: compiler and shader temporary lifetimes — 28 October 2026

- The maintainer asks to retain the IPA 585 five-game table and find concrete
  fixes for all of them; 586 logs do not replace that reference. Three new
  iOS-only common resource-lifetime fixes, on Core 589, are documented in
  `docs/rpcs3-cell591.md`: shader warmup raw fragment copies released only
  after both worker groups join (owned program clones remain); finalized SPU
  Modules detached/destroyed after native entry acquisition (MCJIT native
  objects, RuntimeDyld and LLVMContext remain); stack ObjectCache cleared on
  a recovered `try_add` error before the stack object dies.
- Four native files change including exact codegen compatibility aliases;
  the other 301 canonical files, non-iOS behavior, interpreter, title levers,
  settings, ABI, disk caches, JIT arena, NeoSwap and other engines remain.
  PPU/SPU codegen IDs stay unchanged; no new cold compilation required.
- Tests: `test/rpcs3_cell591_test.py`, inverse 589 fixture and native lifetime
  helpers. Local LLVM20 smoke and adapted ownership tests are partial. The
  actual LLVM22 C++ regression (cached objects, native globals and later
  cross-module relocations, plain + ASan/UBSan) is mandatory in the 591 Core
  workflow; absence cannot pass through a smoke-test substitute. No device
  result or FPS/RAM/crash gain claimed. No IPA or public release by this
  source task; any delivery starts from the delivered 586 baseline.
- Mac Core run `40782533853` at `12dd45b` (native source commit `5ec092c`):
  passed, actual LLVM22.1.8 plain + ASan/UBSan, 66 removed Modules, 64 later
  callers and a real cached-object hit with preserved native code/data.
  iPhone Core SHA256 `08903af6e8f2ff5ddf267c27fa3128df35d737037ec9fa359be024d5302d28f1`,
  ABI30, 88 exports, passive loading and both MoltenVK hooks checked.
  Archives and actual Core independently verified. Evidence:
  `docs/evidence/rpcs3-cell591-macos.json`. Job 12m47s, compile 9m57s,
  new tests/reference 1m08s. Binding module:
  `.github/diagnostics/rpcs3cell591_delivery_core.py`; it retains PROFILE589
  for a future 586-baseline delta delivery, without older receipt traversal.
  No IPA and no iPhone performance/crash claim.

## RPCS3 Core 589: Assassin's Creed joins the texture validation levers; Assassin's Creed relaxed reservations — 28 October 2026

- Build 585 iPhone logs of 28 October (`docs/rpcs3-cell589.md` section 1;
  every session is build 585, none carries Core 587):
  - Assassin's Creed (BLES00158), first run on the official RPCS3 entry
    (Multithreaded RSX, asynchronous texture streaming, relaxed ZCULL): the
    first boot compiled 175 PPU modules for 16.7 min, the next two found them
    cached. Steady game scene 12-29 fps: RSX thread 0.54-0.80 core, FIFO busy
    70-91 %, 1,040-2,170 draws per frame, 14.5-28.2 ms of texture preparation
    per frame (20-45 ms at 1,900-3,300 draws earlier), `OPT559 texture_epoch=0`;
    0.87-1.03 M data-changing PUTLLC per window under the writer lock
    (`wl_putllc` 0.98-1.32 s), PPU waits 1.26-1.71 s (`vm_range_episode`).
    268 Metal pipeline compiles over 50 ms: first launch, rule 5.
  - Black Ops II (585, accurate reservations): `FREEZE_DUMP no_frames` up to
    65 s, the six SPURS kernels looping GETLLAR/PUTLLC on the SPURS control
    line `0x2e20880`, the only running PPU thread found parked by the writer
    lock. In relaxed mode a PUTLLC within 0x80 of the SPURS address is a
    plain store: the 587 profile (shipped by 586) targets exactly this.
  - Bladestorm: 30 fps cap for 45 min; after a savestate creation 348 SPU
    programs recompiled (one 593 ms frame). Dragon Ball Z: one minute (menu
    60 fps), nothing comparable. God of War III: boots only, legacy config
    neutralized (`inherited=19 kept=0`).
- Core change (record `cell589`, three iOS files, codegen identities
  unchanged): `CELL589_TITLE_LEVERS` adds BLES00158 and BLUS30089 (serials of
  the shipped cheat catalogue) to the Automatic mode of texture validation
  per FIFO batch (559) and scoped revalidation (573), per rule 3 (texture
  preparation >= 5 ms per frame). Texture pre-validation (581/583) stays God
  of War III only. Mechanisms, Enabled and Disabled unchanged.
- Profile commit (separate from the Core commit): BLES00158 and BLUS30089
  `advanced.accurate_spu_reservations: false` over the official entry, Black
  Ops II's signature.
- Local: `test/rpcs3_cell589_test.py` (587 preimages from the reverse fixture;
  the two policy blocks compiled verbatim, plain and ASan/UBSan, 11 serials x
  3 modes, and the 587 blocks beside them: only the two Assassin's Creed
  serials change), ARM64 diagnostics of the two units equal to 587. Evidence
  `docs/evidence/rpcs3-cell589-host-linux.json`. The Dart profile test runs
  in the delivery checks (no Flutter in the session container). No iPhone
  measurement of 589; no FPS gain claimed.
- Core run `40778765122` (dispatched on `99a57a6`, the profile commit right
  after the Core commit `d802611`; the push run was skipped because its head
  was the profile commit): the 587 Core authenticated, the 589 test passed on
  the Apple Silicon runner (plain and ASan/UBSan, 587 blocks beside), Core
  SHA-256 `49fed8c0…15a6`, 88 exports, 138 recorded inputs, the new setting
  text present and the 575 three-title text absent, both MoltenVK hooks
  linked, codegen identities unchanged. Evidence
  `docs/evidence/rpcs3-cell589-macos.json`; delivery binding
  `.github/diagnostics/rpcs3cell589_delivery_core.py`. No IPA yet.

## RPCS3 Core 587: MoltenVK asynchronous submits made safe (encode barrier, boot canary), Black Ops II relaxed reservations — 28 October 2026

- Maintainer: the 551 launch crash came from asynchronous MoltenVK submits;
  "Tu peux apporter les correctifs". Core 587 goes into the MeloNX session's
  private 586 in place of Core 585 (maintainer, 28 October 2026); no separate
  587 IPA. `docs/rpcs3-cell587.md`.
- Cause found in MoltenVK 1.4.2 (source read, not proven by a 551 stack):
  asynchronous submits encode on a serial GCD queue after vkQueueSubmit /
  vkQueuePresentKHR return, and vkAcquireNextImageKHR releases, without a
  lock, the drawable of the image it returns, which a still-queued render or
  present of that image fetches. The shader cache dialog flips back to back:
  widest window in the first second, where every 551 boot ended.
- Core changes (record `cell587`, codegen identities unchanged, off-iOS text
  of the five shared VK files equal to 585):
  `CELL587_MVK_ENCODE_BARRIER` (new `ios/IOSMoltenVKExec.h`,
  `ios/IOSMoltenVKExecQueue.h`; `RPCS3IOSPlatform.mm` defines
  `rbx_mvk_exec_q_create`, the build renames the archive's only
  `dispatch_queue_create` reference to it with
  `build-utils/rpcs3/patch_moltenvk_exec_queue.py` after the 551 QoS patch,
  archive `b91a46f7…` -> `0ee6ae96…`; a marker queued behind each present;
  every acquisition waits for the last one; MetalFX handoff flushed and
  drained; `COREPROF OPT587`), `CELL587_MVK_ASYNC_CANARY` (new
  `ios/IOSMoltenVKAsyncCanary.h`; Automatic = God of War III; armed durably
  at Vulkan instance creation, ok after 900 guest flips or a clean renderer
  shutdown, a title found armed at boot is failed and keeps synchronous
  submits; `rewindbox-mvk-async-587.txt`).
- Profile commit (outside the Core): God of War III
  `experimental.moltenvk_async_submits` Disabled -> Automatic; Black Ops II
  `BLES01717` `advanced.accurate_spu_reservations: false` (583 logs: SPU-bound,
  1.1-6.3 M data-changing PUTLLC per 5 s window under the exclusive writer
  lock, 0.74-2.9 s of writer-lock acquisition, 0.3-0.9 s of PPU waits; FPS
  falls with them; same choice as God of War III since Build 412).
- Correction to an earlier remark: Black Ops II's RSX thread uses
  0.15-0.18 core, so asynchronous submits would not help it; its limit is the
  SPU writer lock. DBZ unchanged (synchronous, global profile).
- Host: `test/rpcs3_cell587_test.py` (preimages, contract, off-iOS, tool and
  build step) and `test/native/rpcs3_cell587_mvk_exec_test.cpp` plain,
  ASan/UBSan and TSan, including a model of MoltenVK's swapchain rules on a
  serial queue thread with RPCS3's pacing: 309-373 releases of a drawable
  still awaited without the barrier, 0 with it. The macOS job also runs
  `rpcs3_cell587_mvk_gcd_test.cpp` against the real libdispatch
  (`--require-gcd`). Evidence `docs/evidence/rpcs3-cell587-host-linux.json`.
  Not tested on iPhone; no FPS or crash result claimed.
- Core run `40718679248` (`a8a7ce10`, Apple Silicon; attempt 1 stopped on an
  HTTP 503 of the artifact API before any test, attempt 2 passed): the 587
  test with the GCD registry against the real libdispatch (plain, ASan/UBSan,
  TSan: the barrier stops at the queued present, later work keeps running),
  archive `b91a46f7…` -> `0ee6ae96…` and "MoltenVK encoding-queue hook linked"
  in the build log; iPhone Core SHA-256 `c638d4ce…00e8`, 88 exports, 140
  recorded inputs, codegen identities unchanged, the 587 markers in the binary.
  Evidence `docs/evidence/rpcs3-cell587-macos.json`. Binding module for the
  delivery that ships it: `.github/diagnostics/rpcs3cell587_delivery_core.py`.

## RPCS3 Core 585: early submission for God of War III — 28 October 2026

- Build 583 iPhone logs (`docs/rpcs3-cell585.md` section 1):
  - God of War III, same savestate as 581 (first window 1,066.7 vs 1,066.5
    draws per frame): light ~700-draw scenes 29-33 fps (median 30-34 ms)
    against 26-31 (32-38 ms); heavy ~2,000-draw scenes 16-19 fps (53-67 ms)
    against 12-13 (77-80 ms). The 583 counters barely moved (served 54-66 %
    vs 49-64 %, wasted 39-51 % vs 44-53 %, `worker_passed` 60-400 per
    window): the gain is not attributable to 583 with certainty.
  - God of War III reads one 1280x720x4 render target back every frame
    (`READBACK555 fault_read`, 3.69 MB, one per frame): 2.1-6.7 ms per frame,
    0.80-1.06 s per 5 s window in light scenes. Write Color Buffers (GameDB)
    causes it and stays on: the game needs it (lighting, cinematics).
  - Dragon Ball Z: 60 fps (cap) in 18 of 25 windows, 28-48 in five.
    Black Ops II: 60 Metal pipeline-compile stalls in game (median 0.57 s, up
    to 4.8 s per window), pipeline cache 671 -> 801 (new areas, rule 5).
    Bladestorm: 30 fps (cap).
- Core change (record `cell585`, three iOS files, codegen identities
  unchanged): `CELL585_EARLY_SUBMIT_GOW3`. Early Command Buffer Submission
  (561) Automatic = Dragon Ball Z and the six God of War III serials (rule 4:
  a render-target readback every frame). Mechanism, Enabled and Disabled
  unchanged. God of War III runs Multithreaded RSX (DBZ does not); the early
  submission uses the same `flush_command_queue()` as every other one.
- Local: `test/rpcs3_cell585_test.py` authenticates the 583 preimages and
  compiles the production gating code (plain and ASan/UBSan): Automatic on
  for God of War III and DBZ only, Enabled on for all, Disabled off for all,
  `decide` unchanged; ARM64 diagnostics of the 3 units equal to 583. The 585
  driver also checks `COREPROF OPT581` in the Core. Evidence
  `docs/evidence/rpcs3-cell585-host-linux.json`. No iPhone measurement of 585.
- `test/neo_swap_core_pin_test.py` fails at HEAD before and after 585 on the
  public `neoswap-ipa.yml` exact pin (`cfe92344` lacks
  `test/rpcs3_restore_eof_test.py`), unchanged by decision.
- Core run `40700604912` from `2b013636`: the 583 Core authenticated, the 585
  test passed on the Apple Silicon runner (gating, plain and ASan/UBSan); Core
  SHA-256 `363ea475…8510`, 88 exports, passive loading, 137 recorded inputs,
  the new setting text present and the 561 "only" text absent, codegen
  identities unchanged. Evidence `docs/evidence/rpcs3-cell585-macos.json`.
- Private 585 recipe (`rpcs3-cell585-delivery.yml`, dispatch only): the
  delivered 583 tree with the Core 585 recipe of `2b013636`;
  `rpcs3cell585_tree.py` / `rpcs3cell585_delivery.py` run the 583 recipe
  unchanged in `as_583()` (which runs the 582 one in its own `as_582()`);
  eleven validators wrap the 583 ones (identities renamed to 585; the
  MeloNX base modules' IDENTITY and expected() patched; the RPCS3 one binds
  Core run 40700604912 and adds the 585 setting text). Product trees equal to
  583 (the other agent's later MeloNX commits are not in this tree).
  Recipient `build-utils/delivery-585-recipient.pem`.
- Private 585 delivered from `2b08899d` (recipe of the same commit), run
  `40703700988` (checks + cold success, 56 min): IPA 0.0.8 (585),
  188,118,106 bytes, SHA-256
  `626a2f8b36cf2b1d2a9104e47c52c1272ce6fed09af9f4c9e1a7e53985655abe` (equal to
  SHA256SUMS), artifact `12825874417` encrypted for
  `delivery-585-recipient.pem`; RPCS3 Core 585 `2b013636` (run 40700604912,
  `363ea475…`, identity receipt equal), MeloNX engine `e55ca256` (582)
  unchanged; every validator receipt passed; decrypted and inspected
  independently (build 585, the 561/581/583 markers and the 585 setting text
  in the signed Core, the 561 "only" text absent). Receipt
  `docs/evidence/rpcs3-cell585-delivery.json`. Not tested on iPhone; no FPS,
  frame time or memory gain claimed. Do not reuse the number 585.

## RPCS3 Core 583: texture pre-validation pacing, God of War III only — 28 October 2026

- First iPhone logs of private 581 (God of War III, Black Ops II):
  - God of War III, comparable ~700-draw scenes, 579 + 581 vs 575:
    132-153 frames per 5 s window (26-31 fps) against 90-102 (18-20); median
    interval 32-38 ms against 49-54; `RSXFRAME551 texture_ms` 4.3-5.8 against
    8.6-12.5 ms per frame; RSX-side hashing 2.1-3.2 against 6.5-9.1 ms per
    frame. Heavy 2,100-2,600-draw scenes: 12-13 fps, about 5 % better.
  - The worker served 56 % of the >= 64 KiB validations and hashed 82.7 GB for
    42.9 GB served (48 % wasted), at about 17 GB/s.
  - `JITMEM texture_hash_*` counts every hybrid hash, the worker's included,
    and only the hybrid path (God of War III's FPS batch). Black Ops II does
    hash: 5,000-20,000 validations per window. Dragon Ball Z is unmeasured;
    the 581 doc's "hash nothing" is corrected there.
  - Black Ops II is SPU-bound (3.4-4.1 SPU cores, RSX thread 0.1-0.5): 20-28 %
    served for up to 0.13 core of worker time and 1,756-4,602 skipped
    main-memory ranges per window. Its three `FREEZE_DUMP no_frames`
    (3.0/6.6/7.6 s) coincide with Vulkan pipeline builds (up to 15 per window,
    5.5 s, 0.66 s max) and SPU compiles: first play of those areas, rule 5.
- Core change (`docs/rpcs3-cell583.md`, record `cell583`, five iOS files, the
  shared `texture_cache.cpp` change is inside its iOS block, codegen
  identities unchanged): `CELL583_PREHASH_PACING`.
  - Texture Pre-Validation Automatic = God of War III only.
  - The worker skips ranges the RSX thread already passed in this frame
    (`g_position`, `worker_passed`).
  - The RSX thread wakes the worker halfway through its prepared ranges
    instead of the 4 ms timeout (`worker_refills`).
  - New profile line `COREPROF OPT583`; `OPT581` unchanged.
- Local:
  - `test/rpcs3_cell583_test.py` runs the 581 model with the 581 worker and
    the 583 worker; 0 stale, both 581 mutations still caught. One GCC
    report: steady 70.6 -> 83.3 % served, tight loop 29 -> 67 %. The model
    is noisy: six repeated GCC runs give steady medians 81.3 % (51.6-82.1)
    -> 84.1 % (82.5-89.7), tight-loop medians 66.7 % (57.1-74.6) -> 77.8 %
    (69.0-79.4); one Clang run had 581 above 583 in steady state (81.7 vs
    77.4). The model gain is mainly the tight loop.
  - The unmap race of the model is bounded at 40,000 frames.
  - ARM64 diagnostics of the 4 units equal to 581; pin, scheduling and the
    583 driver contract (139 inputs).
  - Evidence `docs/evidence/rpcs3-cell583-host-linux.json`. No iPhone
    measurement of 583.
- Core run `40683438937` from `8ebca287`: the 581 Core authenticated, then
  the model passed on the Apple Silicon runner (one run each: steady state
  581 worker 69.8 %, 583 worker 83.7 %, ASan/UBSan 62.7 %, TSan 72.6 %;
  tight loop 37 -> 85 %; 0 stale; both mutations caught; 1,677 unmaps
  without a fault); Core SHA-256 `9aa3c7ee…57f4`, 88 exports, passive
  loading, 139 recorded inputs, codegen identities unchanged. The driver's
  marker list names `COREPROF OPT583` twice and not `OPT581` (copy slip);
  `OPT581` is checked by the Mac evidence and the IPA validator. Evidence
  `docs/evidence/rpcs3-cell583-macos.json`.
- Private 583 recipe (`rpcs3-cell583-delivery.yml`, dispatch only): the
  delivered 582 tree (MeloNX engine `e55ca25`, Switch discovery fix) with the
  Core 583 recipe of `8ebca287`; `rpcs3cell583_tree.py` /
  `rpcs3cell583_delivery.py` run the 582 recipe unchanged in `as_582()`
  (which runs the 581 one in its own `as_581()`); eleven validators wrap the
  582 ones (identities renamed to 583, the RPCS3 one binds Core run
  40683438937 and adds the three 583 markers). Product trees equal to 582.
  Recipient `build-utils/delivery-583-recipient.pem`.
- Private 583 delivered from `e6374d49` (recipe of the same commit), run
  `40686712890` (checks + cold success, 52 min): IPA 0.0.8 (583),
  188,117,202 bytes, SHA-256
  `f76718880cf321affd98c53f297822a8c22155a0ad3c440cef53bf5b0db105b3` (equal to
  SHA256SUMS), artifact `12818262071` encrypted for
  `delivery-583-recipient.pem`; RPCS3 Core 583 `8ebca287` (run 40683438937,
  `9aa3c7ee…`, identity receipt equal), MeloNX engine `e55ca256` (582)
  unchanged; every validator receipt passed; decrypted and inspected
  independently (build 583, the four 581 and three 583 markers in the signed
  Core, the 581 "Automatic follows Texture Validation Per FIFO Batch" text
  absent). Receipt `docs/evidence/rpcs3-cell583-delivery.json`. Not tested on
  iPhone; no FPS, frame time or memory gain claimed. Do not reuse the number
  583.
- God of War III reads back one 3.69 MB colour target per frame
  (`READBACK555 fault_read`, 2.1-7.2 ms per frame in 581) because the
  GameDB's Write Color Buffers locks every bound colour target. Turning it off
  is rejected (rule 8, and the game needs it); Core 585 targets the wait.

## MeloNX engine 582: JIT units end where another translation starts; Switch discovery off the main thread — 28 October 2026

- Builds 575-576 app.log: in 12 of 18 MeloNX sessions the iOS main thread ran
  at 86-107 % for 60-134 s from the first second: `MelonxLibraryScanner`
  computed a pure-Dart SHA-256 of whole Switch games (7-16 GB) on the root
  isolate for every file whose absolute path had no index entry (every game
  after iOS moves the app container), and nothing stopped it at a launch.
  Fix `32a0da60` + `63fdb7ed`: the MeloNX bridge hashes with CryptoKit on its
  own utility queue (F_NOCACHE, 4 MiB reads, cancelled between reads at
  `cancelFingerprint` or any launch, refused during a game; same digest);
  discovery does not start while `FrontendMediaGate` is held and stops at the
  next file when a hold begins; the index is saved after each digest and an
  entry follows its file into a new container (same relative path, size and
  mtime). `test/melonx_library_discovery_test.dart` (6 cases). CI:
  melonx-integration `40643006039`/`40648012242`, melonx-host `40643006036`
  (Swift compiled). The Navigation 512 scope test failure on `32a0da60` is
  pre-existing (same failure on `48b9865` and `05c2e03`).
- Engine commits `6d8929d0`, `e72895b6`, `e55ca256`
  (`build-utils/melonx/adapt_jit_decoder.py`, probe and test): a LightningJit
  unit ends where another translation already starts (`TranslatedEntries`,
  one bit per aligned word, set in RegisterFunction, cleared on
  invalidation), unless a branch within 1,024 instructions goes back past the
  entry (a loop around it; for an entry reached by falling through, any
  branch back past it) or the unit reached it by a forward branch of less
  than 256 bytes; guest code is read a 4 KiB page at a time (`CodeReader`)
  instead of one locked HostTracked read per instruction; a unit ends before
  an unmapped page and the 572 rule no longer reads a jump target there.
  Same clang ARM64 text through the production `MemoryManagerHostTracked`,
  every exit followed: compile time 13.2-13.8 s (577) -> 10.6-10.8 s
  (-20 %), host code 495 -> 450 MiB (-9 %), compile allocations -9 %, loops
  held by no single unit +0.3 %, unit hand-overs on a static walk +0.9 %.
  Probe: a 300-function layout translates 3,601 guest instructions instead
  of 542,100. Engine run `40665520797` (artifact `12806293726`). Adversarial
  re-verification (2.6 M decodes against upstream, all compiled): no
  correctness, crash or compile defect on aligned code; the misaligned-PC
  cases it found are guarded in the next engine.
- Private 582 recipe (`melonx-entry582-delivery.yml`, dispatch only): the
  delivered 581 tree with the three engine files of `e55ca256` and the four
  discovery files; `melonxentry582_tree.py` / `melonxentry582_delivery.py`
  run the 581 recipe unchanged in `as_581()` with the 577 engine's evidence
  (`old_engine()`), the inherited validators on `derived_ipa()` (this IPA
  with the 577 engine entries packaged on the 581 tree); ten validators wrap
  the 581 ones, `validate_melonx_entry582` binds the 582 engine (adapted-source
  markers, the probe's 582 cases, its run) and the compiled discovery fix.
  The delivery checks also run the discovery test. Product trees differ from
  581 in lib and packages only. Recipient `build-utils/delivery-582-recipient.pem`.
  Local dry run on a scratch worktree: tree pin, full inherited source
  contract, retained checks, engine evidence 563 to 582 against the real
  artifacts, ten of eleven embeds (the eleventh needs the macOS MoltenVK
  receipt), flutter analyze and the discovery test on the pinned tree.
- Private 582 delivered from `ecad3c40` (recipe of the same commit), run
  `40675054767` (checks + cold success): IPA 0.0.8 (582), 188,118,382 bytes,
  SHA-256 `002d07d18cd5812c724c57a5ceaeca52a06dd748feff9dbc5be6371b8937a0c5`
  (equal to SHA256SUMS), artifact `12813245444` encrypted for
  `delivery-582-recipient.pem`; MeloNX engine `e55ca256` (run 40665520797,
  identity `15aa1ac6…`, the engine artifact's dylib), RPCS3 Core 581; 22
  validator receipts passed; decrypted and inspected independently (build
  582, engine host `e55ca256`, the decoder adaptation in the engine
  identity, the eleven 582 receipts, the discovery markers in the Dart
  snapshot and the Swift bridge). Receipt
  `docs/evidence/melonx-entry582-delivery.json`. Not tested on iPhone; no
  FPS, loading-time or memory gain claimed. Do not reuse the number 582.


## RPCS3 Core 581: texture pre-validation by a worker thread (God of War III) — 28 October 2026

- Build 575 logs, God of War III: on iOS the texture cache confirms CPU
  textures by content hash, and under Texture Validation Per FIFO Batch (559)
  a texture is hashed again on its first use after each synchronization
  point, on the RSX thread: 461-815 ms per 5 s window (2.8-10.4 ms per frame,
  13-17 % of the frame, 7-10 GB) with the RSX FIFO 72-95 % busy. Dragon Ball Z
  and Black Ops II hash nothing.
- Core change (`docs/rpcs3-cell581.md`, record `cell581`, iOS only, shared
  files' off-iOS text equal to 579, codegen identities unchanged):
  `CELL581_TEXTURE_PREHASH` (new `ios/IOSTexturePrehash.h`, worker in
  `texture_cache.cpp`, setting Texture Pre-Validation, Automatic = the
  epoch titles). The RSX thread records the ranges (>= 64 KiB) it validates
  per frame; when an epoch starts, a worker hashes the ranges the previous
  frame validated next with the cache's own hash (identical results) and
  publishes them tagged with the epoch read before the bytes; the RSX uses a
  result only in that epoch, never for a section an RSX write revalidated
  (573), and hashes the rest as before. Local memory is read directly, main
  memory only under a `range_readable` vm range lock (unmaps wait for it,
  PUTLLC writers do not). The worker stops at RSX exit and only restarts on
  the next boot. Profile line `COREPROF OPT581`.
- Local: canonical delta rematerialized on `22f1152`,
  `test/rpcs3_cell581_test.py` (model: real code next to the 579 version on a
  real address reservation, vm range lock protocol, an unmapper on main
  memory; steady-state validations served by the worker 84 % plain, 81 %
  ASan/UBSan and TSan; 0 stale textures; both deliberate mutations caught;
  GCC 13 and Clang 22), pin source contract, Core scheduling, 581 driver
  contract (138 inputs), ARM64 syntax of the 8 touched units equal to 579.
  Evidence `docs/evidence/rpcs3-cell581-host-linux.json`. No iPhone
  measurement: no FPS, frame time or memory gain is claimed.
- Core run `40631132527` from `03956454`: the 579 Core authenticated, then
  the 581 model passed on the Apple Silicon runner (steady-state validations
  served by the worker 81 % plain, 79 % ASan/UBSan, 71 % TSan; 0 stale
  textures; both mutations caught; 1,771 unmaps without a fault); Core
  SHA-256 `a6e97d33…213c`, 88 exports, passive loading, the four 581 markers
  present, codegen identities unchanged. Evidence
  `docs/evidence/rpcs3-cell581-macos.json`.
- Private 581 recipe (`rpcs3-cell581-delivery.yml`, dispatch only): the
  delivered 579 tree with the Core 581 recipe of `03956454`;
  `rpcs3cell581_tree.py` / `rpcs3cell581_delivery.py` run the 579 recipe
  unchanged in `as_579()` (which runs the 577 one in its own `as_577()`);
  ten validators wrap the 579 ones (identities renamed to 581, the RPCS3 one
  binds Core run 40631132527 and adds the four 581 markers to the 579 ones).
  Product trees equal to 579. Recipient `build-utils/delivery-581-recipient.pem`.
- Private 581 delivered from `27fb83c3` (recipe of the same commit), run
  `40634129514` (checks + cold success, 46 min): IPA 0.0.8 (581),
  188,110,017 bytes, SHA-256
  `be80589d0b4f5d6df1f571c698164a69bcb42158f25f728ae7f3d0b2b1631390` (equal to
  SHA256SUMS), artifact `12794492017` encrypted for
  `delivery-581-recipient.pem`; RPCS3 Core 581 `03956454` (run 40631132527,
  `a6e97d33…`, identity receipt equal), MeloNX engine `afd0d4b0` unchanged;
  every validator receipt passed; decrypted and inspected independently
  (build 581, the four 579 and four 581 markers in the signed Core, the 575
  idle-park text absent). Receipt `docs/evidence/rpcs3-cell581-delivery.json`.
  Not tested on iPhone; no FPS, frame time or memory gain claimed. Do not
  reuse the number 581.

## RPCS3 Core 579: SPURS reservation_op wait, sleeping writer deferral, writer yield without depression, PPU spin timing, RSX idle park for every title — 28 October 2026

- Build 575 logs: the first God of War III boot of the process ended in 2 of 2
  cases (567, 575) on "vm::writer_lock is being used without cpu_flag::wait
  set by the caller!" in `cellSpursRemoveWorkload`; Black Ops II heavy PUTLLC
  took 116-197 us per writer lock while its PPU waiters averaged 25-31 timed
  waits per episode (the 571 gate deferring almost always, up to five SPUs
  spinning 500 us); every boot logs `cntfrq=1000000000 timer_scale=1`, so
  `busy_wait(n)` is n/100 ns on the A18 Pro (DBZ: 825 passive-lock episodes
  of 38 us per window against 0.3-0.6 us writer holds).
- Core changes (`docs/rpcs3-cell579.md`, record `cell579`, iOS only, off-iOS
  text of every file equal to 575, PPU/SPU codegen identities unchanged):
  `CELL579_RESERVATION_OP_WAIT` (vm_reservation.h, vm_locking.h, vm.cpp: the
  PPU caller holding its passive lock gets `cpu_flag::wait` around the writer
  lock and leaves through `test_stopped()`); `CELL579_GATE_SLEEP`
  (`ios/IOSPassiveLockGate.h`: a deferring writer spins at most 50 us, then
  sleeps on the starving count with `os_sync_wait_on_address` on iOS 17.4+,
  futex on Linux; the last starving waiter wakes one sleeper, each woken
  writer the next; trigger, 500 us bound and lock protocol unchanged);
  `CELL579_WRITER_YIELD` (new setting Writer Lock Yield Without Depression,
  Automatic = every title: the yield of `reservation_lock_wait`, run while the
  writer holds its exclusive bit, is `thread_switch(MACH_PORT_NULL,
  SWITCH_OPTION_NONE, 0)` from `ios/RPCS3IOSPlatform.mm` instead of
  `sched_yield()` = `swtch_pri(0)`; cadence and wait conditions unchanged;
  Disabled = 575);
  `CELL579_SPIN_NS` (`utils::spin_ns`, rounded up: passive_lock and seven lv2
  primitives wait the upstream 3 GHz durations, 6.7-8.3 us at 1 GHz, the same
  ticks as before at 24 MHz; `shared_mutex` untouched);
  `CELL579_IDLE_PARK_ALL` (RSX idle park Automatic for every title).
- Withdrawn after verification: RSX offloader priority and inline idle copies
  (565 ran every thread at one level with the same GoW3 RSX gap). Not done:
  DBZ ready-ahead readback (refuted), dedicated VkImage memory (MoltenVK
  residency cost not measurable off device), the BO2 no-op PUTLLC poll wait
  (refuted: BO2 session 4 is the menu; it also touches SPUThread.cpp, a SPU
  codegen source); the directed hand-off to the unacknowledged PPU's Mach
  port (only the undepressed yield is in).
- Local: canonical delta rematerialized on `22f1152` (six lv2 preimages
  authenticated against XITRIX), `test/rpcs3_cell579_test.py` passed three
  times (575 text reproduces the fatal error 15 times in the model, 579 0;
  gate model: 503 -> 75 us of writer CPU per full deferral; the yield body
  calls thread_switch(MACH_PORT_NULL, SWITCH_OPTION_NONE, 0) only with the
  lever on; ASan/UBSan, TSan), pin source contract, Core scheduling, 579
  driver contract, ARM64 syntax of the touched C++ units equal to 575
  (`RPCS3IOSPlatform.mm` is compiled by the macOS CI only). Evidence
  `docs/evidence/rpcs3-cell579-host-linux.json`. No iPhone measurement: no
  FPS, frame time or memory gain is claimed.
- Core run `40621029169` from `1f82f9d9` (completing `968920b1`, whose run
  stopped on a host-model assertion now reported, and `9297546a`, cancelled
  before the Core compiled): the 579 models passed on the Apple Silicon runner
  with the real Mach headers and `os_sync_wait_on_address` (`sched_yield`
  under five busy threads up to 22.4 ms, `thread_switch` 18 us; writer CPU per
  full deferral 501 -> 65 us); Core SHA-256 `8d6b91ae…7929`, 88 exports,
  passive loading, the four 579 markers present and the 575 idle-park text
  absent, codegen identities unchanged. Evidence
  `docs/evidence/rpcs3-cell579-macos.json`.
- Private 579 recipe (`rpcs3-cell579-delivery.yml`, dispatch only): the
  delivered 577 tree with the Core 579 recipe of `1f82f9d9`;
  `rpcs3cell579_tree.py` / `rpcs3cell579_delivery.py` run the 577 recipe
  unchanged in `as_577()`; ten validators wrap the 577 ones (identity renamed
  to 579, the RPCS3 one binds Core run 40621029169 and its 24 markers).
  Product trees equal to 577. Recipient
  `build-utils/delivery-579-recipient.pem`. Local dry run on a scratch
  worktree: tree pin, full inherited source contract, retained checks,
  every validator import, the 24 markers in the real Core.
- Private 579 delivered from `cb3450b8` (recipe of the same commit), run
  `40623320457` (checks + cold success, 44 min): IPA 0.0.8 (579),
  188,102,433 bytes, SHA-256
  `72781107834f22af4b1216f576fc7aad144514c6aa36598785b57d40405c873a` (equal to
  SHA256SUMS), artifact `12790455792` encrypted for
  `delivery-579-recipient.pem`; RPCS3 Core 579 `1f82f9d9` (run 40621029169,
  `8d6b91ae…`, identity receipt equal), MeloNX engine `afd0d4b0` unchanged;
  every validator receipt passed; decrypted and inspected independently
  (build 579, the four 579 markers in the signed Core, the 575 idle-park text
  absent). Receipt `docs/evidence/rpcs3-cell579-delivery.json`. Not tested on
  iPhone; no FPS, frame time or memory gain claimed. Do not reuse the number
  579.

## MeloNX engine 577: kernel wakeups, GC memory-load threshold, Hogwarts code arena, per-title pipeline cache — 28 October 2026

- Builds 575-576 app.log (26-28 October 2026): FINAL FANTASY TACTICS - The
  Ivalice Chronicles still froze 0.4 s after start (576 trace: every guest
  thread in a kernel wait, no service call after the save mount, no SVC
  failure). Hogwarts Legacy with its update ended 25-32 s after every launch
  on "JIT Cache exhausted" (512 MiB TXM arena); past loading, `.NET_BGC` used
  40-80 % of a core at 7-14 FPS. The shared Vulkan pipeline cache was over its
  128 MiB budget (Hogwarts 263-269 MiB, never saved) or replaced by another
  game's (Smash reloaded "0,00 KiB main data" after an FFT session).
- Engine commit `cfa51168` (`build-utils/melonx`): `adapt_kernel_sync.py` (an
  expired timed wait leaves the condition variable or arbiter waiter list at
  once, as Horizon's CancelWait; equal priorities stay FIFO;
  SignalAndModifyByWaitingCountIfEqual decrements when the signal leaves no
  waiter; DecrementAndWaitIfLessThan writes only below the threshold; a
  zero-timeout condvar wait returns TimedOut); `adapt_gc.py` adds
  `System.GC.HighMemoryPercent` 99 (on Apple the .NET GC reads the
  device-wide memory load, kern.memorystatus_level); `adapt_jit_arena.py`
  with `native/melonx/EmbeddedRuntime.cs` and `EmbeddedLaunchPreflight.cs`
  (the preflight asks for a 1 GiB TXM code arena for Hogwarts Legacy
  0100F7E00C70E000 with an update; the default arena is mapped if the helper
  cannot prepare it); `adapt_pipeline_cache.py` (one cache file per title
  ID, 384 MiB main budget, an unchanged snapshot is not rewritten, the former
  shared files are removed, MeloNX's MoltenVK keeps its retained MSL
  LZ4-compressed). `adapt_fft_boot_trace.py` removed. `afd0d4b0`: the launch
  preflight test's fixture. `d1f7b8dd`: MeloNXInputRouter takes the pad's
  profile-wide handler (which relayed every stick and trigger change to
  Flutter on the main thread) while a game owns the controller, and restores
  it at close or reconnection.
- Local: full prepare_embedded chain on the pinned source, Ryujinx.Library
  build, launch preflight test (14 checks). Engine run `40610510834`
  (artifact `12782599009`), host run `40609951631` (the Swift compiled).
  Whether the kernel fixes end the FFT freeze is unknown without a device
  log. No iPhone measurement: no FPS, loading-time or memory gain is claimed.
- Private 577 recipe (`melonx-sync577-delivery.yml`, dispatch only): the
  delivered 576 tree with the ten files of `cfa51168`/`afd0d4b0` (the trace
  deleted) and the router of `d1f7b8dd`; `melonxsync577_tree.py` /
  `melonxsync577_delivery.py` run the 576 recipe unchanged in `as_576()` with
  the 576 engine's evidence (`old_engine()`), the inherited validators on
  `derived_ipa()` (this IPA with the 576 engine entries); ten validators (nine
  wrap the 576 ones, `validate_melonx_sync577` binds the 577 engine and the
  router source). Product trees differ from 576 in native and packages only.
  Recipient `build-utils/delivery-577-recipient.pem` (the withdrawn
  interface577 recipe never built an IPA). Local dry run on a scratch
  worktree: tree pin, full inherited source contract, 577 and 576 engine
  evidence against the real artifacts.
- Private 577 delivered from `079b01cf` (recipe of the same commit), run
  `40612213771` (checks + cold success): IPA 0.0.8 (577), 188,098,576 bytes,
  SHA-256 `9dac3d422fbbffe0c2133b35d5709cf75fba32889d71c6fd2ef03e3a45c8ee5b`
  (equal to SHA256SUMS), artifact `12785001665` encrypted for
  `delivery-577-recipient.pem`; MeloNX engine `afd0d4b0` (run 40610510834,
  identity `bf560d80…`), RPCS3 Core 575; 21 validator receipts passed;
  decrypted and inspected independently (build 577, engine host `afd0d4b0`,
  no trace adaptation, the GC knob and the MoltenVK compression literal in
  the engine binary). Receipt `docs/evidence/melonx-sync577-delivery.json`.
  Not tested on iPhone; no FPS, loading-time or memory gain claimed. Caveat
  for the next Hogwarts log: `DualMappedNoWxCache` never frees host code and
  `InvalidateJitCacheRegion` makes a retranslation allocate anew, so if
  v1.0.4 retranslates continuously the 1 GiB arena only delays the crash
  (about 60 s instead of 30 s). Do not reuse the number 577.

## Interface option and controller navigation after a game — 27 October 2026

Maintainer request (video of the Switch playlist, `app.log`), branch `Claude`, no IPA, nothing pushed.

- **Controller lost after a game (cause found in the sources):** GameController keeps one `valueChangedHandler` per pad. `RPCS3GameInputController` replaced the menu bridge's handler at bind and set it to `nil` at unbind; `GamepadsListener` never reinstalled it for a pad it already knew, so the menu stayed deaf until the controller reconnected. The Dart navigation stack itself was restored correctly (log: `system_games_list` reactivated after each close). Fix: RPCS3 restores the previous handler; `GamepadsListener.reclaimHandlers()` (channel `reclaimGamepads`, `Gamepads.reclaim()`) reinstalls the menu handler on the main queue, called once by `GameLaunchManager._finalize` on iOS when any session ends (RPCS3, MeloNX, Dolphin, ARMSX2, libretro, external). Never call it while an engine owns the controller. Libretro and ARMSX2 (SDL) poll the pad and MeloNX restores its per-element handlers, so they are unaffected.
- **`⋯` playlist menu:** a Select (View) tap now latches the chord layer open (`GamepadNavigation.latchSelectLayer`); A/X/Y run one action and close it, B only closes it, only the focused layer can close it. Mute/refresh moved to X in that layer (View + X). Option **Show system bubbles** (`showSystemBubbles`, default on, 12 languages). Details: `docs/liquid-glass-ui.md`, last section.
- Tests: `test/select_layer_latch_test.dart`, `test/system_bubbles_option_test.dart`, contract guard in `test/ios_gamepad_navigation_test.dart`, reclaim count in `test/game_audio_handoff_test.py`. Swift/Objective-C++ not compiled here (Linux, no Apple SDK). **No iPhone or physical-controller validation.**

## MeloNX engine 576: shader-cache warm-ups off the game's start, attachment-less framebuffers, temporary FFT boot trace — 27 October 2026

- Build 572 app.log: Super Smash Bros. Ultimate spent 18 s in "Loading 2743
  shaders from the cache": the disk cache loader waited for each cached
  program's initial pipeline warm-up, compiled one by one by the single
  low-priority pipeline worker of a six-core iPhone. FINAL FANTASY TACTICS -
  The Ivalice Chronicles (010038b015560000, 0 cached shaders) froze 0.4 s
  after start, every guest thread waiting, 4 % CPU, no frame, no audio.
- Engine commit `301e0f86` (`build-utils/melonx`): `adapt_shader_warmup.py`
  (a cached program is ready once its shader modules are; its warm-up keeps
  compiling in the background; a draw that needs a queued warm-up promotes
  it to the demand worker; Dispose cancels a warm-up no worker took);
  `adapt_attachmentless_framebuffer.py` (a pass without attachments covered
  1x1 — Ryubing issue 103's FFT black screen — and now covers its viewports,
  device limit); `adapt_fft_boot_trace.py`, TEMPORARY, FFT only: first 300
  service calls at Info level and the HleProcessDebugger minidump at close.
  Remove the trace once the freeze is understood.
- Local: full prepare_embedded chain on the pinned source; Vulkan and HLE
  build; scratch probes (scheduler cancel/promote 13 checks, framebuffer
  sizing and trace budget 16 checks). Engine run `40591863306`. No iPhone
  measurement: no launch-time or FPS gain is claimed.
- Private 576 recipe (`melonx-warm576-delivery.yml`, dispatch only): the
  delivered 575 tree with the five files of `301e0f86`;
  `melonxwarm576_tree.py` / `melonxwarm576_delivery.py` run the 575 recipe
  unchanged in `as_575()` with the 572 engine's evidence (`old_engine()`),
  the inherited validators on `derived_ipa()` (this IPA with the 572 engine
  entries); nine validators (eight wrap the 575 ones, `validate_melonx_warm576`
  binds the 576 engine). Recipient `build-utils/delivery-576-recipient.pem`.
- At the maintainer's request 576 also carries the StikDebug fallback removal
  (`504f9c08`, the only application change since 575): its three product
  files (lib, packages) and tests from `504f9c08`, the two deleted Dart files
  removed, `test/storage_contract_test.py` from `bfbb8067`. The product trees
  differ from 575 in lib and packages only.
- It also carries the interface fixes of `48b9865a` (another session: system
  bubbles option, controller handler restored after an RPCS3 game, latched
  playlist menu; Swift/Objective-C++ first compiled by this delivery): its 24
  files and two new tests from `48b9865a`.
- Private 576 delivered from `460c5b9b` (recipe `50d15eb1`), run
  `40596334529` (checks + cold success): IPA 0.0.8 (576), 188,095,770 bytes,
  SHA-256 `f9ee961340d8802835d41fa3505e1e687f920b667024e2ff9e216f920fed8f3b`
  (equal to SHA256SUMS), artifact `12777729764` encrypted for
  `delivery-576-recipient.pem`; MeloNX engine `301e0f86` (run 40591863306),
  RPCS3 Core 575; 20 validator receipts passed; the Swift and
  Objective-C++ of `48b9865a` compiled in the Release build. Receipt
  `docs/evidence/melonx-warm576-delivery.json`. Not tested on iPhone; no
  launch-time or FPS gain claimed. Do not reuse the number 576.

## RPCS3 Core 575: title levers for Black Ops II and Bladestorm — 27 October 2026

- Build 567 logs. Call of Duty: Black Ops II `BLES01717` (SPU and RSX bound,
  accurate reservations on): 3.5-10 M failed SPU PUTLLC per 5 s window, 9-16 ms
  texture preparation per frame at ~5,270 draws. Bladestorm `BLES00113`
  (paced at 30 fps by the game): RSX thread 0.66 core for a FIFO busy 31 %,
  7.4 ms texture preparation per frame.
- `CELL575_TITLE_LEVERS` (`ios/IOSTitleLevers.h`): no new mechanism; the
  Automatic mode of four existing levers adds them: no-op PUTLLC (565) +
  Black Ops II; texture validation per FIFO batch (559) and scoped
  revalidation (573) + Black Ops II and Bladestorm (`BLES00113`, `BLUS30070`);
  RSX idle park (565) + Bladestorm. Enabled/Disabled unchanged. Identities
  unchanged.
- BO2 PUTLLC: same signature as DBZ before 565 (DBZ 14-22 M ok / 8-14 M failed
  per window on 560-564, 2.4 M / 0.03 M with the lever on 567; BO2 567 27 M /
  5.3 M).
- Not changed: the BO2 567 freezes are the first launch of an executable
  never run before (85 PPU modules compiled at boot in 111 s, 0 SPU object
  hits for ~11,000 compiles, 389 new pipelines; the ~70 s freeze = ~26 s of
  SPU compiles, then ~55 s of back-to-back Metal pipeline compiles at
  0.35-0.48 s each). All three caches were written; identities unchanged since
  536. Removing first-launch freezes needs an excluded mode (shader
  interpreter, deferred SPU compile). BO2 4.1-4.8 GB = that compile session
  (2.5 -> 4.7 GB in 200 s, all compressed; Vulkan 392 -> 968 MB; the 559
  partly cached session peaked at 3.05 GB; >= 1.75 GB headroom). Bladestorm
  30 fps: no RPCS3 patch exists; the logs cannot tell a 30 fps design from a
  60 fps vsync target missed by an 18.8 ms main PPU thread.
- Host: policy file equal to 573 with the four 573 blocks restored; the four
  blocks compiled verbatim for 7 titles x 2 FIFO idle modes x 3 modes (42
  cases). Evidence `docs/evidence/rpcs3-cell575-host-linux.json`. No iPhone
  measurement. See `docs/rpcs3-cell575.md`.
- Core run `40589313705` (`ddf73420`, Apple Silicon): 42 policy cases pass;
  iPhone Core SHA-256 `90275c29…`, 88 exports, 137 recorded inputs, identities
  unchanged, the 575 Automatic texts in the binary. Evidence
  `docs/evidence/rpcs3-cell575-macos.json`.
- Private 575 recipe (`rpcs3-cell575-delivery.yml`, dispatch only): the
  delivered 573 tree (MeloNX engine 8cc2348, Core 573) with the Core 575 recipe
  of `ddf73420` (Core run `40589313705`); `rpcs3cell575_tree.py` /
  `rpcs3cell575_delivery.py` run the 573 recipe unchanged in `as_573()`, which
  runs the 572 recipe in `as_572()` in turn; eight validators wrap the 573
  ones. Recipient `build-utils/delivery-575-recipient.pem`. Dispatch only once
  `docs/evidence/rpcs3-cell575-macos.json` records a passed Core run.
- Private 575 delivered: run `40591563881` (workflow_dispatch) on `f9bedd76`,
  artifact `12776007264`, IPA 0.0.8 (575) 188,094,296 bytes, SHA-256
  `85b2efeb…`; signed Core = Core 575 (`90275c29…`), MeloNX engine 8cc2348.
  Decrypted and inspected: build 575, Core `ddf73420`, the 575 Automatic texts
  in the signed Core. Receipt `docs/evidence/rpcs3-cell575-delivery.json`.
  Installs over 573. Not tested on iPhone.

## RPCS3 Core 573: texture residency cap and scoped revalidation (God of War III) — 27 October 2026

- Build 567 God of War III: 4.75 GB footprint (1.25 GB compressed by iOS);
  texture pool up to 1.72 GB, purged to 366 MB by the pressure reclaim and
  back to 1.56 GB within 75 s; VMA blocks 2.76-2.83 GB with up to 1.99 GB
  unused; texture time ~10 ms per frame of which ~8 ms hashing (5.4-12.7 GB
  per 5 s window over ~9 validation epochs per frame). On iOS textures are
  confirmed by content hash, so a texture whose guest memory was reused stays
  until looked up again.
- `CELL573_TEXTURE_RESIDENCY` (`ios/IOSTextureResidency.h`, `texture_cache.h`
  `evict_idle_sections`, VK frame end): every 16 frames, while live textures
  (pool minus recyclable images) exceed 768 MiB, idle CPU textures are
  released, at most 128 MiB per pass: first those overlapped by a section used
  after them that extends past them (idle 8 frames), then least recently used
  (idle 64 frames). Bound textures excluded; shader_read/blit_engine_src
  descriptors looked up again. Lookups stamp `last_use_frame`; `trim_sections`
  does not. Setting `experimental.texture_residency`, Automatic = GoW3.
- `CELL573_SCOPED_RSX_WRITES`: `flush_set` revalidates only sections over the
  flushed sections; `committed_as_fbo` / `superseded_by_fbo` only those over
  the trampled range (covers 560 deferred write-backs). PUT, semaphores, CPU
  causes, unmaps and the frame end still advance the global epoch. Setting
  `experimental.scoped_texture_revalidation`, Automatic = GoW3. Boot log
  `texture_residency=%d scoped_revalidation=%d`. Identities unchanged.
- Host models with the Core code copied verbatim (eviction routine; sync, the
  flush_set/invalidate iOS blocks): 6,000-frame GoW3-like stream peaks at 10.3
  GB without, 828 MiB with, no re-upload of used or revisited textures; scoped
  revalidation re-hashes 2 of 5 (flush) and 3 of 5 (commit) instead of 5, every
  change detected. Evidence `docs/evidence/rpcs3-cell573-host-linux.json`. No
  iPhone measurement. See `docs/rpcs3-cell573.md`.
- Core run `40578797847` (`92074e51`, Apple Silicon): same model results; iPhone
  Core SHA-256 `2d80a2beee8e…`, 88 exports, identities unchanged. Evidence
  `docs/evidence/rpcs3-cell573-macos.json`.
- Private 573 recipe (`d1f61ee0`, `rpcs3-cell573-delivery.yml`, dispatch only):
  the delivered 572 tree (MeloNX engine 8cc2348) with the Core 573 recipe of
  `92074e51`; `rpcs3cell573_tree.py` / `rpcs3cell573_delivery.py` run the 572
  recipe unchanged in `as_572()`; eight validators wrap the 572 ones.
  Recipient `build-utils/delivery-573-recipient.pem`.
- Private 573 delivered: run `40581439146` (workflow_dispatch) on `d1f61ee0`,
  artifact `12771372912`, IPA 0.0.8 (573) 188,093,650 bytes, SHA-256
  `369d96cd…`; signed Core = Core 573 (`2d80a2be…`), MeloNX engine 8cc2348.
  Decrypted and inspected: build 573, `RPCS3-cell573-identity.json` names Core
  `92074e51`. Receipt `docs/evidence/rpcs3-cell573-delivery.json`. Installs over
  572. Not tested on iPhone.

## StikDebug fallback removed — 27 October 2026

- User report (app.log via the maintainer): four Pokken Tournament DX launches
  killed between `jitProbe begin` ("Checking executable RX/RW aliases") and
  any result, with "User-selected external JIT method." No `failed` entry, so
  the process was killed rather than refused. Source defect: with the global
  StikDebug fallback (`ios_stikdebug_fallback_v1`), MeloNX sent
  `jitBackend: external`, and `universal` required `builtin`, so iOS 26 ran
  the legacy `MeloNXJitExecutableMappingProbe()` (mmap RX + vm_remap RW +
  execution) instead of the helper's core-mapping handshake. The user's iOS
  version is not in the log; the iOS 26 kill mechanism is inferred, not
  observed.
- Maintainer request: remove the mode. Removed the preference service, its
  twelve-language locale and the Tools row (Tools: pairing, NeoSwap, then the
  BIOS checker index 2 and the storage analysis index 3 on iOS). MeloNX always
  prepares the integrated helper; the native bridge accepts only `builtin`
  and takes the handshake on every iOS 26 launch. A stale stored `true` is
  ignored. MeloNX was the only consumer. Do not reintroduce an external JIT
  path that skips the iOS 26 handshake.
- Tests: `test/jit_backend_preference_service_test.dart` (path kept for the
  workflows that list it, contract replaced), `test/melonx_launch_flow_test.py`
  (stale preference ignored; caught by restoring the old service),
  `test/storage_tools_row_test.dart`, `test/libretro_bios_checker_screen_test.dart`,
  the Tools contracts of `test/storage_contract_test.py` and
  `test/neoplay_build397_integration_test.py`. Run locally with Flutter 3.47.2:
  all pass. Three `storage_contract_test.py` failures in untouched files fail
  identically on `876a087`. Swift not compiled here; no IPA, no iPhone test.
- CI after `504f9c0` (maintainer request: fix the reported failures, all
  already red on its parent): tests updated to the shipped behavior, no
  product change. Rebrand strings (3DS language label, libretro journal
  header, simulator teardown step "returning to RewindBox"); the Import
  segment contrast measured on the Liquid Glass chrome background instead of
  `tertiaryFixed` (all 14 themes >= 3.43); the skin test `settle` also waits
  for `LiquidProgressIndicator`; `cheat_automatic_test.m` follows the reviewed
  PSX condition/repeater contract of `unified_identity_test.m` (19/19 FFVII,
  `C0` still refused; expectations from a Python port of `codesForCheat`, not
  compiled here). `liquid-glass-ui-checks.yml` host guard moved from
  `3494edc9` to `d645f05c` (private 557, the only reviewed change to those
  paths since); move it only to another reviewed host change.
- Second round (maintainer request, same day): steps the red jobs never
  reached, all failing identically on `8cc2348`. Tests only, no product
  change. `cheats_media_source_contract_test.py`: lifecycle reference
  `d3e558fa` -> `eabc057f` (MeloNX quarantine, host run 40209413009).
  `embedded_engine_route_contract_test.py`: anchors the Switch route, not
  the `7f88ee9b` dispatch check; policy call matched across `dart format`.
  `integrated_import_tab_contract_test.py` and the libretro UI contract:
  libretro delegates to `PlaylistImportButton` (`0a7975e3`); directories
  identity `29b24945` -> `598d35d5` (history still checked), NavTab gains
  `airplay`, bulk calls matched across `dart format`. `storage_contract_test.py`:
  the MeloNX imports (all inside `StorageImportActivity.run`) listed, the
  playlist's read of `StorageImportActivity.active` allowed in `_discover`
  only. `ui_refresh_rate_scope_test.py` decodes the YAML-escaped ProMotion
  assert (`48867389`). `retroarch_baseline_scope_test.py` (Build 419
  baseline, maintainer-authorized): the duplicate `restore_rewindbox_branding`
  of merge `4c71aad0` removed, NeoSwap storage fingerprints of RPCS3 Cores
  521/528/534 added as a reviewed overlay (manifest unchanged). HD textures
  harnesses stage the published `<neo_cheat_catalog/...>` headers and link
  `RBLiquidProgressView.m`. Local: 40 contract scripts and 252 build486 Dart
  tests pass, analyzer clean; macOS harnesses not run here.
## Private 572: MeloNX engine — a JIT unit ends at a jump past the other cases of a switch — 27 October 2026

- Build 566 `app.log` (18:51): Hogwarts Legacy with its update (SDK 17.5.4)
  still ended about 30 s after start with "JIT Cache exhausted" on engine
  86c2b4d; the base game (19:01, 159 s) closed normally.
- `8cc23480` (`adapt_jit_decoder.py`): after a forward B within 4 KB the A64
  decoder read on through the code the jump passes over, so a switch case
  entered through its jump table translated every case after it. A unit now
  ends at such a jump when it passes over 64 instructions or more and nothing
  in the unit enters them (no earlier branch target, no backward branch from
  the jump target's code before its next unconditional branch: rotated loops
  keep their body); shorter skips keep the upstream unit. Offline with this
  engine's compiler on the 20,543 jump-table targets of a clang ARM64 binary:
  host code 26.6 -> 19.5 MiB; following every exit, 56.6 -> 41.6 MiB, and
  408 -> 386 MiB from all 93,318 function starts, with fewer units and exits.
  Decoder test: switch case 82 -> 6 instructions, every other case unchanged;
  the simulator smoke homebrew jumps past 67 undefined words before its SVC.
  Not measured on the iPhone; not proven to be the whole cause.
- Private 572 recipe (`melonxjit572_tree.py`, `melonxjit572_delivery.py`,
  `melonx-jit572-delivery.yml`, `validate_*572_ipa.py`,
  `delivery-572-recipient.pem`): the delivered 567 product (RPCS3 Core 567,
  God of War III profile, MeloNX keyboard and L3/R3) with only the MeloNX
  engine swapped 86c2b4d -> 8cc2348; product trees equal to 567. The 567
  recipe runs unchanged in `as_567()`; inherited IPA validators check
  `derived_ipa()` (this IPA with the 566 engine entries). The RPCS3 Cores
  569 and 571 committed after 567, and the StikDebug fallback removal
  (`504f9c08`), are not part of 572. Engine run `40570622034` on `8cc23480`
  (every 566 engine step, the decoder test with the switch case, and the
  simulator smoke executing the new unit end), artifact `12766340886`
  (sha256 `612754d6…`). Maintainer: install over 567. No release.
- Private 572 delivered: run `40578083074` (workflow_dispatch) on `9ef839f4`,
  artifact `12770453569`, IPA 0.0.8 (572) 188,090,347 bytes, SHA-256
  `39e4b701…`; MeloNX engine 8cc2348 (identity `04f235fd…`), signed Core =
  Core 567 (`51273092…`); 19 IPA validators passed. The first run
  (`40572900601` on `da10d8a4`) stopped at the key import validator, which
  still named the 566 engine (fixed in `9ef839f4`). Receipt
  `docs/evidence/melonx-jit572-delivery.json`. Not tested on iPhone.

## RPCS3 Core 571: passive-lock fairness (DBZ combat stalls) — 27 October 2026

- Build 567 DBZ combat (~195 draws/frame), per 5 s window: passive-lock
  episodes 520-720, 90-200 ms, max ~10 ms (build 564: 140-230, 3-10 ms total);
  ~120,000 heavy PUTLLC acquired their writer lock in ~103 ms (564: 12.8 ms);
  frame max 130-150 ms. 565's no-op PUTLLC removed the SPU failure loop
  (PUTLLC fails 10 M -> 30 k) and SPUs now take writer locks in bursts; a
  `vm::passive_lock` waiter needs the whole exclusive word clear and is only
  notified when it clears, so it starves.
- `CELL571_PASSIVE_LOCK_FAIRNESS` (`ios/IOSPassiveLockGate.h`, `vm.cpp`): a
  waiter past two 50 us timed waits marks itself starving; range-lock writers
  (`vm::writer_lock` with a range lock) defer while one is, at most ~0.5 ms,
  before publishing their bit, spinning with the CPU `yield` hint (Darwin's
  `sched_yield()` depresses a thread for ~10 ms: Core run `40569244176` failed
  with a 127 ms re-entry and an 11 ms writer deferral with the first version).
  No lock skipped. Setting
  `experimental.passive_lock_fairness`, Automatic = every title; Disabled = 569.
  Boot log `passive_fairness=%d`. Identities unchanged (no cold compile).
- Host model with the production header (3 bursty writers, or 2 below 4 cores
  so the waiter keeps a core; 1 passive waiter; 2,000 re-entries; optimized,
  4-core Linux): max wait 13.1 -> 3.9 ms, total 2,545 -> 252 ms, writer
  throughput -6 % (-20..+8 % across runs, continuous writers being the worst
  case). Every build asserts no re-entry reaches 20 ms; latencies are reported,
  not bounded (run `40568663915` failed on a 10 ms TSan bound). Evidence
  `docs/evidence/rpcs3-cell571-host-linux.json`. No iPhone measurement. See
  `docs/rpcs3-cell571.md`.
- Core run `40570081835` (`0522f593`, Apple Silicon, 3 cores, 2 writers,
  optimized): capped re-entries 2 -> 0, max wait 26.4 -> 12.1 ms, total 786 ->
  211 ms, writer throughput -18 %; sanitizer builds without a capped re-entry.
  iPhone Core SHA-256 `4f13dda2893c…`, 88 exports, identities unchanged.
  Evidence `docs/evidence/rpcs3-cell571-macos.json`.

## RPCS3 Core 569: iOS threads keep their QoS (567 fix) — 27 October 2026

- Build 567 `RPCS3-diagnostic.log`: `pthread_set_qos_class_self_np() failed: 1`
  (EPERM) 1,486 times (none in any earlier build): worker job starts, RSX,
  cellAudio, RsxAudioData, SPU workers. The 567 priorities were never applied.
- Cause: `thread_ctrl::set_thread_affinity_mask` calls
  `thread_policy_set(THREAD_AFFINITY_POLICY)` (every pooled job end; CPU/RSX
  threads when the thread scheduler is not the OS one). iOS has no affinity
  sets, so it fails; XNU's `thread_policy_set()` removed the QoS first and
  restores it with the stored relative priority unnegated: 0 survives, -2
  (567) is rejected and the thread stays opted out of QoS (EPERM afterwards).
- `CELL569_QOS_KEEP`: the iOS branch of `set_thread_affinity_mask` applies
  nothing. Callers unchanged; identities unchanged (no cold compile).
  Host evidence `docs/evidence/rpcs3-cell569-host-linux.json`; the Mac CI runs
  the real QoS/affinity calls. No iPhone measurement. See `docs/rpcs3-cell569.md`.
- Core run `40566094740` on `e70fa381`: Core `7fd47394…`, 88 exports, identities
  unchanged. On the Apple Silicon runner: relpri -2 + THREAD_AFFINITY_POLICY +
  raise = EPERM; relpri 0 = success; the 569 sequence keeps QoS. Receipt
  `docs/evidence/rpcs3-cell569-macos.json`.

## RPCS3 Core 567: RSX thread priority, pooled-worker QoS reset — 27 October 2026

- From 565 logs: God of War III without the 30 cap runs 13-17 FPS with the RSX
  FIFO 85-90 % busy while the RSX thread gets 0.57 core (SPU ~3.4 cores).
  On iOS `set_native_priority` gave every thread that asks nothing the same
  user-interactive QoS as RSX, so upstream's `scoped_priority(+1)` (RSX,
  cellAudio, rsxaudio) did nothing; and a pooled `ios_thread_worker` kept the
  utility class the shader-cache writer sets (`rsx_cache.h`, never restored)
  for its next job, PPU or SPU included.
- `CELL567_THREAD_QOS` (`ios/IOSThreadQoS.h`, `Utilities/Thread.cpp`): one
  mapping; +1 user-interactive relpri 0, 0 user-interactive relpri -2, -1
  utility (unchanged); `ios_thread_worker::run` calls `set_native_priority(0)`
  before each job. Setting `experimental.rsx_thread_priority`, Automatic = every
  title; Disabled = relpri 0 for all (565 order), the worker reset stays.
  `Thread.cpp` is not a codegen identity input: identities unchanged (no cold
  compile). Non-iOS view of every touched file unchanged.
- Host evidence `docs/evidence/rpcs3-cell567-host-linux.json` (three modes under
  ASan/UBSan and TSan, worker reset, placement contract; the real Darwin QoS
  calls run on the Mac CI runner); materialized from upstream; `Thread.cpp`
  ARM64 iOS syntax with Apple QoS declarations, no new warning. No iPhone
  measurement. See `docs/rpcs3-cell567.md`.
- Core run `40547296252` on `67dd222`: Core `51273092…`, 88 exports, identities
  unchanged; on the Apple Silicon runner the real Darwin QoS calls give the
  three modes under ASan/UBSan and TSan (lowered = utility, reset =
  user-interactive at the mode's relpri, raised = relpri 0). Receipt
  `docs/evidence/rpcs3-cell567-macos.json`.
- Private 567 recipe (`rpcs3cell567_tree.py`, `rpcs3cell567_delivery.py`,
  `rpcs3-cell567-delivery.yml`, `validate_*567_ipa.py`,
  `delivery-567-recipient.pem`): the delivered 566 product (MeloNX engine
  86c2b4d, keyboard, L3/R3, GoW3 frame limit Auto) with only the Core swapped
  565 -> 567; product trees equal to 566. The 566 recipe runs unchanged in
  `as_566()`; the 566 validators run under it and their receipts are carried
  under build 567. Maintainer: install over 566. No release.
- Private 567 delivered: run `40552860886` (workflow_dispatch) on `30022a46`,
  artifact `12757313916`, IPA 0.0.8 (567) 188,087,640 bytes, SHA-256
  `2d0f343b…`; signed Core = Core 567 (`51273092…`), MeloNX engine 86c2b4d.
  An earlier run (`40549806812` on `ea559dfe`) started because the draft's
  message quoted the delivery tag; it stopped in checks before any IPA. Receipt
  `docs/evidence/rpcs3-cell567-delivery.json`. Not tested on iPhone.

## Private 566: MeloNX engine — JIT translation units, GC gen2 budget — 27 October 2026

- Build 564 `app.log`, Hogwarts Legacy with its update (SDK 17.5.4): two
  sessions (one in a fresh process) ended about 32 s after start with
  `JIT Cache exhausted` (512 MB TXM arena, never freed); the base game ran
  727 s but from 50 s on `.NET_BGC` used 46-72 % of a core and FPS fell from
  30 to 6-13. Analysis: `docs/melonx-jit-gc-566.md`. Engine commits
  `b4e81d5f` + `86c2b4dc` (test comparison only): `adapt_jit_decoder.py` (end
  a LightningJit unit after BRK/UDF and after a call or jump followed by a
  stack-frame opening; offline on 93,318 functions of a clang ARM64 binary:
  host code 293 -> 123 MiB, compile time -43 %) and `adapt_gc.py`
  (`System.GC.ConserveMemory` 9 -> 5). Tests: `test/melonx_jit_decoder_test.py`;
  the simulator smoke homebrew executes both new unit ends.
- Private 566 recipe (`melonxjit566_tree.py`, `melonxjit566_delivery.py`,
  `melonx-jit566-delivery.yml`, `validate_*566_ipa.py`,
  `delivery-566-recipient.pem`): the delivered 565 product (RPCS3 Core 565,
  God of War III frame limit Auto) with only the MeloNX engine swapped 564
  (`876a087b`) -> 566, on the 564 pattern: `as_565()`, `old_engine()` (564
  engine in `dist/melonx564engine`), `derived_ipa()` (564 engine entries; the
  565/564 validators derive their 563-equivalent from it); source contract
  memoized per job (`delivery_contract_memo.py`). A first 566 run on the 564
  tree (`40539638348`) was cancelled at the maintainer's request so that 566
  keeps the RPCS3 565 fixes. Claimed by session `session_01K9YJtz…`. Do not
  reuse 566.
- Delivered private 566: run `40547475049` on `45a7a3cc` (run `40542079433`
  on `e7e96afb` stopped at the key import validator, which the workflow still
  pointed at the 564 engine; fixed), artifact `12756265837`, IPA 0.0.8 (566)
  188,084,692 bytes, SHA-256
  `fba32a90a32dac22deb381ea58864e39c902dd77439d36f409d1591bc5e5aa70`; every
  validator passed; decrypted and inspected independently (MeloNX engine
  `86c2b4dc`, RPCS3 Core `07e416c4`). Receipt
  `docs/evidence/melonx-jit566-delivery.json`. Not tested on iPhone; no FPS
  gain measured. A workflow stacked on 566 must pass the 566 engine
  (`86c2b4dc…`, run `40535449055`) to `validate_melonx_keys_ipa.py`.

## Private 564: MeloNX engine — garbage texture descriptors, bounded engine journal, crash record — 27 October 2026

- Hogwarts Legacy `app.log` (Build 562): 15 s at 0 FPS (GPU thread 99 %,
  `Logger.MessageThread` 80 %) and later 1-9 FPS with the .NET GC busy, while
  pool entries filled with 0x5A5A5A5A (format `0x25A5A`, GPU VA beyond 40 bits)
  logged "Invalid texture format" more than 13,000 times a second, each
  written synchronously to app.log on the GPU thread. Analysis:
  `docs/melonx-texture-journal.md`. Engine commit `876a087b`:
  `adapt_texture_pool.py` (reject an address that fails `ValidateAddress`
  before sizing or logging; same null result), `RecordEngine` (8 occurrences
  per text, then powers of two; reset per game), `RecordCrash` (unhandled
  managed exception written past the 5 MiB ceiling). Engine run `40502672385`
  green with `test/melonx_texture_pool_test.py` and
  `test/melonx_engine_journal_test.py` (NativeAOT crash record included).
- Private 564 recipe (`melonxtexture564_tree.py`, `melonxtexture564_delivery.py`,
  `melonx-texture564-delivery.yml`, `validate_*564_ipa.py`,
  `delivery-564-recipient.pem`): the delivered 563 product with only the MeloNX
  engine swapped 558 (`8f83748b`) -> 564. The 563 recipe runs unchanged in
  `as_563()`; `old_engine()` puts the 558 engine evidence back in
  `dist/melonx` for inherited checks, and the inherited MeloNX IPA validators
  check `derived_ipa()` (the IPA with the 558 engine entries packaged by
  `package_runtime` on the 563 tree, every other entry byte for byte).
  `validate_melonx_texture564_ipa.py` checks the real engine and that only the
  engine entries differ. Claimed by session `session_01K9YJtz…`. Do not reuse 564.
- Delivered private 564: run `40516675743` on `19914ca9` (the first attempt,
  run `40509468373`, stopped at an embed step: `old_engine()` had moved the
  standalone MoltenVK receipt aside; fixed), artifact `12742845669`, IPA 0.0.8
  (564) 188,082,264 bytes, SHA-256
  `a5703d7fd8e82d492b781e2a7ad6b9e7175e78d2fa0c59b2689970cf8fb5c4c7`; every
  validator passed; decrypted and inspected independently (engine identity
  `876a087b`). Receipt `docs/evidence/melonx-texture564-delivery.json`. Not
  tested on iPhone.

## Private 562: MeloNX Switch keyboard and L3/R3 touch buttons — 27 October 2026

- User requests (Discord, via the maintainer): a game asking for text crashed
  or hung (Hogwarts Legacy, character name), and an L3/R3 option for the
  virtual gamepad. Analysis and iPhone protocol: `docs/melonx-keyboard562.md`.
- Cause: MeloNX's `AlertHelper` sends `show_text_input` through the engine's
  callback registry and blocks the HLE thread until
  `show_text_input_result_<id>` is invoked; the standalone app registers it,
  RewindBox never did. Host-only fix in `9b40129f` (no engine rebuild; the
  engine already exports `RegisterCallback`/`InvokeCallback`):
  `MeloNXTextInput.swift` (UIKit text field, answers queued and every request
  answered before each session stop, entered text never journaled),
  optional binding in `MeloNXRuntimeAPI.swift`, wiring and the in-game
  "Stick buttons (L3/R3)" entry (Melo-Controller's own
  `rewindbox.melonx.stickButton`) in `MeloNXMetalSessionViewController.swift`,
  two strings in twelve languages. Host run `40484359276` green, including
  the UIKit keyboard probe (`test/melonx_text_input_test.py`, 45 + 19 checks).
- `melonx-display` fails on `melonx_presentation_widgets_test.dart` at
  `9b40129f` and already at its parent when run after
  `melonx_display_test.dart` (timing-dependent, not this change).
- 561 is the RPCS3 Core 561 delivery of another session (`5dd6a5ae`), so this
  build is 562, stacked on it. Private 562 recipe (`melonxinput562_tree.py`,
  `melonxinput562_delivery.py`, `melonx-input562-delivery.yml`,
  `validate_*562_ipa.py`, `delivery-562-recipient.pem`): the delivered 561
  product with only the 562 MeloNX host files; the 561 recipe runs unchanged
  in `as_561()` (which also regenerates the 561 controller strings), the 562
  host run is bound to the pinned tree. RPCS3 Core 561 and the 558 MeloNX
  engine unchanged. Claimed by session `session_01K9YJtz…`. Do not reuse 562.
- Delivered private 562: run `40490382532` on `e33cee36` (full Xcode build),
  artifact `12730156567`, IPA 0.0.8 (562) 188,076,362 bytes, SHA-256
  `b5ec68d58c031356df27da779e84f2f40b8d2e2bd5671cde08f9af99290b395e`; all five
  562 validators passed; decrypted and inspected independently. Receipt
  `docs/evidence/melonx-input562-delivery.json`. Not tested on iPhone.

## Core-only deliveries from the published application (core swap) — 27 October 2026

- Release `0.0.10` was published by the maintainer on 26 October 2026 (tag at
  `9e7bed79`, normal release). Its IPA asset `RewindBox-.0.0.10.ipa` is build
  559, SHA-256 `f16c2a35…7896480d`, identical to the delivered private 559
  (`docs/evidence/rpcs3-cell559-delivery.json`). The release also carries a
  `body.md` asset.
- A delivery that changes only the RPCS3 Core may be derived with
  `build-utils/make_core_swap_workflow.py` from its full workflow. The macOS
  job runs `build-utils/core_swap_base.py` in place of the Xcode compile; it
  verifies the published asset (pinned SHA-256, GitHub digest, base delivery
  receipt) and that the pinned product trees equal the base receipt's, then
  extracts the app to the Xcode products path, stamps the build number into
  the bundles of the base build and removes the base's build-numbered identity
  receipts. The four RPCS3 Core steps move just before the Core is embedded;
  every other step and validator is unchanged, and the checks job runs
  `core_swap_base.py --check` first. The build's tree module must list
  `build-utils/core_swap_base.py` in its recipe.
- First CI run (delivery 561, run `40486995044`): `checks` passed; the macOS
  job failed at packaging, `validate_stikjit_ipa.py` (before the seal) compares
  StikJIT byte for byte with the tested artifact `224325cc`, and the published
  app carries it signed (`5e37408c`). `core_swap_base.py` now puts the tested
  binary back after requiring the seal step's `payload_fingerprint` (code and
  data sections, ABI metadata) to equal the published one's; the 559 seal
  receipt records that fingerprint (`57e75fbd`) for the unsigned binary.
  `make_core_swap_workflow.py` adds `core_swap_base.py` to the variant's push
  paths. Tests: `test/core_swap_base_test.py`. Any shipped-source change
  requires the full build. Push the Core commit and the
  delivery recipe together; the delivery waits for the exact Core run. See
  `docs/core-swap-delivery.md`.

## Delivery speed: the source contract computed once per job — 27 October 2026

- Measured (563, run `40501404250`): 40 min end to end; the macOS job (32.6 min)
  waits for `checks` (7.6 min). Every delivery-module call starts with the full
  source contract (pin, parent, the whole chain of earlier recipes in nested
  views): ~2 min on macOS, six calls per job, ~12 min of identical work.
- `build-utils/delivery_contract_memo.py`: `reuse(BUILD, source_contract,
  declared=[INSTALLED])` records the first report of a job and reuses it only
  when the commit, the index tree, every tracked file in the working tree,
  every untracked file the contract opened, every listed or globbed directory,
  the declared existence-tested paths and the asserted environment are
  unchanged; otherwise it recomputes and prints why. Failing or
  checkout-changing contracts are never recorded; the record
  (`build/source-contract-memo/`) is never uploaded. Use it in each new
  delivery module's `main()` and list the file in the tree module's recipe.
  Expected 6-10 min less on the macOS job (build steps that patch tracked files
  force one recomputation); not yet measured on CI. Tests:
  `test/delivery_contract_memo_test.py`. See `docs/delivery-speed.md`.

## God of War III: no 30 fps limiter (maintainer request, 27 October 2026)

- The only 30 fps cap was the RewindBox God of War III profile
  (`gpu.frame_limit: '30'`, build 412). The Core has no title-specific frame
  limit; the shipped GoW3 patches are cheats only; on PS3 the game is not
  locked to 30 (variable, 60 Hz vblank, own timing). `c5ba917` sets
  `'gpu.frame_limit': 'Auto'` (Core default, 60 Hz vblank), explicit so a
  GameDB entry cannot lower it; per-game user choices still apply last; the
  legacy-config inheritance applies it where the old file left the global
  value. Above 60 would need a higher VBlank Frequency (may change game speed):
  not enabled, not tested. Do not bring the 30 cap back without a maintainer
  decision. Shipped by private 565. No GoW3 measurement since 551.

## RPCS3 Core 565: early submission kept on, no-op PUTLLC keeps reservations, RSX idle park — 27 October 2026

- Maintainer direction (27 October): engine optimizations over diagnostics and
  A/B cycles; keep the 561 lever on. From 564 logs of DBZ `BLES01658` (combat):
  ~120,000 successful and ~75,000 failed SPU PUTLLC per frame for ~500 that
  change data (Accurate SPU Reservations on: a no-op write-back advances the
  reservation time and kills the other SPUs' reservations on the line); RSX
  thread 0.90 core for a FIFO busy 33-43 % (one ~12 ms idle period per frame in
  `yield`); the iPhone (A18 Pro) has two performance cores.
- A: the 563 alternation is removed; `IOSEarlySubmit.h` and
  `RPCS3IOSPerformance.cpp` are the 561 files again; Automatic keeps early
  submission on for `BLES01658` all session.
- B `CELL565_NOOP_PUTLLC` (`do_putllc`, accurate mode, data equal to the
  snapshot): succeeds when the line and the time are unchanged on both sides of
  the comparison, without advancing the time; waiters are not notified (as
  before). Setting `experimental.noop_putllc_keeps_reservations`, Automatic =
  DBZ only. Host code SPU objects call: the `SPUThread.cpp` alias in
  `JITCacheCompatibility.cmake` moves to the new snapshot; codegen identities
  unchanged (no cold compile).
- C `CELL565_RSX_IDLE_PARK` (`ios/IOSRsxIdlePark.h`): after 1 ms of empty FIFO,
  `FIFO_control::idle_wait` sleeps in 50 us slices instead of yielding; FIFO
  resume ends the idle period; the fault flush request, offloader request, PPU
  flip request and ZCULL pipe flush call `wake()`. Setting
  `experimental.rsx_idle_park`, Automatic = DBZ and God of War III, only with
  "RSX FIFO Idle Wait" = Yield. Non-iOS view of every touched file unchanged.
- Host evidence `docs/evidence/rpcs3-cell565-host-linux.json`: 162 policy cases,
  10 PUTLLC protocol cases, three-poller model (0 failed data-changing PUTLLC
  with 565; with the old path 0 to 37,392 depending on build and run), park
  (200/200 wakes, 14 ms CPU per 60 ms idle on the Linux host vs 60 ms), six
  mutations detected;
  ASan/UBSan, TSan, ARM64 qemu, materialized from upstream, ARM64 iOS syntax
  with the 563 warning set. No iPhone measurement. See `docs/rpcs3-cell565.md`.
- Core run `40533429692` on `07e416c` (the first, `40532040733` on `36ff40f`,
  stopped on a harness timing check, fixed without production change): Core
  `428b11e6…`, identities unchanged; on the Apple Silicon runner the
  three-poller model gives 0 vs 637,736 failed data-changing PUTLLC (200,000
  increments) and the parked idle thread 1.7 ms CPU per 60 ms vs 56.4 ms.
  Receipt `docs/evidence/rpcs3-cell565-macos.json`.
- Private 565 recipe (`rpcs3cell565_tree.py`, `rpcs3cell565_delivery.py`,
  `rpcs3-cell565-delivery.yml`, `validate_*565_ipa.py`,
  `delivery-565-recipient.pem`): the delivered 564 product (other session's
  MeloNX engine 876a087, keyboard, L3/R3) with the Core swapped 563 -> 565
  (`07e416c`) and the God of War III profile of `c5ba917` (frame limit Auto);
  only the `lib` tree differs from 564. The 564 recipe runs unchanged in
  `as_564()`. First delivery to compute its source contract once per job
  (`delivery_contract_memo.reuse`). Full Xcode build. No release.
- Private 565 delivered: run `40536444985` on `5869c89e`, artifact
  `12750059637`, IPA 0.0.8 (565) 188,083,286 bytes, SHA-256 `970a48ac…`;
  signed Core = Core 565 (`428b11e6…`), MeloNX engine 876a087. Delivery time
  33.4 min end to end (macOS job 26.6 min) vs 40 / 32.6 min for 563: the
  contract memo saved ~6 min. Receipt `docs/evidence/rpcs3-cell565-delivery.json`.
  Not tested on iPhone. The other session's private 566 (`e7e96afb`) stacks
  MeloNX engine 86c2b4d on this delivered 565 tree (Core 565 and the GoW3
  profile kept); the next RPCS3 build stacks on 566.

## RPCS3 Core 563: in-session A/B of the 561 early submission (DBZ HD) — 27 October 2026

- Reason: the 562 measurement could not isolate 561 (the 562 session was also
  slower where 561 never acted). Core 563 (`CELL563_EARLY_AB`) makes Automatic on
  `BLES01658` alternate the 561 lever per profiling window (~5 s, on first):
  `early_submit::window_boundary()` runs under `m_profile_mutex` with the window
  snapshot, returns the ending window's state and switches the next one.
  `COREPROF OPT561` prints that state plus `ab=1`; the boot log adds
  `early_submit_ab=`. Explicit Enabled/Disabled keep one state; other titles and
  the 561 decision, limits, guards and renderer hook are unchanged (renderer
  sources byte-identical to 561). Codegen identities unchanged.
- Host evidence `docs/evidence/rpcs3-cell563-host-linux.json`: production
  header and verbatim policy/boundary/export bodies under ASan/UBSan, TSan and
  ARM64 qemu (identical); 7 policy cases, alternation 101010101010, explicit
  modes stable, 400 concurrent windows with every early submission reported
  once; seven behavioral mutations detected; driver preflight authenticated
  the 561 diagnostics artifact. A measurement build, not an optimization. See
  `docs/rpcs3-cell563.md`.
- Private 563 recipe (`rpcs3cell563_tree.py`, `rpcs3cell563_delivery.py`,
  `rpcs3-cell563-delivery.yml`, `validate_*563_ipa.py`,
  `delivery-563-recipient.pem`): the delivered 562 product (the other session's
  MeloNX keyboard and L3/R3 on the 561 product) with only the RPCS3 Core swapped
  561 -> 563 (`dd65e867`, Core run `40500425037`). Full Xcode build (562 is not
  a published release). The 562 recipe runs unchanged in `as_562()`. No
  release. Do not reuse 563.
- Private 563 delivered: run `40501404250` on `0bf5854a` (checks + cold),
  artifact `12735616104`, IPA 0.0.8 (563) 188,074,851 bytes, SHA-256
  `d23c6b78…34119319`. Core = CI Core 563 (fingerprint), 562 MeloNX keyboard
  present; against 561 only `libRPCS3Core.dylib`, `melonx_internal_bridge` and
  `Runner` change code. Local revalidation identical to CI. Receipt
  `docs/evidence/rpcs3-cell563-delivery.json`. Not tested on iPhone.
- A/B measured on DBZ with the other session's 564 (Core 563): in combat,
  lever-on windows are faster than their two lever-off neighbours in 12 of 12
  pairs: +1.8 FPS median (+1.1 to +2.3), frame -0.9 ms (-4%), p95 -0.7 ms,
  readback wait -1.7 ms/frame; p99 and 1% low unchanged within noise. The 562
  slowdown was session conditions (lever-off combat 43.7 FPS here). Receipt
  `docs/evidence/rpcs3-cell563-dbz-ab-measured.json`, `docs/rpcs3-cell563.md` §8.

## RPCS3 Core 561: early command buffer submission (DBZ HD) — 27 October 2026

- Build 560 measured on DBZ `BLES01658` (`docs/rpcs3-cell560.md` §9): neutral,
  ~42 FPS in combat; the guest reads one 1280x720x4 surface back per frame
  (`fault_read` ~7.9 ms/frame, `dropped` 0) and waits for the GPU to execute
  the frame, which the RSX thread submits only at the flip or at a flush.
- Core 561 (`CELL561_EARLY_SUBMIT`, `ios/IOSEarlySubmit.h`): at the end of a
  draw, when at least 32 draws were recorded since the last primary submission,
  that submission's fence has completed (non-blocking `poke()`), the frame has
  used fewer than 6 early submissions and no flush, offloader deadlock or
  uninterruptible recording is active, call `flush_command_queue()`. Commands
  and their order are unchanged; only command buffer boundaries move. The flip
  resets the budget. Setting "Early Command Buffer Submission"
  (`experimental.early_submit`, Automatic = `BLES01658` only). New
  `COREPROF OPT561`; boot log `early_submit=`. Codegen identities unchanged.
- Host evidence `docs/evidence/rpcs3-cell561-host-linux.json`: production
  bodies against the 560 preimages under ASan/UBSan, TSan and ARM64 qemu;
  simulated-time model (not a measurement): combat frame 24.0 -> 18.2 ms,
  light scenes and disabled identical to 560, GPU-bound not worse; seven
  behavioral mutations detected; driver preflight authenticated the 560
  diagnostics artifact. No iPhone measurement. See `docs/rpcs3-cell561.md`.
- Core 561 pushed as `5b033881` (rebased over the MeloNX commit `9b40129f`;
  Core run `40486026315`). Private 561 recipe (`rpcs3cell561_tree.py`,
  `rpcs3cell561_delivery.py`, `validate_*561_ipa.py`,
  `delivery-561-recipient.pem`): the delivered 560 product (the 559/558 one)
  with only the RPCS3 Core swapped 560 -> 561; the 560 recipe runs unchanged in
  `as_560()`. First Core-swap delivery: `rpcs3-cell561-delivery.yml` is the
  `make_core_swap_workflow.py` variant (base release 0.0.10, build 559). The
  `9b40129f` MeloNX change is not in 561 (product files stay pinned to their
  delivered versions; it needs a full build). No release. Do not reuse 561.
- Private 561 delivered: first attempt run `40486995044` failed at the StikJIT
  pre-seal check (fixed in `9a805c6c`, see the core-swap section); run
  `40491394767` on `9a805c6c` passed (macOS job 21.0 min vs 24.9 for the full
  560). Artifact `12730102171`, IPA 0.0.8 (561) 188,062,278 bytes, SHA-256
  `d92f314b…f5a18d`. Against the published 0.0.10 IPA, only
  `libRPCS3Core.dylib` changes code: 73 of 85 Mach-O images are byte-identical,
  11 differ only in signature. Local revalidation identical to CI. Receipt
  `docs/evidence/rpcs3-cell561-delivery.json`. Not tested on iPhone.
- Measured on DBZ with the other session's 562 (Core 561): combat 35.4 FPS vs
  41.7 in 560, but menus where 561 never submitted early (the 560 code path) are
  also 17% slower (43.0 vs 51.9 FPS; new app container, RSX CPU costs equal):
  the drop is not attributable to 561. Where 561 acts, the readback wait falls
  8.0 -> 6.2 ms/frame with no FPS gain; the GPU is busy at ~118 of ~208 draw
  ends. No gain from 561. Isolating it needs an in-session A/B. Receipt
  `docs/evidence/rpcs3-cell561-dbz-measured.json`, `docs/rpcs3-cell561.md` §9.

## RPCS3 Core 560: deferred framebuffer-commit write-back (DBZ HD) — 26 October 2026

- Maintainer logs of build 559, Dragon Ball Z Budokai HD Collection `BLES01658`
  (PID 36124). Each frame reads back two (light scenes) or three (battles)
  1280x720x4 sections (3,686,400 bytes, origin `unknown`), 8.8 / 14.2 ms per
  frame; RSX texture-site GPU waits are exactly one fewer per frame (4.0 / 8.7
  ms). `OPT559` is zero. Analysis: `docs/rpcs3-cell560.md`; receipt
  `docs/evidence/rpcs3-cell560-dbz-observed.json`.
- Code path (deduced, not attributed by 559 logs): with Write Color Buffers
  off, `prepare_rtts` commits each framebuffer (`committed_as_fbo`, which does
  not skip flushes), so a blit-protected `framebuffer_storage` section at the
  framebuffer base is read back synchronously on the RSX thread.
- Core 560 (`CELL560_DEFERRED_COMMIT`, `ios/IOSDeferredCommit.h`): for a single
  flushable framebuffer section, record the same GPU copy, keep the pages
  locked, no wait; write the bytes at the first access that needs them (fault,
  savestate commit, any flush) or before any release (unprotect, discard, dirty
  release, readable reprotect); drop them if the GPU recreates the section
  first. Guest-visible bytes are the 559 ones. `prepare_rtts` submits after
  each commit that recorded a copy. Setting "Deferred Framebuffer Write-back"
  (Automatic = `BLES01658` only). New `COREPROF OPT560`; `READBACK555` appends
  `fbo_commit`, `fault_read`, `fault_write`. Codegen identities unchanged.
- Host evidence `docs/evidence/rpcs3-cell560-host-linux.json`: 12 scenarios
  identical to 559 for guest reads, GPU waits 17 -> 3, no wait on an
  unsubmitted buffer, six mutations detected; ASan/UBSan, TSan, ARM64 qemu;
  driver preflight authenticated the 559 diagnostics artifact. No iPhone
  measurement.
- Core 560 built: run `40420391683` on `cba3fa9f`, artifact `12698001069`,
  dylib SHA-256 `84e4e21c…2678cf`, ABI 30, 88 exports, codegen identities
  unchanged. macOS ARM64 evidence `docs/evidence/rpcs3-cell560-macos.json`
  (same 12 scenarios and figures as Linux, harness hash identical).
- Private 560 recipe (`rpcs3cell560_tree.py`, `rpcs3cell560_delivery.py`,
  `rpcs3-cell560-delivery.yml`, `validate_*560_ipa.py`,
  `delivery-560-recipient.pem`): the delivered 559 product byte for byte (the
  558 product) with only the RPCS3 Core swapped 559 → 560. The 559 recipe runs
  unchanged in `as_559()` (scratch index, the 560 Core recipe files at their
  559 versions, the pin test and Core driver modules of that tree,
  BUILD_NUMBER 559, installed 560 identity set aside); 558 receipts go through
  `as_559()` then the 559 recipe's `as_558()`. No release. Do not reuse 560.
- Private 560 delivered: run `40422457325` on `b5f1a3a4`, artifact
  `12699494190`, IPA 0.0.8 (560) 188,062,719 bytes, SHA-256
  `98483d55…2c3ecd9`. Dart image identical to 559; only the RPCS3 Core,
  versions, signatures and receipts change (`Runner` rebuilt: UUID and project
  version). Local revalidation identical to CI. Receipt
  `docs/evidence/rpcs3-cell560-delivery.json`. Installs over 559 after
  SideStore re-signing; not tested on iPhone.

## RPCS3 Core 559: SPU cache-hit, texture, shader and GPU copy costs — 26 October 2026

- Resumed on `Claude` at `9d0ca40` (the session checkout was 83 commits behind;
  fast-forwarded, nothing lost). The five optimizations reported as "engaged"
  (SPU LLVM bypass on object-cache hit, no hash of invalid textures, fast
  identical vertex-program compare, sync-compile copies, full-overwrite GPU
  copies) existed in no commit, branch or PR: implemented on the 555 canonical
  source as Core **559** (`CELL559_*`, analysis `docs/rpcs3-cell559.md`).
- SPU `compile()` builds analysis managers/PassBuilder/pass pipeline only on a
  cache miss. `JITCacheCompatibility.cmake` aliases the exact new
  `SPULLVMRecompiler.cpp` hash to 555: identities stay PPU `a987639e9f838d1c` /
  SPU `d070cb361bdef607` (without the alias SPU would become `7330ce26…`, a
  cold recompile). Any later edit of that file must keep or drop the alias
  deliberately.
- Dirty hash-validated texture sections are released without hashing; clean
  sections are always hashed. Exact vertex-program repeats are confirmed by one
  `memcmp`. Inline pipeline builds reference the RSX-owned vertex program and
  move the callback; the fragment snapshot is kept (guest memory). A strict
  DMA blit destination skips the read-back of sections it overwrites entirely;
  an existing single-sampled color target fully replaced by a blit skips its
  memory reload. New bounded line `COREPROF OPT559`.
- "Texture Validation Per FIFO Batch" (`experimental.texture_validation_epoch`,
  `CELL559_TEXTURE_EPOCH`): a confirmed texture hash lasts until the next
  synchronization point (new FIFO PUT, NV406E semaphore acquire, texture-cache
  write/unmap/surface commit or flush, frame end). Automatic = the six God of
  War III title IDs only; Disabled restores per-draw hashing exactly. Aimed at
  the ~270 MiB/interval GoW3 hashing of 553; unverified on iPhone.
- Not changed, by decision: Metal pipeline compile time (driver-bound; Async
  shader mode excluded by the maintainer), the minimal-object SPU linker
  (prototype pending real-title proof), and the public `neoswap-ipa.yml` Core
  pin that `neo_swap_core_pin_test.py` checks.
- Host evidence `docs/evidence/rpcs3-cell559-host-linux.json` (LLVM 22.1.8,
  ASan/UBSan, TSan, ARM64 under qemu; CI preflight run locally, 555 Core
  authenticated). No iPhone measurement: FPS, frame time and stalls remain
  unconfirmed. The Core is built by `rpcs3-cell559-core.yml`
  (`[rpcs3-cell559-core]`) on top of the delivered 558; no release.
- Core 559 built: run `40403710130` on `07c76ec1`, artifact `12690812338`,
  dylib SHA-256 `1b490126…55a25d0`, ABI 30, 88 exports, codegen identities
  unchanged since 551. macOS ARM64 evidence
  `docs/evidence/rpcs3-cell559-macos.json` (VP compare 512 instr. 707 → 283 ns,
  SPU pass setup 3.29 µs per cache hit avoided; not iPhone measurements).
- Private 559 recipe (`rpcs3cell559_tree.py`, `rpcs3cell559_delivery.py`,
  `rpcs3-cell559-delivery.yml`, `validate_*559_ipa.py`,
  `delivery-559-recipient.pem`): the delivered 558 product byte for byte with
  only the RPCS3 Core swapped 551 → 559. The 558 recipe runs unchanged in
  `as_558()`, which also swaps the Core pin test module and sets aside the
  installed 559 Core identity, which only the 559 recipe checks. Do not reuse 559.
- Private 559 delivered: source `fb0a80e7`, run `40407883637` (checks and cold
  passed), encrypted artifact `12693906038`. IPA 0.0.8 (559), 188,063,063
  bytes, SHA-256 `f16c2a3529537bfbaa933972ed63f6ce96bb2a9ca176f1e2d1726dcd7896480d`;
  SideStore re-signing required. Receipt `docs/evidence/rpcs3-cell559-delivery.json`.
  No iPhone validation; no release.

## Private 558: MeloNX measurement and log fixes on 557 — 26 October 2026

- Measurement build for the Persona 4 Golden / Persona 5 Royal stutter
  reported on 553 (flicker gone). Nothing changes emulation by default.
  Analysis and how to read the logs: `docs/melonx-persona-performance-2026-10-25.md`
  ("MeloNX measurement build 558").
- Contents (`4464ed6..cfce9f6`, Claude MeloNX session only):
  - one `[MeloNX:perf]` app.log line per second during a game: game FPS,
    presented frames and gaps, audio DSP late episodes and output
    starvations (engine export `neostation_melonx_audio_pacing`; a host pause
    is not counted), per-thread CPU and priority, thermal state;
  - "Emulation priority" in the in-game menu (default unchanged);
  - repeated NSLog stubs copied once in the stderr capture;
  - Dart log lines written with O_APPEND (`fopen(path, "a")` through
    `dart:ffi`), so native app.log lines are no longer overwritten;
  - the live log follows a user-data migration (`LoggerService.moveLogFile`).
- CI on push: engine 40376664278 (`8f83748`) and host 40385961915 (`e2c9437`),
  which now runs the performance journal and parity Swift tests on macOS
  (`melonx-host.yml`, maintainer-approved).
- Built on the delivered 557 tree at the maintainer's request (557 keeps its
  library-file fix and the 554 import). The same change was first prepared as
  556 on the 554 tree (`640ff06`); 556 was never armed nor delivered and its
  recipe is replaced by this one: do not reuse build number 556.
- Recipe: `.github/diagnostics/melonxperf558_tree.py` (FIX558 from `cfce9f6`;
  nine 553 parity files replaced; no file of 550, 551, 552, 554 or 557) and
  `melonxperf558_delivery.py`, which checks the 557 receipts on the delivered
  557 tree (`as_557`; the 557 recipe puts the 554 tree back for its own
  inherited checks) and the new engine and host on the pinned tree; the RAM
  graph proof stays the 553 host's (inputs unchanged). The 537 import input
  that 557 changed (`sqlite_service.dart`) is bound to the 557 receipt.
  Validators `validate_melonx_perf558_ipa.py`, `validate_liquid_glass558_ipa.py`,
  `validate_rpcs3_library_files558_ipa.py`; workflow
  `melonx-perf558-delivery.yml`; recipient `build-utils/delivery-558-recipient.pem`
  (private key outside Git); local receipt `docs/evidence/melonx-perf558-local.json`.
- **Delivered** (26 October, no GitHub release): commit `7b4d002`, run 40397869535
  (checks and cold green), encrypted artifact 12688109052; IPA 0.0.8 (558)
  `RewindBox-Build558-7b4d002…-cold.ipa`, 188,054,032 bytes, SHA-256
  `7a9964f55bb490ae4c3bd813d45c2c3b19bacfad04af49a8be4427f567446e5a`
  (= SHA256SUMS and signed-payload identity). Product trees: 557's with lib,
  native and packages changed by the 558 files only. The three 558 IPA
  validators re-run locally on the decrypted IPA give reports identical to
  CI (standalone MoltenVK packaging hash taken from CI, as for 553). Whole
  Dart suite 3560 passed / 24 failed against 557's 3551 / 23; the 24th
  (`melonx_presentation_widgets_test`, a timed wait) fails identically on
  the delivered 557 tree. Receipt `docs/evidence/melonx-perf558-delivery.json`.
  No iPhone run yet. **Do not reuse 558.**

## Private 557: library-folder PS3 disc lifecycle and queued ROM folder saves — 26 October 2026

- Maintainer request after 554: "je t'autorise à finir ce que tu n'as pas
  corrigé. Il faut tout corriger." Analysis: `docs/rpcs3-library-files557.md`.
- Fix `d645f05` (Dart only; 551 Core and native bridges unchanged):
  `SqliteService.saveUserRomFolders` queues saves in call order (a transaction
  opened during another runs inside it on the shared connection: `UNIQUE
  constraint failed: user_rom_folders.path`); the scan keeps an iOS PS3 `.iso`
  row linked to a title while its folder exists (two `RPCS3_LIBRARY_FILE` blocks
  in `sqlite_database_service.dart`); the launcher boots such a row by title ID
  without its file; `Rpcs3LibraryService.settleLibraryFileRows` relinks renamed
  ISOs from PARAM.SFO, folds rows whose file is gone, and on a live sync removes
  rows of titles RPCS3 no longer holds; the install prompt can delete the
  original and its key once installed (off by default); `Rpcs3LibraryFileDeletion`
  deletes ISO, key, RPCS3 copy and row; the PS3 multi-delete lists every row;
  search shows no error for a cancelled launch. The Build 419 contract
  (`test/retroarch_baseline_scope_test.py`) reconstructs both SQLite files'
  419 bytes (`ROM_FOLDERS_SAVE_557`, `RPCS3_LIBRARY_FILE_BLOCK`).
- Private IPA **0.0.8 (557)** from `b71a046`, run 40389098711: the delivered 554
  tree plus the 11 shipped Dart files of `d645f05` (recipe `4e232f7`); same 551
  Core dylib as 554. 188,024,522 bytes, SHA-256 `208118f4…129c01`, encrypted
  artifact 12685546029 for `build-utils/delivery-557-rpcs3-recipient.pem`
  (private key outside Git); decrypted, re-checked, delivered. Evidence:
  `docs/evidence/rpcs3-library-files557-local.json` (whole Dart suite on the 557
  and 554 trees: 3551 vs 3527 passed, the same 23 failures; negative controls on
  554), `docs/evidence/rpcs3-library-files557-delivery.json`. No iPhone
  validation yet. **Do not reuse 557.** 556 was never delivered (MeloNX recipe
  `640ff06`, unarmed); 558 = MeloNX measurement build on the 557 tree (Claude
  MeloNX session).
- 557 replaces files earlier receipts hash (550 `search_screen.dart`, eight 554
  files, `sqlite_service.dart`, an input of the 550 and MeloNX 537–553
  receipts): `rpcs3libraryfiles557_delivery.as_554()` puts the delivered 554
  tree back (scratch index, 554 bytes of the 557 files, BUILD_NUMBER 554) for
  every inherited check, then restores the 557 tree (re-entrant). A build on the
  557 tree chains `rpcs3libraryfiles557_tree.py` and gives the 557 checks a view
  where its own files are at their 557 versions and its recipe is absent.

## Private 554: RPCS3 import of library-folder PS3 discs — 26 October 2026

- A user's `app.log`: a PS3 ISO in `Documents/roms/ps3` was listed by the scan,
  but all 20 launches ended in the RetroArch route (`RetroArchLaunch ...
  stage=cacheEmpty ... No persisted RetroArch export is available`) while the
  RPCS3 library stayed at 0 games. On iOS the router handed a PS3 row to RPCS3
  only with a title ID, which a scanned file never has; RPCS3 boots only
  titles installed in its library. Analysis: `docs/rpcs3-import554.md`.
- Fix `410678b` (Dart only): every iOS PS3 row takes the RPCS3 branch, which
  returns on every path. A library-folder `.iso` is resolved by
  `Rpcs3LibraryFileService`: `PS3_GAME/PARAM.SFO` read in place
  (`Rpcs3DiscImage`, ISO 9660); a disc RPCS3 holds (title ID, or same image)
  is linked; otherwise the user is asked, RPCS3's own `installIso` copies it
  (sibling `.dkey`/`.key`), the row is linked (`Rpcs3LibraryService.linkLibraryFile`)
  and the game boots. The import menu accepts `.dkey` and logs every result
  (`RPCS3 import: ...`, `RPCS3 library file: ...`; never `key=`, which the log
  redaction scrubs). `GameLaunchResult.cancelled()` is a decline, not an error.
- Not changed: `search_screen.dart` (frozen 550 interface) still notifies a
  generic launch error after a decline from search; the repeated
  `UNIQUE constraint failed: user_rom_folders.path` is two concurrent config
  saves on one SQLite connection (reproduced), but `sqlite_service.dart` is
  pinned by the Build 419 rollback contract.
- Private IPA **0.0.8 (554)** from `9f6892b`, run 40360743251: the delivered 553
  tree plus the 8 shipped Dart files of `410678b`; 551 Core unchanged (same
  dylib as 552/553). 188,012,202 bytes, SHA-256 `51d8024e…d4f2b4`, encrypted
  artifact 12667899580 for `build-utils/delivery-554-rpcs3-recipient.pem`
  (private key outside Git); decrypted, re-checked, delivered. Evidence:
  `docs/evidence/rpcs3-import554-local.json`, `docs/evidence/rpcs3-import554-delivery.json`.
  The 553 checks are bound to the 553 tree computed from the 554 index
  (`rpcs3import554_tree.product_trees_553`), equal to the delivered 553 IPA's.
  No iPhone validation yet. **Do not reuse 554.** Next numbers: 555 = the RPCS3
  Cell work of `f508f1b`/`8593169` (`[rpcs3-cell555-core]`, authored "Tarble FR":
  the maintainer or a non-Claude agent; not the Claude RPCS3 session, whose last
  delivery is 551); 556 = MeloNX measurement (Claude MeloNX session; never
  delivered, rebuilt as 558 on the 557 tree). A build
  on the 554 tree chains `rpcs3import554_tree.py` and, like
  `rpcs3import554_delivery.py`, rebinds the previous recipe's `product_trees*`
  so the earlier receipts see the 554 files at their 553 versions.

## Private 552: RPCS3 551 launch-crash fix — 26 October 2026

- Maintainer logs: every 551 launch (Dragon Ball Z twice, God of War III once)
  ended within 0.4 s of `game_boot_return`, before `JITPROF_BOOT`, with no
  error line; the app restarted 2-3 s later. Only the RSX thread was starting.
  Both titles had, for the first time on the iPhone, MoltenVK asynchronous
  submits (+ high global priority), asynchronous texture streaming, FIFO 4 KiB
  and the ARM64 batch; only the submits act in that window. Unproven without a
  stack. Analysis: `docs/rpcs3-crash552.md`.
- Fix `6b527ca`: Dragon Ball Z `BLES01658` has no title profile (the 547 global
  profile); God of War III keeps the 551 profile with
  `MoltenVK Asynchronous Submits: Disabled` and
  `Asynchronous Texture Streaming: false` (explicit; the official GameDB asks
  for true; on MoltenVK it enables async compute, passthrough DMA and
  cross-queue events). `report_fatal_error` logs then aborts: the logger now
  writes `core_log` lines before returning, so a fatal line reaches
  `RPCS3-diagnostic.log` (macOS test with the 551 logger as losing control).
- Private IPA **0.0.8 (552)** from `6a72700`, run 40335530316: the 551 tree plus
  the `6b527ca` files, 551 Core unchanged (run 40247161327, artifact `38bd663e…`).
  186,533,120 bytes, SHA-256 `5ffc8bcd…037467`, encrypted artifact 12657104494
  for `build-utils/delivery-552-rpcs3-recipient.pem` (private key outside Git);
  decrypted, re-checked, delivered. Evidence: `docs/evidence/rpcs3-fix552-local.json`,
  `docs/evidence/rpcs3-fix552-delivery.json`. The 551 Core identity records the
  profile file, its Dart test and `test/native/rpcs3_cell551.inc` as inputs;
  `rpcs3fix552_delivery.validate_rpc_core_identity` binds those three to
  `6b527ca` and the rest to `4e5bf59`. No iPhone validation yet.
  **Do not reuse 552.** 553 is the MeloNX parity IPA on this tree.

## MeloNX standalone parity (private 553 after the RPCS3 crash fix 552) — 26 October 2026

- **Numbering:** the user asked the interface session for the urgent RPCS3 551
  crash fix as **552**; this MeloNX IPA yields 552 and becomes **553**, pinned on
  that 552 tree. Run 40331958399 (recipe `melonxparity552_*`, commit `e458b1d`)
  is only a dry run of the recipe on the 551 tree and is **not delivered**.

- After 549 (`threading=On`, no more "GPU too slow"), the Persona 5 Royal
  flicker and Persona 4 Golden stutter remained. A second comparison with the
  standalone app (`docs/melonx-persona-performance-2026-10-25.md`, section
  "Standalone parity after 549") led to `62626c0`: selectable MoltenVK, with
  the standalone app's own `libMoltenVK.dylib` as default
  (`MeloNXMoltenVKStandalone.framework`, unmodified pinned bytes SHA-256
  `5735ca4a…`, only the install name changes; **maintainer-approved exception
  to source-built engine libraries**, Apache-2.0 notice in
  `Legal/MeloNX/StandaloneMoltenVK`), in-game "MoltenVK version" switch (next
  start; falls back to RewindBox's 1.3.0 if the standalone one does not start),
  stderr teed into `app.log` as `[MeloNX:stderr]`, `configuration/engine`
  journal line, `set_unbounded_present_target_fps` on layout, Game Mode keys,
  no auto-lock in game, and the standalone config's stored threading Off no
  longer imported. Presentation probe fix `0452528` (tests only).
- Review before building (`docs/melonx-persona-performance-2026-10-25.md`):
  `a487268` gives NSLog lines a separate stderr budget and limits the MoltenVK
  fallback to a framework load failure; `6633588` clears, once per game, the
  threading Off stored from the 549-551 import.
- Engine `62626c0f` run 40328874348 (artifact 12654516832), host `a4872682`
  run 40339415828 (artifact 12658953626). 553 recipe:
  `.github/diagnostics/melonxparity553_tree.py` (the RPCS3 crash-fix 552 tree,
  `rpcs3fix552_tree.py`, plus exactly the parity files, from `62626c0`,
  `a487268` and `6633588`; the two sets share no file), `melonxparity553_delivery.py`,
  `build-utils/validate_melonx_parity553_ipa.py`,
  `validate_liquid_glass553_ipa.py` (the RPCS3 validator is
  `validate_rpcs3_552_ipa.py` unchanged), workflow
  `melonx-parity553-delivery.yml`, recipient
  `build-utils/delivery-553-recipient.pem` (private key outside Git). Frontend
  re-run on the pinned 553 tree: `docs/evidence/melonx-parity553-local.json`.
  Armed after 552 was delivered (run 40335530316).
- Delivered private **0.0.8 (553)**: run `40342988817` on `4a4d0fc6`,
  187,987,716 bytes, SHA-256
  `82abd2480f6a7e1d666088262dbe985b596ebd51be2f8b232bfad2a004e1997a`,
  encrypted artifact 12661083441 for `build-utils/delivery-553-recipient.pem`
  (private key outside Git); decrypted, parity and interface validators re-run
  locally on the build commit (reports identical to CI), delivered for
  SideStore re-signing. Installs over 547-552 keeping the RPCS3 552 fix and the
  550 interface. Receipt: `docs/evidence/melonx-parity553-delivery.json`.
  **Do not reuse 553.** A later MeloNX IPA should pin on
  `.github/diagnostics/melonxparity553_tree.py`. The dry run
  of the same change on the 551 tree (552-named recipe, run 40331958399) passed
  every job including the macOS Swift capture and the IPA validators.
  Not a flicker fix claim: an A/B to run on iPhone.

## RPCS3 551: God of War III profile finally applied, RSX queue and Metal compile QoS — 25 October 2026

- The maintainer sent build 547 logs (DBZ HD Collection BLES01658 process
  32192; process 32208 with God of War III's measurements). Facts, changes,
  limits and the iPhone protocol: `docs/rpcs3-cell551.md`.
- Every God of War III boot from build 412 to 547 reported `CONFIG_LAYERS
  legacy_custom=1 database=0`: an old full `config_BCES00510.yml` disabled the
  database layer, so its RewindBox profile never ran. Core record `cell551`: a
  full custom config now keeps only the settings it changed relative to the
  global config and inherits the database settings it left at the global value
  (`RPCS3IOSConfigInheritance.h`, `System.cpp`; CONFIG_LAYERS `inherited=`
  `kept=`). The God of War III profile no longer forces Async shaders (skipped
  draws are excluded by the maintainer).
- iOS Experimental `MoltenVK Asynchronous Submits` (Automatic = off; enabled by
  the God of War III and DBZ profiles) with high-priority device queues
  (MoltenVK's encoding queue becomes user-interactive). Metal compiles run in
  the waiting thread's QoS class: `build-utils/rpcs3/patch_moltenvk_compile_qos.py`
  renames MoltenVK 1.4.2's single `dispatch_get_global_queue` call
  (MVKMetalCompiler::compile) in a copy of the pinned archive; the Core defines
  `rbx_mvk_compile_qos_queue`. New DBZ profile: async submits, FIFO 4 KiB, ARM64
  batch, async texture streaming.
- Diagnostics: `COREPROF RSXSYNC551` (GPU waits by reason, submit, acquire,
  present, frame latency, Metal compile classes), `RSXFRAME551` (RPCS3 frame
  statistics, stage timers on one frame in eight), `SPUWAIT551`; timeline
  `title`, `config`, `rsx_sync`, `rsx_frame`, `spu_wait`. SPUThread.cpp aliased:
  PPU/SPU identities unchanged. Build numbers: 549 is the combined Liquid Glass
  + 547 Core + MeloNX threading IPA (c605eafd); 550 is the new interface on the
  549 tree (69404f45); **551 is the RPCS3 delivery**. No iPhone validation yet.
- Delivered private 551: run `40249519900` on `8715bd55` (the 550 product tree
  plus only the files of `4e5bf59b`; Core run `40247161327`, Core SHA-256
  `38bd663e…`), IPA 0.0.8 (551) 186,532,490 bytes, SHA-256
  `2795e6db2dbdd0c95ce6313f3ad905ec4f2f8701b13efbc5b02bbd67090cd7d5`, recipient
  `build-utils/delivery-551-recipient.pem` (private key outside Git). Receipt:
  `docs/evidence/rpcs3-cell551-delivery.json`. A later RPCS3 IPA should pin on
  `.github/diagnostics/rpcs3cell551_tree.py`. **Do not reuse 551.**

## Private 550: interface feedback on the 549 tree — 26 October 2026

- Maintainer feedback on 548, fixed in `e12f1d4`: main header on one line
  (JIT dot and its 2 s polling removed, clock glyph removed, header pills then
  tabs shrink instead of wrapping; text above 125 % keeps its size and wraps),
  fourth general style "NeoStation" (solid accent pill, 160 ms, LB/RB glyphs,
  matte surfaces, no blur), working Interface preview (style chip and menu,
  labels switch, Apply/Revert), opaque Interface screen, floating side-menu
  bubbles in Settings and Scraper (panel optional), and new options in 12
  languages: status bar items, accent colour, controller focus style, LB/RB
  glyphs, side-menu panel. Details: `docs/liquid-glass-ui.md`.
- Private IPA **0.0.8 (550)** from `69404f4`, run 40245459841: the 549
  product tree with the `e12f1d4` interface, each file from the commit that
  validated it (`.github/diagnostics/liquidglass550_tree.py`); 15 shipped files
  differ from 549, all interface files. 186,517,507 bytes, SHA-256
  `fcb25fca…281ac0b`, encrypted artifact 12619082525 for
  `build-utils/delivery-550-recipient.pem` (private key outside Git);
  decrypted, interface validator re-run locally (report identical to CI),
  delivered for SideStore re-signing. Installs over 547, 548 and 549 without
  losing the RPCS3 547 Core or MeloNX threading. Evidence:
  `docs/evidence/liquid-glass-ui550-local.json`,
  `docs/evidence/liquid-glass-ui550-delivery.json`. No iPhone validation yet.
  **Do not reuse 550.** 551 is claimed by the RPCS3 session; a later RPCS3 or
  MeloNX delivery that must keep this interface should build on the 550 tree.

## Private 549: Liquid Glass + RPCS3 547 Core + MeloNX threading and FPS counter — 25 October 2026

- A user reported Persona 4 Golden flicker and slowdowns absent from standalone
  MeloNX: the embedded engine forced `BackendThreading.Off`. Diagnosis and fix:
  `docs/melonx-persona-performance-2026-10-25.md`. Threading is now On by
  default (per-game "Backend threading" switch, 12 languages); the window
  lifetime releases the threaded renderer from the controlling thread after the
  render loop drains (`NotifyRenderDrained`), keeping quarantine guarantees.
  The RAM overlay shows the engine's game FPS
  (`neostation_melonx_performance_snapshot`, resolved optionally by the host).
- Engine `9bf068b3` run 40235589254 (attempt 2; attempt 1 died fetching the
  upstream source and left a same-named artifact with the previous engine, so
  deliveries take artifact 12614789426 by ID and digest); host run 40235589280.
- Private IPA **0.0.8 (549)** from `c605eafd`, run 40242492444: the 546
  delivery tree with the RPCS3 547 Core files (as in 547), the Liquid Glass
  interface (as in 548) and the 11 MeloNX files; the three sets share no file
  (`.github/diagnostics/melonxthreading549_tree.py`). 186,489,037 bytes,
  SHA-256 `63a1ff6a…076e95e`, encrypted artifact 12617463688 for
  `build-utils/delivery-549-recipient.pem` (private key outside Git);
  decrypted, re-validated locally, delivered for SideStore re-signing. Installs
  over 547 and 548 without losing either. Evidence:
  `docs/evidence/melonx-threading549-delivery.json`,
  `docs/evidence/melonx-threading549-local.json`. `melonx_transfer_test.dart`
  still fails one Liquid Glass Import-icon contrast case, identically on the
  delivered 548 tree. No iPhone validation yet. **Do not reuse 549.** Per the
  other sessions: 550 is suggested for the next interface IPA and 551 is
  claimed for the next RPCS3 delivery; check before using either.

## RPCS3 547: GPU fence wait and SPU compile pressure — 25 October 2026

- First step of the deep optimisation phase (`docs/rpcs3-cell547.md`: the five
  measured costs, what is not done and why).
- Core `1b5c278c` (run 40232640441), record `cell547`: iOS `vk::wait_for_fence`
  without timeout spins 100 us then blocks in `vkWaitForFences` (an 8 ms GPU
  wait costs 116 us of waiter CPU instead of 30.6 ms on macOS arm64); while a
  draw waits for a pipeline build, confirmed SPU GETLLAR polls of unchanged data
  take the existing passive wait; `COREPROF PRESSURE547` and the timeline
  `pressure` family. SPUThread.cpp aliased: PPU/SPU identities unchanged.
- Private IPA **0.0.8 (547)** from `08f2f7fa`, run 40233140957, on the 546
  delivery tree (Liquid Glass excluded, `rpcs3cell547_tree.py`): 186,395,394
  bytes, SHA-256 `09030d12…d9e4e6`, encrypted artifact 12614695376 for
  `build-utils/delivery-547-recipient.pem`; decrypted, re-validated, delivered.
  Evidence: `docs/evidence/rpcs3-cell547-delivery.json`. No iPhone validation
  yet. **Do not reuse 547.** 548 is the Liquid Glass interface, built on the 546
  tree: it carries the RPCS3 546 Core, not 547, so installing 548 over 547 drops
  the 547 Core changes. A build combining both needs a new number (549+).

## RPCS3 546: build 541 logs, JIT object writes, bounded diagnostics — 25 October 2026

- The maintainer sent build 541 logs (Bladestorm BLES00113, Dragon Ball Z HD
  Collection BLES01658; no God of War III Core lines survived). Analysis, facts
  versus hypotheses and the iPhone protocol: `docs/rpcs3-cell546.md`.
- Core `343649293c` (run 40230183096), record `cell546`: zip() writes PPU/SPU
  LLVM objects with zlib level 1 on iOS (3.58 s for one 6.66 MB object at
  level 9; 4.4x faster on ARM64 code, +7 % bytes; caches stay valid); restore
  trace only on a thread that began a restore. Codegen identities unchanged.
- Host: bounded `RPCS3-restore-trace.log` (no fsync), milestone rotation
  instead of truncation, `RPCS3-timeline.log` (one row per Core window,
  2 MiB + .1), `LOG_BUDGET dropped=`, explicit GameDB publication log.
- Private IPA **0.0.8 (546)** from `6c6c6241`, run 40231210331: 186,395,032
  bytes, SHA-256 `4ae64690…942742`, encrypted artifact 12613457207 for
  `build-utils/delivery-546-recipient.pem`; decrypted, re-validated and
  delivered. Evidence: `docs/evidence/rpcs3-cell546-delivery.json`. No iPhone
  validation yet. **Do not reuse 546.** The next RPCS3 IPA (Core cell 547:
  fence wait, SPU compile pressure) is **547**; **548** is reserved for the
  Liquid Glass interface candidate (`docs/liquid-glass-ui.md`).

## RPCS3 545: public ARMSX3 22528 fixes — 25 October 2026

- The maintainer sent the ARMSX3 22528-eef0dc9c notes and chose "port the
  missing, useful fixes". `eef0dc9c` is private; only public RPCS3/ARMSX3
  commits were ported (classification: `docs/rpcs3-cell545.md`). The RPCS3 543
  session handed over the RPCS3 files from 54fd900b.
- Core `39ad9725` (run 40223313523), record `cell545`: SPU warmup dedup and
  biggest-first order (codegen identities kept through
  JITCacheCompatibility), PKG path containment (custom installers held to
  dev_hdd0), debug SELF decryption, SCE iv_idx bound, in-memory savestate
  files, cellSaveData SDK 2.6 cap, thread-local log buffer. Harness
  `test/rpcs3_cell545_test.py`. MFC shuffling, SPU mailbox/SNR timing, RPCN
  and app-side patches were deliberately not ported.
- Private IPA **0.0.8 (545)** from `e5007d92`, run 40223565422: 542 host +
  MeloNX close fix (544) + RPCS3 545 Core. 186,386,764 bytes, SHA-256
  `26cf7d78…d4c3ee`, encrypted artifact 12610469398 for
  `build-utils/delivery-545-recipient.pem`; decrypted, re-validated and
  delivered for SideStore re-signing. Evidence:
  `docs/evidence/rpcs3-cell545-delivery.json`. No iPhone validation yet.
  **Do not reuse 545.**

## MeloNX close teardown and Persona review — 25 October 2026

- Smash Bros. Ultimate (PID 30506, build ≥539) stopped its guest, then the
  render worker's single GpuContext.Dispose failed in PhysicalMemory.Destroy →
  TextureCache.Dispose with ObjectDisposedException(RegionHandle). BufferCache
  had already been disposed: Destroy ran once; a listed texture had already
  released its tracking handles. The session was quarantined, the 4 GiB donor
  lease retained, and the plugin answered isSessionActive=true forever, so the
  Flutter "closing" route never ended. Report:
  `docs/melonx-fermeture-persona-2026-10-25.md`; evidence:
  `docs/evidence/melonx-close-teardown-2026-10-25.json`.
- `build-utils/melonx/adapt_gpu_lifetime.py`: never evict the texture being
  added/lifted (MeloNX 2.6 loop regression), idempotent Texture/TextureGroup
  disposal, tolerant TextureCache teardown with journal counters, one
  PhysicalMemory destruction, ConcurrentQueue deferred actions (RewindBox stops
  the guest while rendering), complete renderer release before reporting an
  error. Unknown release errors still quarantine; do not weaken that rule.
- The plugin records a post-run quarantine: isSessionActive=false,
  isSessionQuarantined=true, relaunch → `quarantined`/requiresRestart. Dart
  shows the 12-language explanation until acknowledged and keeps frontend
  audio paused. MeloNXSessionHost.swift stays identical to `084fdb5d`.
- Executed on Linux .NET 10.0.100 against the compiled pinned Gpu/Cpu/Memory
  projects (GAL double only): control reproduces the device stack; fixed passes
  7 scenarios (`test/melonx_gpu_teardown_test.py`, wired into melonx-core.yml).
  Flutter close-status/audio/route/launch-flow tests pass on 3.47.2. CI: engine
  d9f35c27 run 40210266656 (macOS harness, NativeAOT ABI, two ARM64 simulator
  homebrew sessions with close and relaunch) and host eabc057f run 40209413009
  succeeded. Private IPA **0.0.8 (544)** from `a5bd2bb7`, run 40213735246:
  validated 542 host + RPCS3 542 Core + only the MeloNX close files (runner pin
  `.github/diagnostics/melonxclose544_tree.py`; RPCS3 543 excluded). IPA
  186,348,693 bytes, SHA-256 `69293526…507180f`, encrypted artifact
  12607122894 for `build-utils/delivery-544-recipient.pem` (private key outside
  Git), decrypted and re-validated, delivered for SideStore re-signing.
  Evidence: `docs/evidence/melonx-close544-delivery.json`. No iPhone validation
  yet. **Do not reuse 544.**
- Persona 4 Golden (010062B01525C000, v0): no error after the 530 host-import
  fix in the supplied journals; its 10:59 `localGameRequired` is a stale
  container path right after reinstall, not a regression. Persona 5 Royal black
  regions remain unconfirmed: no P5R session ≥540 was supplied. Do not apply a
  P5R hypothesis to P4G. No release, tag or main change.

## RPCS3 memory audit implementation — 23 October 2026

The maintainer explicitly asked Codex to implement the attached ARM64/iOS audit.
Work is isolated in work/rpcs3-audit-20261023 from Claude 932e4a9f; preserve
concurrent frontend work, MeloNX and unrelated engines. Detailed scope and
F1-F9 mapping: docs/rpcs3-memory-audit-2026-10-23.md. The canonical Core delta
now owns direct bounded object loading, a bounded validated PPU object window,
shared host NeoSwap compiler admission, in-phase memory observations,
fault-before-reservation ordering and free data-page advice. Code aliases and
ABI 30 remain unchanged. Small-heap VMA granularity is based on the reported
heap, not the phone's physical RAM. The minimal-object SPU linker is a research
prototype, disabled in production pending real-title binding/gameplay proof.
Do not claim FPS, footprint savings or physical relaunch validation from host
fixtures or a successful Core build. Do not alter main or publish releases/tags.
Use the dedicated rpcs3-memory-audit workflow for the immutable candidate and
reuse unrelated validated components; no Flutter campaign for this Core work.

## Current MeloNX embedded test integration — 22 October 2026

This continuation supersedes the older bootstrap-only/staged descriptions below.
The user explicitly authorized completing MeloNX in an isolated checkout, merging
into Claude, and producing a test IPA without any release, tag or main change.

- Actual source-built engine: host `38d997064cd81c5f17de6187ab36d2c78b0ba97c`,
  run `39858967222`, iPhone and ARM64 simulator. Session ownership, startup
  pause, firmware rollback and bounded game-header/metadata checks are included.
- Swift/Objective-C++ host: `721380dd7f241d1343fe6ae8fbf563e1b63f6d66`, run
  `39859362301`. Original editable controls, generation-bound input, controller
  mappings, first-Metal-frame launch confirmation and dedicated host-PID JIT
  are registered by the local Flutter plugin. Cancellation before presentation
  cannot start a new session. SDK type checks and ABI-double cases passed.
- Real NativeAOT initialization initially failed because SDL was not prepared
  for UIKit's main(). The host now calls the private SDL_SetMainReady and video
  initialization on the UIKit thread before managed initialization on its
  library worker. Actual simulator bootstrap `39859017226` passed against the
  preceding engine. Final-engine smoke run `39859909967` must pass before IPA.
- Private SDL, MoltenVK, FFmpeg and assembly JIT-support frameworks are built
  from pinned sources; dependency audit `39854858591` passed. No upstream
  unverified prebuilt frameworks or BreakpointJIT binary are redistributed.
  Managed package resolution, original notices and build configuration are
  retained with the engine artifact. Preserve both upstream MIT notice and
  GPLv3 README statements; do not invent a blanket license clearance.
- Switch playlist imports personal local games, firmware, keys, updates and
  DLC. Add-ons are inspected against the actual base title. Graphics settings
  are persisted per game. Flutter/integration run `39857539994` passed; its Dart
  inputs remain unchanged. The legacy external launcher is not restored.
- Build 506 assembly is prepared in retroarch-delivery.yml and
  melonx506_delivery.py; no IPA is claimed until that workflow completes and
  the downloaded payload is independently verified. Startup/Liquid Glass 505,
  HD catalogues and all other emulator code remain unchanged.
- NeoSwap live loans are intentionally not connected to MeloNX's resetting
  Offer/Withdraw API. No fake donation, Switch storage-backed GiB or device
  performance is claimed. Switch HD references remain research-only without
  a validated payload/format. Physical gameplay/audio/controller/relaunch
  verification still requires an iPhone. No Jetsam/IPS requests.

## AI coordination — maintainer rule, 21 October 2026

**Claude Code must remain the principal coder and integrator for RewindBox iOS.** ChatGPT/Codex coordinates, investigates and reviews; Cursor Agent handles light assistance and explicitly authorized isolated small fixes. This is a manual three-agent workflow, not an autonomous cross-subscription orchestrator. See `docs/AI_ORCHESTRATION.md` and `docs/AI_TASK_BOARD.md`.

Do not use separately billed API keys, extra credits, automatic top-ups or third-party Cursor models that require prepaid credits as a way around subscription quotas. All three agents must observe the existing `Claude` branch policy, single-writer checkout rule, targeted validation and explicit permission for pushes, GitHub Actions/IPA builds and releases. The maintainer approves the final result.

# Consignes permanentes — stabilité NeoStation iOS

## MeloNX owned-session continuation — 20 October 2026

- Native session ABI 1 now implements prepare/run/stop/pause/cancel/state/error,
  with borrowed UTF-8 buffers and generation IDs. One owner stops input, ends
  the guest while GPU service remains live, joins rendering, then releases
  host resources. Partial execution failure quarantines the process. A late
  stop cannot close the next game. Input drivers remain process-owned; window
  managers and bindings are per-session. Do not restore upstream double disposal.
- Engine source `65f957e7278da94dee601d51e5c2265e64c60fdc`, run `39510222541`,
  job `118929099331`, artifact `12304554717` passed. Independent ZIP/Mach-O/input
  verification: 37,353,112 bytes, SHA-256
  `7a37793779d5014d8686d34a9f6c7f9cddfcb5817372d6dd15b9b9d1dab882c5`,
  22 required exports. The previous bootstrap-only binary remains historical.
- Swift native host and CAMetalLayer presentation primitive exist under
  `packages/melonx_internal_bridge/ios/Classes`; they are not yet registered as
  a Flutter plugin or packaged in Runner. They retain the render layer and
  report active through clean native return. Quarantined hosts/layers remain
  rooted and active until process exit, including after UI release. Do not mark the
  Switch route available from these source files or ABI compatibility alone.
- Run `39510222562`, source `65f957e7278da94dee601d51e5c2265e64c60fdc`,
  job `118929099480`, artifact `12304664296`: iPhone SDK type-check and 20
  executable Swift/native-ABI-double cases passed. These use a native double
  on the macOS runner, not the actual emulator or an iPhone guest session.
- Run `39508485894` passed 15 storage and 20 production session/window-owner
  cases, then failed at a C# visibility error. The visibility error is corrected
  in c49ef51, which passed and reused those exact tests after input/SDK checks.
  The final 65f957e reruns the changed 20 session cases for quarantine retention;
  it reuses the unchanged 15 storage cases. Do not count the initial full
  run as successful, or rerun unchanged tests. LibHac's existing 5-test package
  proof is reused. Receipts: `docs/evidence/melonx-native-session-2026-10-20.json`.
- Eleven committed ARM64/iOS dependencies are inventoried, not embedded:
  `docs/evidence/melonx-native-dependencies-2026-10-20.json`. The supplied
  MoltenVK strongly imports a versioned IOKit path needing resolution before
  packaging. FFmpeg's framework install names need an explicit versioned-name
  resolver; binary presence does not identify its corresponding build source.
- Before input activation, fix the observed shared NativeGamepad ownership:
  HandlePlayerConfiguration disposes the driver's actual gamepad, and its
  Dispose sets IsConnected=false. Also bind late input to a session generation.
  Original Melo-Controller/editor adaptation, dedicated NeoStation-PID JIT and
  its mapping handshake, isolated runtime dependency loading, imports and
  NeoSwap integration remain unfinished. Do not install upstream's broad
  SIGTRAP-skipping handler over the existing engines' handlers. No firmware,
  keys or games bundled; no device/gameplay/IPA claim; no public release.
- Keep native context/window resources rooted on execution failure. Failed guest
  termination must skip GPU release and refuse window disposal. The upstream
  DonatedMemory Offer/Withdraw reset live-loan ownership; do not connect a live
  NeoSwap loan to that API without a broker ownership adapter.
- Detailed continuation: `docs/melonx-native-session-2026-10-20.md`. This block
  supersedes the bootstrap-only readiness description immediately below.

## MeloNX embedded integration — maintainer instruction, 20 October 2026

- Integrate MeloNX as an embedded Switch engine on Claude. The follow-up
  explicitly retires the external entry: no library-sync card, external URL,
  Shortcut or external-process JIT fallback. Preserve personal files, saves and
  cached metadata. Old virtual rows require import of the actual local game.
- Source/architecture/license audit and exact build attempts:
  `docs/melonx-embedded-integration-2026-10-20.md`. Engine pin `13700519f3`;
  upstream .NET 10 NativeAOT is distinct from mandatory guest JIT. Do not mark
  an engine available from an embedded flag or route alone: require the native
  runtime's report. The original LibHac NuGet package remains unavailable;
  matching source `23e402ebb6dedc517e34a98a033078dc0f6fd478` is reconstructed
  locally, with five upstream NACP layout tests passed. Source identification
  comes from the matching consumer change; no original package-byte equivalence
  is claimed. Package SHA-256 `b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9`.
- The first adapted NativeAOT engine now compiles and passes iOS/arm64/export
  checks: source `3ec09b234b758814976d955cf52cf695b2de0226`, successful run
  `39506631512`, artifact `12304021888`; dylib SHA-256
  `0ac7412e80f562f02446feab934aafe3df4e614524811a440ee42467d3646509`.
  Independent ZIP/Mach-O verification matches its receipt. The bootstrap in
  `native/melonx` confines storage to Documents/MeloNX and serializes initial
  engine setup; 15 executable host cases passed and are reused with unchanged
  inputs and matching SDK/runtime identities. It is initialization only.
- Native game sessions, app runtime packaging, JIT for NeoStation's PID,
  imports, original touch/editor adaptation and NeoSwap integration remain
  incomplete. No Switch game/homebrew/device run or test IPA is claimed.
  Before activation, resolve session ownership/relaunch: upstream Load disposes
  its input manager and Stop/Exit/ExecutionEntrypoint can repeatedly dispose
  the same emulation context. Do not equate the bootstrap ABI with session
  readiness. No engine is yet packaged in a NeoStation IPA.
- Retain the existing dedicated Dolphin/ARMSX2/RPCS3 helper identities and
  source-built StikJIT framework. The two old Swift launcher source snapshots
  remain only for the unchanged framework ABI/source verifier and are explicitly
  excluded from CocoaPods compilation. Neither is registered by the app. No
  StikJIT rebuild is needed for this removal. Main.dart's exact removal-only
  exception is reconstructed in the baseline test; other protected library
  bytes stay unchanged.
- The Switch HD research entries remain research-only. No pack is installable
  until the actual engine adapter loads its format and exact target/version.
  No firmware/keys/games are bundled. No public release is authorized.

## Recherche PS1 HD — continuation courante, 20 octobre 2026

- État courant : **180 familles, 228 fiches, 48 hors décompte, 141 jeux/éditions, 47 groupes crédités**. 53 familles mentionnent Beetle, 109 DuckStation, 9 communes. Ce total 180 ajoute une nouvelle famille après la correction Tekken 2 de la passe précédente ; il ne rétablit pas ce doublon. 97 requêtes web et 14 recherches de dépôts GitHub consignées ; 298 URLs de consultation avec échecs, sans assimiler les résultats indexés à des pages lues.
- **38 références PS1 = 8 téléchargements vérifiés + 30 pages d’auteurs**, 36 jeux/éditions. Nouvel original : Resident Evil: Survivor HQ de LeigiBoy, page ModDB publique, Beetle confirmé par les publications de l’auteur. RAR annoncé 718086365 octets, fichier du 9 octobre 2025 ; téléchargement temporaire observé 410, aucune archive transférée ou inspectée. USA SLUS-01087 candidat à confirmer, pas de support PAL établi ; personnages/ennemis et palettes animées limités. Pas de téléchargement intégré ni de rendu iPhone déclaré.
- Onze pistes nouvelles restent hors décompte : Parappa, Bugs Bunny, WipEout interface, trois démos DuckScaler, trois essais historiques Libretro, un relais Chrono Cross sans auteur établi et un composant Tomba 2. L’outil DuckScaler et Faithful Remaster ne sont pas des packs publiés. Aucun nouveau pack prioritaire Crash/FF/Tekken/Tomb Raider installable confirmé. Suikoden II Kyaro reste vérifié ; les autres formats DuckStation ne deviennent pas Beetle par renommage.
- Source catalogue **b5207313a5ac9458b9ea765daf72d04a781b937e**, révision **2026-10-20.cb9ec63ce729**, SHA-256 **80b1284294d7ac29d4a64f5512af1b3ffd61f26753df898ee28e2eab7f633453**. Copies distante/embarquée identiques ; 1123 objets précédents et toutes les autres consoles préservés. Global : 1124 références, 424 familles installables / 509 profils.
- Validation ciblée **39496716743** réussie : **189 contrôles Foundation, zéro échec**, 691 observations rapprochées, 19 empreintes d’entrée réconciliées. Artefacts publication12297523218 / natif12297338171 ; brut courant dans `docs/evidence/ps1-hd-catalogue-checks.json`, ancien brut37 archivé dans `docs/evidence/ps1-hd-publications/39484361864.json`. L’ancienne porte39484758626 reste historique et ne couvre pas38.
- **IPA 500 déjà livrée et figée avec37/8/29** ; ne pas réutiliser500. Aucun build IPA demandé pour cette continuation. Aucun Core, moteur, Dart ou UI modifié ; aucun rendu physique attesté, cache borné et chargement à la demande. Travail surClaude uniquement. Rapport `docs/ps1-hd-continued-research-2026-10-20.md` et journal `tools/textures/research/ps1-continued-research-2026-10-20.json`. Ce bloc remplace les compteurs courants plus anciens, dont les preuves restent historiques.


## Priorité PS1 HD aux grandes séries — 20 octobre 2026

- Demande du mainteneur : chercher essentiellement Crash PS1, Final Fantasy, Suikoden, Tekken, Tomb Raider et autres grands titres. Priorité aux titres couverts et aux archives réellement compatibles, pas au volume. Matrice19 jeux /44 requêtes : `tools/textures/research/ps1-major-franchises-2026-10-20.json` ; rapport `docs/ps1-major-franchises-2026-10-20.md`.
- Correction de crédits : EstudioCases attribue ses textures Tekken2 à Bl4ckH4nd ; conserver les deux IDs mais une seule famille. État corrigé **179 familles,216 fiches,37 hors décompte,140 jeux/éditions,46 groupes crédités** ;52 familles nomment Beetle,109 DuckStation,9 communes. L’ancien total180 reste historique. Aucun nouveau téléchargement vérifié dans cette passe ; catalogue37/8/29 et IPA500 inchangés.
- SuikodenII Kyaro est déjà vérifié. FFVII/VIII et Tekken sont essentiellement DuckStation ; Crash1/Bash HUD/icônes sans archive publique confirmée ; pas de pack PS1 Tomb Raider qualifié. Les ressources PC Glidos/TombATI ne comptent pas comme PS1. Les fichiers DuckStation ne deviennent pas Beetle par renommage ; adaptation à étudier avec dumps, palettes et essais, aucun moteur modifié ici.

## Build 500 livrée — Core RPCS3 499 et dernier catalogue PS1, 20 octobre 2026

- Le mainteneur demande explicitement la dernière IPA NeoStation avec le Core PS3 terminé **et** les derniers catalogues PS1. La499 figée (34 références) ne satisfait pas ce nouvel assemblage ; candidate unique **500**, surClaude, sans release publique.
- Réutiliser le Core RPCS3 déjà construit et validé : source0b18a23460b0a9840406fda2e3d6da4c5cdb7273, run39472233521, SHA-25687bd77794232fc44b61d421e55d71bae3b2829a58b87ee36b2a176730d78004f, ABI30. Aucun nouveau build Core et aucune nouvelle modification moteur, NeoSwap, Dart ou interface. Les autres cœurs et le correctif PSP497 restent identiques.
- Inclure exactement le catalogue PS1 2026-10-20.56904c72933f, SHA-256cd05e0ebd8c1783768f7dbc94f94abe9adce61b376ecc058961ca2e39a2c48a7 :37 références,8 téléchargements vérifiés,29 pages manuelles ; catalogue global424 familles installables/509 profils. Publication39484361864 et porte39484758626 déjà réussies,187 contrôles Foundation. Ne pas rejouer les tests Flutter ou reconstruire les cœurs inchangés.
- Recette500 séparée de499, source d’assemblage figée et provenance explicite. Les deux manifestes sont les seules différences produit autorisées depuis499 ; emballage, numéro500, signature et vérification du contenu final restent nécessaires. La499 livrée reste immuable. SideStore requis pour la signature Apple ; aucune validation physique ou gain FPS inventé.


- Livraison500 vérifiée : source `76cb22f155188908345796ae504958e26eba1427`, workflow `c5ac1161b8b44e1607b8692ffee0152a60fbbd53`, run39487947573 réussi ; artefact12294424092 (ZIP SHA-2562ffd2b0227e1f43987789bed125a73888bcb23d70a1b7efff9b47810e75eab10). IPA0.0.8(500),168389597octets,SHA-256 `0c91d716c51c60391219cc1ce54e30fe7ab980faf39e8ea53f7f82c451b9d625`. Six bundles500 ; Core signé identique à499 (`49033f06bcbe5bfb635a956783f87e35934f21d9be5fd3d84b4d902adb190a63`) ; manifestePS1exact37/8/29. Reçu `docs/evidence/ps1rpcs3500-delivery.json`. Aucun nouveau Core, aucun test Flutter inchangé, aucune release publique. SignatureSideStore/AltStore requise ; pas de validation physique. **500 est figée, ne pas réutiliser ce numéro.**

## Recherche PS1 HD — troisième extension intégrée, 20 octobre 2026

- État courant : **180 familles documentées**, **216 fiches**, **140 jeux/éditions** et **46 créateurs ou équipes crédités**. Gain net de21 familles depuis159 :19 nouvelles lignes et3 promotions, moins1 regroupement conservateur Sesame Street ; tous les197 anciens IDs sont conservés.36 références restent hors décompte.52 familles mentionnent Beetle,110 DuckStation, dont9 communes ;4 projets C et23 moteurs non confirmés. Aucun seuil200/300 ni exhaustivité mondiale revendiqué.
- Catalogue courant : **37 références PS1**, **8 téléchargements vérifiés**, **29 pages d’auteurs sans installation**,35 jeux/éditions représentés. Depuis les2 références initiales :6 nouveaux jeux à téléchargement vérifié. La nouvelle archive originale CAC GAMER Gran Turismo2 partielle passe l’installateur :233 PNG valides,48 802 081octets compressés,162 492 740installés ; USA v1.1 Arcade, confirmation de l’édition obligatoire. Les deux Somber Dead or Alive et Clock Tower:The First Fear restent manuels après défi anti-robot. Aucun contournement ni réhébergement.
- Source catalogue **015e40b70cff8f853709cc6e5cf0a4050c5e3b7f**, révision **2026-10-20.56904c72933f**, SHA-256 **cd05e0ebd8c1783768f7dbc94f94abe9adce61b376ecc058961ca2e39a2c48a7**. Copies distante et embarquée identiques ; les1120 anciens objets sont inchangés. Catalogue global :424 familles installables,509 profils.
- Publication validée : run39484361864, deux jobs réussis,187 contrôles Foundation sans échec et19 entrées de preuve hachées. Archives : run39482826008 (2 refus conservés) et39483666586 (CAC réussi). Registre :691 observations CI enregistrées comparées,701 IDs dans le ledger ; depuis le catalogue initial,19 nouvelles observations PS1 dont6 succès et13 refus. Brut et empreintes dans docs/evidence/ps1-hd-catalogue-checks.json.
- Porte de prochaine livraison réussie : run39484758626, source299cbd90d45a2148d60608df307e5fa4948fbe21, artefact12291804847, ZIP SHA-2569962e69a3fa9970baa388080c8675f5715640dc03c2874693c3952a062dd82dd. Le reçu conserve le nom historique previous32CatalogueObjectsUnchanged pour1120 objets ; il s’agit bien du précédent catalogue de34 références PS1.
- **La499 déjà livrée reste figée**, avec son ancien catalogue34. Cette publication37 surClaude doit être incluse dans la prochaine livraison ultérieure, sans réutiliser499. Aucun Core, moteur, Dart ou interface produit modifié par cette recherche ; aucune IPA produite et aucun rendu physique iPhone attesté. Repli logiciel Beetle sans remplacement ; pas de préchargement intégral recommandé. Inventaire, CSV, rapport complet et provenance actualisés ;247 termes de recherche racine,261 URLs de consultation consignées,1054 URLs issues des résultats de recherche distinguées des sources qualifiées.
- Ce bloc remplace les anciens compteurs courants ci-dessous ; leurs preuves restent historiques.


## Recherche PS1 HD — seconde extension intégrée, 20 octobre 2026

- État courant : **159 familles documentées** (+32 depuis127), **197 fiches**,124 titres normalisés.38 références hors compteur, dont25 assemblages Crazy Ivan à provenance indépendante non établie. Les variantes de région, disque, version et moteur restent regroupées ; aucun seuil200/300 ou exhaustivité absolue n’est revendiqué.
- Le catalogue courant contient **34 références PS1**, **7 téléchargements vérifiés** et **27 pages d’auteurs sans installation**. Nouveaux téléchargements de cette vague : NR74W WipEout (100PNG), NR74W WipEout2097/XL (89PNG), SomberTwilight Tenchu Stealth Assassins USA v1.1 (1757PNG). Édition à confirmer conservée, région des deux NR74W non établie. Thrill Kill a répondu par un défi anti-robot et reste manuel ; Shadow Tower est manuel après144JPEG déguisés enPNG. Aucun contournement ou réhébergement.
- Source catalogue **388f5c5194c5ace2e26ee2753ce1ab221756c512**, révision **2026-10-20.169a7760ffbe**, SHA-256 **f1ffd564157dc5383cb926f4fbec5d560fc9bdd73cdf8caf9302d42227007504**. Copies distante/embarquée identiques ; toutes les1112 anciennes fiches, dont les26 PS1 de la première extension, sont inchangées. Catalogue global :423 familles installables,508 profils.
- Preuves : run39479736059 sur0a2fdbab, trois archives installées réellement et1946PNG décodés, un refus conservé ; run39480710051 sur388f5c51, deux jobs réussis,184 contrôles Foundation sans échec,688 observations conformes aux artefacts canoniques. Rapport et inventaire existants mis à jour ; brut publication dans docs/evidence/ps1-hd-catalogue-checks.json.
- Porte de prochaine livraison réussie : source145616c8c00788bd6be30adb580aadde0c607cec, run39480992757, artefact12290593946, ZIP SHA-25689e40f5ec769608398e00dafa67b927b0b24a5f34c43fca4584c6f307391a06e. La499 doit inclure cette publication exacte (17 entrées de validation), les27 références sans installation et la preuve indépendante du Core RPCS3. Pas de changement Core, moteur, Dart ou UI pour cette recherche, pas de nouvelle IPA et pas de rendu iPhone physique attesté.
- Ces compteurs et cette référence remplacent l’état26/4 de la première extension pour la prochaine livraison ; les preuves précédentes restent historiques.

## PS1 HD catalogue — première extension historique, 20 octobre 2026

- Le mainteneur demande davantage de packs PS1 et leur intégration dans la prochaine mise à jour. Travail sur `Claude`, sans nouvelle IPA demandée dans cette tâche, sans changement de cœur, de moteur ou d’interface. Le catalogue élargi est déjà publié et sa copie embarquée est identique : source `29381d0441081b93b36ed924e9a295a8ba34280c`, révision `2026-10-20.2a44a9d3ed55`, SHA-256 `6b37e6e3adb927c76f98aded2e7784269cd0839d855a56fbb75e02fb0181b4e1`.
- **26 références PS1** au lieu de 2 : **4 téléchargements vérifiés** au total (deux ajouts : Xenogears PAW 1.8 et Suikoden II Kyaro 2.6), **22 pages d’auteurs manuelles**. Dans cet état, les pages manuelles ne comptent pas comme des packs installables, n’ont aucun plan/taille d’installation ni bouton de téléchargement intégré, et leurs identités restent à confirmer. Les 1 088 anciennes entrées sont inchangées ; catalogue global : 420 familles directement installables, 505 profils.
- Archives : run `39475381324` sur `0ed65865`, deux installations réelles (399 + 437 PNG, zéro PNG invalide) ; run `39475695835` sur `070557e7`, dix refus MediaFire (défi anti-robot/403), conservés exactement, sans contournement. Les archives de la boutique 1vierock et la pièce jointe Shining Red non récupérée restent des pages d’auteurs ; Lunar (ENOENT), Silent Hill (404) et les formats DuckStation ne deviennent pas des téléchargements compatibles.
- Validation finale du catalogue : run `39477034529` sur `29381d04`, deux jobs réussis, 177 contrôles Foundation sans échec, 684 observations conformes aux artefacts CI. Kyaro USA exact/PAL candidat, PAW USA/Japon et pages manuelles à confirmer sont sondés dans le vrai catalogue. Source CI et empreintes exactes : `docs/evidence/ps1-hd-catalogue-checks.json`. Rapport : `docs/ps1-hd-catalogue-expansion-2026-10-20.md` ; preuves : `docs/evidence/ps1-hd-catalogue-expansion.json`.
- La prochaine livraison 499 doit inclure ces deux manifestes. Exception bornée dans `rpcs3audit499_delivery.py` : seules les données PS1, leurs preuves et leurs contrôles sont admis ; la porte compare les deux jobs réussis et toutes leurs entrées à l’octet, conserve les anciennes fiches et impose les 22 références sans installation. Tous les autres fichiers produit, Dart et natifs restent identiques à la 498 ; le nouveau Core RPCS3 499 conserve sa preuve indépendante. La livraison 498 figée n’est pas modifiée.
- Porte de livraison dédiée réussie : run `39477840463` sur `e2d30581`, artefact `12290290354` ; rapport brut `docs/evidence/ps1-hd-delivery-guard.json`. Ce contrôle prouve uniquement la clôture du catalogue PS1 ; il ne remplace pas la preuve indépendante du Core RPCS3.
- Recherche étendue : 127 familles de projets (115 auparavant), 140 fiches, 104 jeux ; variantes de moteur, disques, régions et compilations regroupés. L’ancien inventaire reste historique ; état courant : `tools/textures/research/ps1-hd-inventory-expanded-2026-10-20.json`. Aucun rendu sur iPhone physique ni couverture visuelle intégrale des nouveaux packs attestés ; certains éléments UI PAW 1.8 peuvent dépendre d’un Beetle plus récent.


## Build 499 delivered — selective ARMSX3 22348 / RPCS3 audit, 20 October 2026

- The maintainer supplies `ARMSX3-22348-bbe9ce84.ipa` and explicitly requests a deep comparison, selective improvements, a rebuilt RPCS3 Core and a private test IPA on `Claude`. No main push or official release. Preserve the delivered 498 PSP/native-RAR product and every unrelated core. Include the separately verified 34-reference PS1 catalogue mandated above, without rebuilding its unchanged native host.
- The supplied IPA has SHA-256 `0db92aea054b716863eeea486d2102656f20e9a58f8872742ae405deeb43385d`; its private `bbe9ce84` revision does not resolve in the public ARMSX3 repository. Do not equate public master with that exact iOS binary or infer FPS from symbols.
- Port two independently identified, public upstream fixes: SHUFB u64 insertion mask (`d7f4c350`, ARMSX3 `e99467b5`), conditional branch targets taken-first (`9c8e4349`, ARMSX3 `ddd902e7`). Independently gate decrementer disassembly behind explicit SPU debug and move ordinary per-block build lines to trace; preserve error, JITPROF and SPUPROF diagnostics. Add SPUThread.cpp and SPUOpcodes.h to the SPU codegen digest.
- ABI 30, NeoSwap, guest mappings, memory limits, PPU pipeline, JIT/VPN route and deferred-SPU prohibition remain unchanged. New SPU object identity recompiles once; PPU codegen inputs are unchanged. Tests execute production snippets and all 30 SHUFB masks against a scalar reference, actual branch decoding and exact pre-499 controls. No physical-device/FPS claim.
- Core 499 compiled and independently checked: source `0b18a23460b0a9840406fda2e3d6da4c5cdb7273`, run `39472233521`, Core SHA-256 `87bd77794232fc44b61d421e55d71bae3b2829a58b87ee36b2a176730d78004f`, ABI 30, 78 input identities. Native iPhoneOS syntax, cache relocation, LLVM pipelines, 499 controls and passive-load/export checks passed. PPU codegen `cf1718033f6fda2d` is present in both the delivered 498 and the new binary; SPU codegen is `42c4b3542f924d07`. IPA delivered and independently verified; see docs/evidence/rpcs3audit499-delivery.json.
- Private IPA 0.0.8 (499) delivered: source `4fc50a8701db627607821ab393a1522d21fd00c4`, frozen workflow `e91ce81bd2ace6d7820d260cac31d32aca6798dd`, successful run `39482319527`, artifact `12292826550` (ZIP SHA-256 `8899a346956228bd69f065ada982001e85bacacf5679eaa14fb3974ce7058953`). IPA **168,388,839 bytes**, SHA-256 **`fe0925f294addabd0a11c74c4af0db237e38a00d1d177348fa1e3ad58d4a1c4e`**, equal to both SHA256SUMS and signed-payload-identity.json. Six versioned bundles, 4,609 members, no paths added/removed vs 498. Of 75 Mach-O images, 72 have identical compiled sections; change RPCS3, Runner (only build constant and equivalent linkage stubs) and libretro bridge (equivalent linkage stubs only). All 10,110 regular/Objective-C stubs resolve to the same symbol or selector at every index. NeoSwap and every unrelated core retain their compiled sections. Embedded RPCS3 signed SHA-256 `49033f06bcbe5bfb635a956783f87e35934f21d9be5fd3d84b4d902adb190a63`; every compiled section matches the new Core artifact. PS1 index `2026-10-20.169a7760ffbe` is included exactly. SideStore re-signing required; no physical-device or 30-FPS claim. No official release. Do not reuse number 499. Later PS1 research staging is preserved on Claude and outside this frozen IPA.

## Build 498 livrée — catalogue téléchargeable et RAR natif, 20 octobre 2026

- Le mainteneur renouvelle la demande d’élargir le catalogue jusqu’à **400 packs téléchargeables depuis l’application**, puis demande l’extraction et l’installation RAR intégrées. Le gel HD des cycles 496/497 ne s’applique pas à ce nouveau cycle ; la livraison 497 reste figée sur `e999a5fdc98a42f5d1995ca85fdfa04479d7f77a` et ne doit pas être modifiée ni annulée.
- Candidate de ce cycle : **498**, sans publication publique et sans reconstruire les cœurs. Conserver le package PPSSPP 497 vérifié, les autres cœurs, les réglages, bibliothèques et sauvegardes. Une recette de livraison distincte, déclenchée explicitement, évite le groupe d’annulation de la 497.
- Le client ajoute libarchive 3.8.10 en lecture seule (RAR4 non solide et RAR5, symboles préfixés et mémoire bornée), les résolveurs publics Drive/Yandex/MEGA et les imports RAR par les installateurs existants. Les archives chiffrées, multi-volumes et RAR4 solides restent refusées. Aucun fichier de pack n’est réhébergé ou reconstitué.
- Les descripteurs `download.in_app` sont activés seulement par le nouveau client après validation du fichier exact. Les anciens builds gardent le repli manuel/page ; une simple actualisation du catalogue ne leur ajoute pas ces fonctions natives. Les familles et variantes conservent la méthode de comptage existante. Registre CI canonique unique ; anciennes observations remplacées conservées exactement dans les preuves et runs explicitement supersédés.
- Catalogue `2026-10-20.28541bbfe23e` : **418 familles directement installables**, 503 profils/85 variantes ; les 1 086 anciens IDs sont conservés (1 088 au total). Les 209 anciens profils directs et les archives/plans/identités des 231 anciens profils manuels sont préservés. Preuve native finale `d8a11a7d`, run `39461533070` : résolveurs223, MEGA76, compatibilité20, Store125, Foundation169 et 36 sources liées pour iPhone. Six vrais téléchargements antérieurs sont réutilisés uniquement par identité du code HTTP/crypto ; aucune preuve de rendu physique. Bilan et limites : `docs/hd-direct400-rar-native.md`. La livraison 498 utilise sa recette séparée et les cœurs497 inchangés.

- Livraison vérifiée : source figée `2617d176e091d0bff63820a5c46917b17dd4a943`, workflow `69176e02b6e2133075b2745dd06d6a70316674a4`, run `39464441422` (checks/native/cold réussis). IPA **0.0.8 (498)**, **168 386 155 octets**, SHA-256 `6b054cac8a78de265e6d1d1c151d2f8bfb05fed293f3b9715b20cccaa8f37c79`. Les 418 familles et le lecteur RAR/hôtes publics sont contrôlés dans l’IPA scellée ; cœurs497 conservés, aucune reconstruction ni publication publique. Reçu `docs/evidence/hdnative498-delivery.json`. Signature Apple via SideStore requise ; aucun essai physique iPhone attesté. Ne pas réutiliser 498 pour une autre source.


## Build 497 — verified IPA, PSP memory ownership, 20 October 2026

- The maintainer's new app log confirms Build 496 did not fix the observed close/reopen failure. Do not describe 496 as device-confirmed. At 15:30 UTC the core's backing arena occupies its own intended RAM destination (`0x17c000000`, remap from offset `0x204000` fails with kernel error 3).
- Replace the allocator-placement assumption with a versioned host/core memory-ownership contract. Rebuild only PPSSPP from the same upstream `1bd28b0d634d4ec31acb7092563f3e1e247d1e9c`; retain all other pinned cores. Include the final verified 355-family catalogue published concurrently at `730e065f` (revision `2026-10-20.8a38a79c72f0`), superseding the 352-family freeze for this new delivery. Details: `docs/build497-psp-managed-memory.md`.
- Validate exact collision reproduction, owned mappings under concurrent allocation, 32/64/76 MiB and failed-start cleanup, then real-core relaunches with a crowded address window. Reuse unchanged Dart/catalogue/other-core evidence. Deliver a new testable IPA; no public release and no external device-log request.
- Targeted core/session source `ab9361c29f7c9ab769c4263dd8b7427fc4f4c036`, run `39455712245`, passed: six PSP sessions and an intervening other-core session; native 18-cycle/iPhone SDK evidence reused by exact input identity. The IPA source is frozen before subsequent installer development; preserve that work on Claude and dispatch on Claude with an explicit immutable checkout of the delivery commit, without creating a release.

- Delivered: frozen source `e999a5fdc98a42f5d1995ca85fdfa04479d7f77a`, workflow commit `9319dc98176dcfd89dca3489569b1dbf23fd3ba4`, run `39458674086` (checks/native/cold succeeded). IPA 0.0.8 (497), 168,217,798 bytes, SHA-256 `3481881ea6f880595f736b7bebfed240def38887bae69f5972e9a420c81f58eb`. Receipt: `docs/evidence/psprelaunch497-delivery.json`. Final IPA independently matches the tested PSP payload, all 34 unchanged other cores and the exact 355-family catalogue. Temporary frozen-checkout driver restored after delivery; later candidates must use their own validated source. SideStore re-signing remains required; commercial-game and physical-iPhone GLES relaunch remain unconfirmed. No tag or public release. Do not reuse 497.

## Build 496 — verified IPA, PSP relaunch and frozen HD catalogue, 20 October 2026

- The maintainer requests stopping HD discovery, a recap, a PSP close/reopen fix and an IPA containing the latest catalogues. Build 495 already compiled successfully (`fee67e4d`, run `39384517903`); use 496 for this delivery, on `Claude`, no public release.
- Freeze catalogue `2026-10-20.d64e1ff29d79` at 352 installable families (437 profiles, 161 one-tap / 191 verified manual); preserve both manifests and all source/region/format exclusions. No further pack discovery in this cycle.
- PSP: the supplied app log reports `vm_remap failed (3)` and `Memory init failed` after closing a successful session. Fix ownership of unused memory-view pieces while a 32 MiB title runs, so its unused upper RAM view stays reserved for the next title. Never release or overwrite foreign mappings. No core rebuild, settings change, save deletion or retry workaround.
- Targeted source `4b12e244d9093564a6d57a30b72900030f0733e5`, run `39444272536`: old/new native regression, iPhone SDK compile, seven alternating PSP/other-core Simulator sessions and final catalogue checks. Evidence and limits: `docs/build496-psp-hd-catalogue.md`; gate `.github/diagnostics/psprelaunch496_delivery.py`. Reuse unchanged Build 495 validations; do not claim physical-device confirmation from Simulator results.
- Delivery source `b332bc2e59e4f44d4e820aa4879520a058bfd76b`, run `39445610738`: checks/native/cold Release succeeded. IPA 0.0.8 (496), 167,100,199 bytes, SHA-256 `466be74c72346f0a246f171dff0dd1b686a5bb0b229c254fdb93ed26ea9848ee`; exact receipt `docs/evidence/psprelaunch496-delivery.json`. The seven Simulator sessions used software rendering; commercial-game relaunch and iPhone OpenGLES remain unconfirmed. No public release.

Ces règles expriment les exigences du mainteneur du 18 septembre 2026 et s'appliquent à toute intervention sur ce dépôt.

## Une seule référence de travail

- Le mainteneur adopte la Build 419 comme nouvelle baseline le 8 octobre 2026 : référence source `9e0aca6a34034102b2e6aa083b1588b274b83e5f`, notamment pour le comportement de bibliothèque. Ne pas réutiliser le numéro 419 pour une nouvelle livraison. Aucun SHA d'IPA Build 419 n'est attesté ici. La Build 350 reste uniquement le donneur natif historiquement vérifié (`5e6dc00b35b7bb7847c24198d9f4b08ade8ed9a0`, run `36323843067`, IPA SHA-256 `e1017b96842ec970be3ed0cd981083ee945d069cf76e689a4ca3c81339299b46`). Ne pas modifier `main`, `backup` ou les références Git de baseline sans demande explicite.
- Travailler sur une seule version candidate clairement identifiée pendant le cycle de correction. Chaque modification crée naturellement un nouveau SHA : consigner ce SHA exact, ne pas mélanger des binaires ou des résultats de tests provenant de révisions différentes.
- Ne jamais réutiliser le nom d'un artefact pour faire passer une autre révision pour celle déjà testée. Associer version, SHA, entrées natives et résultats de validation.

## Branche de travail unique — dernière consigne du mainteneur du 9 octobre 2026

- À la demande du mainteneur, tous les assistants, y compris ChatGPT/Codex et Claude, travaillent désormais uniquement sur la branche `Claude` (ancienne `experimental`, renommée au commit `0bf904a`, source de la Build 423). Toutes les modifications, commits, CI et builds de travail se font sur cette branche. Cette consigne remplace la réservation précédente de cette branche à l'assistant Claude.
- Les branches de travail `ChatGPT` et `neoplay-v2-frames` ont été supprimées ; aucune branche NeoSwap n'était présente. Ne pas recréer de branches de travail ChatGPT, NeoSwap ou NeoPlay sans demande explicite du mainteneur. La règle existante exigeant une demande explicite pour modifier `main`, `backup` ou les références de baseline reste applicable.
- Les workflows déclenchés par push filtrent encore `experimental` : sur `Claude`, une build ou un contrôle se lance par `workflow_dispatch` avec `--ref Claude`.

## Décision du mainteneur — lancement RetroArch, 9 octobre 2026 après-midi

- La bibliothèque s'affiche avec la Build 423. Le défaut restant : un jeu lancé depuis NeoStation ouvre RetroArch sans le démarrer quand RetroArch était fermé.
- Exigence : l'utilisateur ne fait aucune manipulation (ni réglage RetroArch, ni raccourci) ; il lance simplement son jeu depuis NeoStation. La voie des commandes réseau de RetroArch, désactivées par défaut, est donc écartée. Les essais 424 et 425 ont été annulés avant toute IPA et retirés ; les sources produit restent celles de la 423.
- Démontré : `RetroArchSceneDelegate` ignore l'URL qui démarre RetroArch (de `630b36bd` à `master` `df16ef1`) ; iOS refuse un second lien envoyé dans le même passage au premier plan (run `37927541605`) ; commandes réseau et serveur MCP de RetroArch sont désactivés par défaut. Aucun changement de NeoStation seul ne démarre le jeu à froid sans réglage : le correctif appartient au récepteur RetroArch (`docs/upstream/retroarch-initial-scene-url.patch`).

## Décision du mainteneur — moteur libretro intégré, 9 octobre 2026 soir

- Le mainteneur demande toutes les phases de `docs/retroarch-integre-architecture.md` jusqu'à une IPA de test, avant toute validation des licences. Les licences des cœurs (dont snes9x, genesis_plus_gx, genesis_plus_gx_wide, fbneo et picodrive) seront revues après les tests sur iPhone.
- Le moteur est le pont `packages/libretro_internal_bridge` : hôte libretro natif, session plein écran, menu en jeu, sauvegardes, états, triches et RetroAchievements. Les cœurs officiels du buildbot sont empaquetés par `.github/workflows/libretro-cores.yml` (artefact `LibretroCores-<sha>`), copiés après `xcodebuild` et chargés seulement au lancement d'un jeu.
- Aucun des dix fichiers de bibliothèque verrouillés sur la Build 419 n'est modifié : les jeux importés vont dans `Documents/roms/<système>`, enregistré comme dossier de bibliothèque, et les ROM des dossiers déjà liés sont lues sur place.
- La route `retroarch://` reste pour les systèmes sans cœur intégré, pour les jeux connus seulement de la bibliothèque RetroArch et pour les jeux déjà réglés sur l’application RetroArch avant la Build 440 (« Application RetroArch (réglage précédent) ») ; ce choix n’est plus proposé pour les autres jeux.

## Décisions du mainteneur — bibliothèques, 10 octobre 2026

- Les jeux importés vont dans une bibliothèque existante de l’utilisateur, jamais dans une seconde bibliothèque créée à côté : choix parmi les dossiers enregistrés accessibles (direct s’il n’y en a qu’un) ; le dossier `roms` de NeoStation n’est utilisé que si aucune bibliothèque n’est enregistrée ; un jeu déjà présent (même nom, même taille) n’est pas recopié.
- Première ouverture iOS : NeoStation propose de créer un dossier par console dans `NeoStation › roms` (recommandé, sans autre action), de **déplacer** une bibliothèque existante dans ce dossier (l’autre dossier n’est ensuite plus utilisé), ou de lier un dossier sans le déplacer. Depuis la Build 440, les mêmes actions sont dans l’onglet Consoles de la barre principale (« Consoles intégrées » a quitté Réglages › Dossiers, revenu à la version revue `a5650b9b`).
- Autorisation explicite de modifier le démarrage (`lib/main.dart`, verrouillé sur la 419) : les dossiers enregistrés introuvables après le déplacement d’un conteneur iOS sont retrouvés au même endroit du conteneur actuel (blocs `LIBRARY_RELOCATION_*`, exception documentée dans `test/retroarch_baseline_scope_test.py`). Aucun fichier de jeu n’est déplacé, aucune ligne de jeu n’est réécrite. Voir `docs/library-folders-2026-10-10.md`.

## Décision du mainteneur — God of War III et NeoSwap, 10 octobre 2026 soir

- Le mainteneur refuse le retour au Core 434 : il faut corriger la Build 435. Les journaux de l’iPhone montrent God of War III figé environ 5 s après le démarrage dans 3 sessions sur 3 avec le Core 435 (images présentées, PPU/SPU/RSX inactifs, mémoire plate), alors que le Core 434 le fait tourner. La Build 436 désactive la compilation SPU différée (delta B, `deferred_compile_enabled = false`) et conserve les deltas A et C. Ne pas la réactiver sans preuve sur l’iPhone. Voir `docs/rpcs3-build436-gow3-black-screen.md`.
- NeoSwap est conservé (sa suppression avait été demandée à cause de l’écran noir, qui ne vient pas de lui). Pendant le jeu, la mémoire libre de tout l’iPhone (≈ 0,6 Go) limite les donneurs : ne pas présenter NeoSwap comme une source de RAM supplémentaire au-delà de la mémoire libre du système.
- À la demande du mainteneur, le même Core 436 importe cinq commits RSX/Vulkan de XITRIX v0.11 (`ios-port` `395636f5`) tels quels, avec leurs fixtures exécutées par `test/rpcs3_xitrix_v011_native_test.py`. Le correctif de blocage au démarrage `a5c5ed56` ne s’applique pas à notre base ; les commits audio, JIT, horloge invitée, cubemaps et occlusion restent à examiner. Toute modification du patch RPCS3 met aussi à jour `PATCH_SHA256` de `test/neo_swap_core_pin_test.py` avant la construction du Core. Voir `docs/rpcs3-xitrix-v011-build436.md`.

## Décisions du mainteneur — Build 440, 11 octobre 2026

- Les Builds 438 et 439 (NeoSwap : adaptation mémoire MeloNX pour RPCS3, puis comptage des dons, `2b1c0dea`) ont été livrées par une autre session ; la candidate de ce cycle est la Build 440, construite par-dessus la 439 à la demande du mainteneur. Décisions et répartition : `docs/build440-plan.md`.
- Dolphin Wii : bouton tactile « Secouer » (secousse Wiimote X/Y/Z par Touchscreen 132–134, 120 ms minimum, relâché à l’annulation, en pause, en arrière-plan et à la fermeture) et ligne « Secouer » du menu Commandes pour une manette. `DolphinSessionMenu.h`, `core/`, les nibs et `native/dolphin_motion/strings.json` restent inchangés ; GameCube inchangé. Voir `docs/dolphin-wii-shake-button.md`.
- RPCS3 : « Importer des licences RAP » dans le menu Importer de la bibliothèque PS3, vers `dev_hdd0/home/00000001/exdata/<CONTENT_ID>.rap` ; remplacement seulement après confirmation, avec copie dans `NeoStation/RPCS3/RapBackups`. Aucune tuile, aucun changement natif. Voir `docs/rpcs3-rap-import-build440.md`.
- Onglet Consoles dans la barre principale (après la première icône) ; les consoles ajoutées sont mémorisées hors des fichiers verrouillés. Voir `docs/consoles-tab-build440.md`.
- « Interface 120 Hz » (Réglages › Général, activée par défaut, appliquée au lancement suivant) : plugin `packages/ui_refresh_rate` qui borne seulement `+[FlutterDisplayLinkManager displayRefreshRate]` de l’interface Flutter. Les moteurs d’émulation ne sont pas touchés. Ce point d’accroche privé est à revalider après toute mise à jour de Flutter. Voir `docs/ui-120hz-build440.md`.
- Vérificateur de BIOS (Réglages › Outils) en lecture seule : il n’écrit que son cache. La règle de lancement PS1 ne change pas, et un BIOS optionnel manquant ne bloque jamais un lancement. Voir `docs/libretro-bios-checker.md`.
- « RetroArch embarqué » dans Paramètres du système ; le choix par jeu de l’application RetroArch n’est plus proposé, sauf pour les jeux déjà réglés ainsi. Voir `docs/retroarch-settings-build440.md`.
- Lecteurs de la Bibliothèque : un retour en un geste, toujours accessible (bouton flottant quand les barres sont masquées). Voir `docs/library-reader-back-button-build440.md`.
- Sources de la Bibliothèque : chaque source installée a un fichier dans Fichiers › NeoStation › Library › Sources, et supprimer ce fichier retire la source. Consigne du mainteneur : les gens doivent trouver ce dossier par eux-mêmes. Ne jamais ajouter dans l’app de bouton, lien, chemin, aide ou message vers ce dossier, ni le mentionner dans le README. Voir `docs/library-source-files-build440.md`.

## Décision du mainteneur — Build 441, 11 octobre 2026

- Après l'audit NeoSwap, le mainteneur demande l'implémentation et la production du Build 441 sur `Claude`, limitée à RPCS3 et NeoSwap, en conservant les ajouts 440. Les demandes antérieures « audit seulement » et « pas d'IPA » sont remplacées par cette autorisation explicite. Voir `docs/neoswap-build441.md`.
- Ouvrir les nouvelles allocations invitées pendant le jeu via un stock préparé, partager le budget selon les demandes, et distinguer préparé/attribué/footprint. Aucun transfert des objets FILE déjà publiés ni réactivation de la compilation SPU différée.

## Décisions du mainteneur — Build 442, 11 octobre 2026 soir

- Demande du 11 octobre 2026 (soir) : secousse du téléphone (Wii) plus sensible et régulière avec un réglage simple, stabilité/saccades de Dolphin, import/export des sauvegardes RPCS3 réparés, affichage AirPlay/Apple TV sans bandes. Candidate : Build 442, construite par-dessus la 441 (NeoSwap, autre session). Décisions et vérifications : `docs/build442-plan.md`.
- Secousse : détecteur réécrit (`DolphinShakeDetector.swift`) — confirmation sur deux échantillons ou un échantillon fort, maintien tant que le téléphone bouge, relâchement au calme (≥ 120 ms), nouveau geste 80 ms après ; trois niveaux (`low` = comportement 440, `medium` par défaut, `high`), préférence `NeoStation.Dolphin.PhoneShake.Sensitivity` partagée par le menu Commandes en jeu, l’onglet Émulateurs du système Wii (`DolphinWiiMotionPanel`) et le canal `phoneShakeSettings`. Les entrées 132–134, l’arbitre et le routage de la 440 ne changent pas. Voir `docs/dolphin-shake-sensitivity-build442.md`.
- Saccades : le cœur Dolphin reste verrouillé (identité 350) ; changements hôte seulement — fréquence d’affichage 60 Hz par défaut (120 Hz et Automatique au choix, effet immédiat), sous-échantillonnage 10 Hz des temps d’image dans la trace et la surcouche (pic, lents ≥ 25 ms, très lents ≥ 50 ms, mémoire, thermique). Aucune baisse de résolution ni hack automatique. Les gains ne sont pas mesurés sur iPhone : procédure de comparaison dans `docs/dolphin-smoothness-build442.md`.
- Écran externe : `DolphinExternalDisplay` déplace la vue Metal de Dolphin sur l’écran AirPlay/adaptateur (fenêtre dédiée), commandes sur l’iPhone ; modes Désactivé / Adapter (défaut, image entière, seules les bandes latérales propres à l’iPhone sont coupées) / Remplir (zoom 4:3 annoncé, haut et bas coupés). Aucun redimensionnement de la surface Dolphin. Réglage dans Affichage et fluidité, préférence `NeoStation.Dolphin.ExternalDisplay.Mode`. Les autres moteurs ne sont pas concernés par cette build. Voir `docs/dolphin-external-display-build442.md`.
- Sauvegardes RPCS3 (savedata, pas les savestates) : export en archive ZIP dans Fichiers › NeoStation › RPCS3 › Export › Game Saves (partage proposé), import depuis Import › Game Saves (dossier ou ZIP, dossier parent supplémentaire accepté), un ZIP ou un dossier choisi ; validation (PARAM.SFO, noms, traversée, taille), confirmation avant remplacement avec copie dans `NeoStation/RPCS3/SaveBackups`, refus quand un jeu PS3 tourne. Plus aucune consommation automatique du dossier Import au démarrage ; `synchronizeFilesWorkspace()` ne fait que créer les dossiers (`lib/main.dart` verrouillé, non modifié). Chemins réels résolus à l’appel (`Data`, `vfs.yml`, utilisateur `00000001` du Core iOS). Cœur, pont et natif RPCS3 inchangés. Voir `docs/rpcs3-save-exchange-build442.md`.

## Décisions du mainteneur — Build 444, 11 octobre 2026 nuit

- La Build 443 a été livrée par une autre session (couvertures 3D de la Bibliothèque, source `79a5920a`). Le cycle RPCS3/LLVM/NeoSwap demandé le 11 octobre au soir est la Build 444 (code `7ec94a8c` + correctif `dcf0df67`, patch canonique `f19ec0f8…c7cfb7`, Core run `38178247609` épinglé). Depuis cette build, la clé publique à laquelle l'artefact chiffré est adressé se choisit par l'entrée `recipient` du workflow de livraison (défaut : `build-utils/delivery-443-recipient.pem` de l'autre session) ; chaque session passe la clé dont elle détient la clé privée, sans modifier le workflow. Audit, explication de l'écart God of War III / BladeStorm, compteurs à comparer et captures nécessaires : `docs/rpcs3-neoswap-llvm-build444-audit.md`. Aucun journal d'iPhone n'était disponible : l'écart est expliqué par les sources (admission bornée par la mémoire système libre que le jeu consomme lui-même ; chemin de jeu 441 limité au stock préparé ≤ 16 Mio avec repli FILE définitif), pas mesuré.
- NeoSwap : nouvelle ABI optionnelle `NeoSwapDirectRelayAPI` (`try_create`, non bloquante, admission de `create()` plus l'allocation budgétée `direct_guest_allowance_bytes` renouvelée à chaque passage) pour les manques de stock et les tailles > 16 Mio pendant le jeu ; réapprovisionnement d'une classe de taille jusqu'à sa demande enregistrée (quatre) dans les bornes existantes (8 objets, 32 Mio par passage) ; réveil anticipé du passage de maintenance sur manque (au plus un par 50 ms). Aucun objet FILE ne migre ; la pression reste fail-closed. Les règles 441 (stock ≤ 64 Mio, 128 objets) ne sont pas relevées sans capture qui le justifie.
- Core : compteurs `JITPROF` par phase LLVM (traduction, passes, vérification, génération, cache, chargement, finalisation, symboles PPU ; construction, passes, génération SPU ; marge mémoire minimale) ; nom d'objet PPU `v9-neostation-…-<identité>` (version LLVM, empreinte CMake des sources du traducteur/moteur, attributs CPU) : une recompilation unique à la première ouverture après ce Core ; option `emulator.ppu_llvm_ir_passes` (EarlyCSE PPU sur ARM64, désactivée par défaut, hachée dans la clé du cache) à comparer sur l'iPhone avant toute activation par défaut. La compilation SPU différée reste désactivée. Le catalogue de réglages du Core reste en anglais, comme ses autres entrées.
- Livraison 444 vérifiée : source `a221ae0c66fedb1f899d16eaadaf3877a14f8349`, run `38182831110`, Core `dcf0df67` run `38178247609`, IPA SHA-256 `a06c4d460fb6531e2f16f2b06998489d4520cf9a9789694b0ad1212090ebeade` (207 536 584 octets), aucune validation iPhone. Voir `docs/build444-delivery.md`. Ne pas réutiliser le numéro 444.
- Comparaison des deux titres : `tools/compare_rpcs3_neoswap_builds.py --mode cross-title` (même IPA, même Core, mêmes réglages, même appareil) ; lignes `neoswap_guest_sample_ext` et `JITPROF`, objet `guestDirectCreation`. Un « Donated » plus élevé n'est pas un gain : seuls les temps d'image, les compilations en jeu et la couverture des demandes invitées (octets) le sont.

## Décision du mainteneur — Build 445, 12 octobre 2026

- La Build 445 se construit par-dessus la Build 444 livrée (`a221ae0c`, run `38182831110`) et conserve toutes ses améliorations et corrections. Le mainteneur ne demande aucun correctif pour cette build. Son produit est identique à la 444 : aucun changement sous `lib/`, `packages/`, `native/`, `assets/` ni dans `pubspec.*`.
- Ajouts sans effet sur le produit :
  - l'artefact est chiffré pour `build-utils/delivery-445-recipient.pem`, clé détenue par la session tactile/skins et passée par l'entrée `recipient` ;
  - `test/libretro_skin_catalogs_test.dart` est exécuté par le contrôle de livraison.
- Livraison 445 vérifiée : source `c0e33717a64f6b66280d6bef3aae6c4a8bcacd55`, run `38186199603`, IPA SHA-256 `c7ab05534373af4e27ec63f01341705b24f6bc793b9fbddfb16e3c4bf57db598` (207 536 562 octets), aucune validation iPhone. Plan, vérifications et remise : `docs/build445-plan.md`. Ne pas réutiliser le numéro 445.

## Décision du mainteneur — Build 446, 12 octobre 2026

- Constat du mainteneur sur la Build 445 installée (vidéo) : aucun catalogue de skins ne se charge, recherche grisée, message « The catalog could not be loaded ». Demande : « apporte un correctif et produit le build 446 ».
- Cause démontrée : `LibretroSkinCatalogs.normalizeDownloadURL` décodait deux fois les segments d'URL ; deux liens DeltaStyles réels du catalogue Provenance (« pokÃ©mon pinball GBA », « DK control + real dpad Â ») levaient une exception hors de tout `try` dans `load()`, ce qui faisait échouer tous les catalogues de toutes les consoles (régression de `6639e7a3`, 444/445). Correctif : plus de second décodage, aucune exception possible, une entrée Provenance ou une carte Delta Skins inutilisable est ignorée sans bloquer les autres. Tests de non-régression avec ces liens réels. Aucun libellé, natif ni écran modifié. Voir `docs/build446-plan.md`.
- Règle : une entrée de catalogue externe, quelle qu'elle soit, ne doit jamais empêcher le chargement des autres entrées ni des autres sources.
- Livraison 446 vérifiée : source `8ceeb055c67688442b637a5a0f48dfbcd4f8ae9a`, run `38189277921`, IPA SHA-256 `60e55240bd8ec85bf2efdeca3b960dcdbafbf0547bedec8a7719f095223ad905` (207 536 632 octets), aucune validation iPhone. Ne pas réutiliser le numéro 446.

## Décisions du mainteneur — Grande mise à jour, 12 octobre 2026

- Audit complet avant toute modification, exigé par le mainteneur et livré dans `docs/grande-mise-a-jour-audit-2026-10-12.md` (six audits, six vérifications contradictoires, révision `165c0201` relue sur `fa3aba11`). Les cinq chantiers demandés : AirPlay universel, Nintendo 3DS (langue, région, données système), livres et mangas 3D, musique d'ambiance, analyse et nettoyage du stockage.
- Réponses du mainteneur du 12 octobre 2026 : la version iOS de l'iPhone de test n'est pas connue — le chantier AirPlay couvre les deux régimes de scène externe (connexion automatique avant iOS 27, accessoire de scène à partir d'iOS 27 appelé par sélecteurs, la CI compilant avec Xcode 26.3) et consigne la version à la première validation ; les cœurs libretro sont ré-épinglés immédiatement (l'artefact `LibretroCores-48635465…` du run `37945318237` expire le 23 octobre 2026, rétention 14 jours, et bloquerait toute livraison) ; le chantier musique « Fairy Lights » est **reporté** à un cycle ultérieur (fichier et licence inaccessibles depuis le conteneur de travail) ; **une seule IPA** en fin de cycle, construite par-dessus la Build 446.
- Les autres décisions suivent les recommandations du § 11 du document d'audit, sauf avis contraire du mainteneur : préférences en SharedPreferences/NSUserDefaults/JSON (aucune colonne SQLite), filtres de branche des workflows inchangés (dispatch `--ref Claude`), import 3DS avec titres NAND et clés en option avancée, données uniques de console exclues par défaut, suppression des métadonnées orphelines seulement explicite, prévisualisée et transactionnelle, `RPCS3/Cache` en niveau 2 avec avertissement, mesure fine du stockage par `dart:ffi` avec repli tailles logiques, aucune mention du dossier `Library/Sources`.
- Rappels issus de la vérification : `FilePicker.clearTemporaryFiles()` (import de sauvegardes RPCS3) vide toute la racine `tmp/` de l'app — à restreindre dans le chantier de maintenance légère, jamais à réutiliser comme primitive de nettoyage ; le modèle Old/New 3DS n'est pas appliqué par « Redémarrer le jeu » (nouvelle session) ; `_finalize()` de `GameLaunchManager` peut s'exécuter pendant que RetroArch/MeloNX est au premier plan (route `ios_direct_launch`, ≈ 4 s).

## Build 447 — grande mise à jour livrée, 12 octobre 2026

- Livraison 447 (unique IPA du cycle, par-dessus la 446) : source `af3cec8af0a373641abbf0b11a286bf2c7d5cb03`, run `38286881882` (périmètre `full`, `checks`, `native` et `cold` réussis), artefact `NeoStation-Build-447-af3cec8a…-cold` (`11764636973`, 208 284 573 octets, archive SHA-256 `bec0ee1daa0fe829d65fd2949eba71dc9f8a452342eec9bd223891f4fee8c9da`, conservé jusqu'au 26 octobre 2026), chiffré pour `build-utils/delivery-424-recipient.pem` (PC du mainteneur hors ligne ; la clé privée 445 n'existe que dans le conteneur temporaire de la session). IPA SHA-256 `b4e9d6a75caf1c4bc7b75f4965a5377a9c163bb6f1af6a211ca41b3133adcdb3` (208 051 121 octets), égal à `SHA256SUMS` et à `signed-payload-identity.json`, relevé après déchiffrement sur le PC du mainteneur ; `08d53732…`, imprimé avant le scellement SideStore qui recrée l'IPA, n'est pas celui de l'IPA livrée. Aucune validation iPhone. Plan, vérifications, emplacements dans l'app et protocole iPhone : `docs/build447-plan.md`. Ne pas réutiliser le numéro 447. Musique « Fairy Lights » toujours reportée.
- Lecteur de la Bibliothèque : `Library/reading-state.json` garde exactement la disposition de la Build 446 ; toute donnée ajoutée après la 446 (marque-pages, réglages par livre, nouveaux réglages généraux) va dans `Library/reading-state-extra.json`, et les deux fichiers conservent les clés qu'ils ne connaissent pas : un retour à une build antérieure ne doit jamais effacer de données. Le sens de lecture global ne s'applique pas aux PDF.
- Nettoyage du stockage : jamais au démarrage ni en arrière-plan ; doublons supprimables seulement à empreintes SHA-256 identiques ; sauvegardes faites par NeoStation (`RPCS3/SaveBackups`, `RPCS3/RapBackups`, copies de la base, sauvegardes 3DS) en classe « jamais » ; plan refusé pendant un jeu, un import (`StorageImportActivity`, à utiliser autour de tout nouvel import après un choix de fichiers) ou une analyse de la bibliothèque ; métadonnées supprimées seulement hors de toute autre transaction. Voir `docs/storage-audit-cleanup.md` §§ 9.6–9.7.
- Livraison : dans l'étape Dart du job `checks`, la ligne `flutter test test/dolphin_shake_locale_test.dart …` (tests AirPlay) doit rester la dernière ligne `flutter test` (`test/external_display_host_plist_test.py`) ; les tests du stockage passent par `flutter test test/storage_*_test.dart`, ceux des livres par `test/library_*_test.dart` et `test/library_books_3d_contract_test.py`.

## Build 448 — skins, consoles, Frontend uniquement, musique, fichiers 3DS, 12 octobre 2026

- Demande du mainteneur du 12 octobre 2026 : catalogue de skins adaptatif et tactile fiable (appuis, maintiens, relâchements, diagonales, multitouch ; aucun halo sans commande), onglet Consoles étendu à toutes les consoles (visibilité et moteur intégré distincts), réglage « Utiliser les émulateurs intégrés » (Frontend uniquement, RetroArch en priorité), musique d'ambiance « Once Upon a Time (loop) » de TAD (CC0, fichier fourni par le mainteneur) en boucle exacte, puis import réel des fichiers système 3DS. Plan, emplacements et vérifications : `docs/build448-plan.md`.
- Règles posées : un réglage global ne réécrit jamais les réglages par console (`EmbeddedEnginePolicy`, préférences séparées) ; masquer une console passe par le même réglage que Paramètres › Systèmes ; « Rétablir par défaut » ne retire du menu principal que les consoles ajoutées par l'onglet et sans jeu ; un moteur désactivé n'ouvre jamais un autre émulateur que RetroArch, et seulement quand RetroArch peut lancer la console ; une piste en boucle se reconstruit avec `tools/ambient_music/` et se prouve par `test/ambient_music_loop_test.py` (rendu SoLoud réel, exact à l'échantillon) ; le cœur 3DS refuse tout NCCH chiffré, aucun texte ne doit présenter un fichier de clés comme remède.
- Livraison 448 vérifiée : source `36567551838130bb34abe48f93177ac3cef15f1c` (arbre identique à `aab282e7`), run `38317793450`, artefact `11777099283` (210 114 461 octets, archive SHA-256 `b855919bbe8064a2a37e27f7c77b7474cf361cf4386eeadcf217a35480c45cea`), chiffré pour `build-utils/delivery-424-recipient.pem` ; SHA-256 de l'IPA à relever après déchiffrement. Le run `38315400256` (même arbre, clé de session 448) n'est pas remis : le conteneur de la session ne peut pas télécharger les artefacts (politique de sortie) ; ne pas contourner cette politique par un workflow. Aucune validation iPhone. Ne pas réutiliser le numéro 448.

## Build 449 — recopie AirPlay, version 0.0.7, import 3DS depuis iCloud Drive, 13 octobre 2026

- Demandes du mainteneur : l'Apple TV doit recopier exactement l'interface NeoStation de l'iPhone (menus, bibliothèque, jaquettes, jeux) au lieu du logo de la console ; « baser la future compilation sur la 0.0.7 » ; « je ne peux toujours pas importer un dossier Nand-zip pour la 3DS ». Plan, cause et vérifications : `docs/build449-plan.md` ; cause AirPlay : `docs/external-display-universal.md` § 10.
- Règles posées : hors jeu, la fenêtre de la scène externe est retirée de sa scène (`windowScene = nil`, voie documentée par Apple) et iOS recopie l'iPhone ; seul un jeu reprend la scène ; le second moteur Flutter (`externalDisplayMain`) n'est plus jamais affiché. La version vient uniquement de `pubspec.yaml` (`stamp_host_version.py`, portes d'IPA) : ne plus écrire de version en dur dans les validateurs. Un fichier système 3DS encore dans iCloud Drive est signalé `notDownloaded`, jamais lu.
- Livraison 449 : source `ff2a491c83b9eb7477b0e38e6f4a83e4a20680d1`, run `38326750311` (périmètre `full`, `checks`, `native` et `cold` réussis), artefact `11781772870` (210 115 997 octets, archive SHA-256 `68abff9c0db715ee6f7b56116d50196ffc42ec084164450007e7538dc1675683`, conservé jusqu'au 27 octobre 2026), chiffré pour `build-utils/delivery-424-recipient.pem` ; SHA-256 de l'IPA à relever après déchiffrement. Aucune validation sur iPhone ni sur Apple TV. Ne pas réutiliser le numéro 449.

## Build 450 — système de shaders (moteur libretro, Dolphin), 13 octobre 2026

- Demande du mainteneur : système avancé de shaders depuis le menu en jeu (parcourir, télécharger, installer, prévisualiser, appliquer, régler) pour le moteur libretro intégré, Dolphin et les moteurs futurs ; « ne pas déclarer un shader compatible uniquement parce que son fichier est reconnu » ; ne pas empaqueter ni distribuer les shaders Mattias CRT tant que l'autorisation de redistribution n'est pas établie. Architecture et vérifications : `docs/shaders-system.md` ; étude Mattias : `docs/shaders-mattias-crt.md` ; plan : `docs/build450-plan.md`.
- Règles posées : un préréglage slang n'est offert « Vérifié » que s'il a été compilé pour iPhone, exécuté par le code de l'application sur un GPU Metal et trouvé visiblement différent en CI (`shader-kit-checks`, verdicts transcrits dans `tools/shaders/slang-metal-results.json`) ; ses fichiers ne sont téléchargés qu'à la demande, au commit épinglé, vérifiés par taille et SHA-256. Les effets Dolphin officiels sont ceux du dossier Sys livré (catalogue épinglé, verdicts dans `tools/shaders/dolphin-metal-results.json`) ; un effet sans changement visible sur iPhone n'est pas proposé (AutoHDR, PerceptualHDR : DolphiniOS n'a pas de sortie HDR sous `IPHONEOS`). Un effet Dolphin s'applique au lancement suivant (le cœur conservé n'a pas d'appel pour le changer en jeu et réécrit ses réglages à l'arrêt) : ne pas écrire `GFX.ini` pendant une partie ; le changement en direct demande une ABI du cœur à décider par le mainteneur. Les fichiers Mattias ne sont ni dans le dépôt ni dans l'IPA ; la CI les récupère pour les vérifier seulement.
- Sonde simulateur : l'échec de `ppsspp-crowded` est une limitation connue de la sonde simulateur — aucune régression de lancement démontrée (décision permanente du 13 octobre 2026 ci-dessous). Relevé ajouté à la sonde, diagnostic seulement : `docs/build450-plan.md`.
- Version 0.0.7+450. Livraison 450 : source `e7f223365a12327c62bfc154b0bddd789d2a0131`, run `38339349667` (périmètre `full`, `checks`, `native` et `cold` réussis), artefact `11786148903` (212 085 661 octets, archive SHA-256 `ba07914261d9ba8066939c3f8cf406147f6274e6ac61d8020387edbca00d061a`, conservé jusqu'au 27 octobre 2026), chiffré pour `build-utils/delivery-424-recipient.pem` ; IPA validée avant scellement `418444d95bb54fef381fc15e34b8cc0ce8f25fd7c2d1cdd676022a2fe3d8e309`, SHA-256 de l'IPA scellée à relever après déchiffrement. Aucune validation sur iPhone ni sur Apple TV. Ne pas réutiliser le numéro 450.

## Build 451 — import 3DS des titres chiffrés par Azahar pour leur console, 13 octobre 2026

- Demande du mainteneur : « je ne peux toujours pas importer un dossier Nand-zip pour la 3DS ». Le ZIP fourni (`nand.zip`) a été examiné en lecture seule sur son PC, jamais copié ni versionné. Cause démontrée : c'est le dossier `nand` d'Azahar, dont les titres système sont chiffrés pour la console dans la forme « Legacy » que le cœur lit encore (AES-CTR sur tout le fichier, sans en-tête `AZCR`, clé dérivée de l'OTP) ; l'import ne connaissait que `AZCR` et refusait ces titres. Plan : `docs/build451-plan.md` ; détail et sources amont : `docs/libretro-3ds-system-settings.md` § 9.
- Règles posées :
  - un contenu sans en-tête lisible n'est gardé que si son empreinte sans clé (flux sur les champs que tout NCCH porte en clair) est confirmée par un contenu d'un autre titre ou d'une autre taille, avec une seule empreinte confirmée dans l'import ;
  - un tel titre ne s'installe qu'avec `sysdata/otp.bin`, déjà en place ou importé avec les données de console ;
  - aucun octet de flux n'est conservé ni journalisé ;
  - un NCCH chiffré reste refusé, et aucun texte ne présente un fichier de clés comme remède : `otp.bin` est une donnée de console, nommée parce que le cœur en dérive réellement la clé de ces titres.
- Livraison 451 : source `c65efd42e09da3d1a1f27e59644a4ad2c7875902`, run `38346881629` (périmètre `full`, `checks`, `native` et `cold` réussis), artefact `11789424542` (212 092 317 octets, archive SHA-256 `2599f3df9d722e51c9668cea504ff13f27d1085483e948afef75a13da676b1fb`, conservé jusqu'au 27 octobre 2026), chiffré pour `build-utils/delivery-424-recipient.pem`. IPA `NeoStation-Build451-c65efd42…-cold.ipa`, 211 839 266 octets, SHA-256 `56599cc412cc6f13e766997eec8fa5b1b359942b64b2ee8606a617a1091722b2`, égal à `SHA256SUMS` et à `signed-payload-identity.json` ; version 0.0.7 (451). Déchiffrée sur le PC du mainteneur à sa demande ; copie `C:\Users\Coren\Downloads\NeoStation-Build451-c65efd4.ipa`. Aucune validation sur iPhone. Ne pas réutiliser le numéro 451.

## Build 452 — import du BIOS 3DS depuis le menu de la console, 13 octobre 2026

- Demande du mainteneur, avec vidéo : « analyse la vidéo et lis le message d'erreur pour le bios de la 3ds, j'ai tout essayé ! il n'importe aucun de mes fichiers ». Constat : il passait par « Copier les sauvegardes et BIOS de RetroArch » (dossier Azahar, `nand`, `sysdata`), qui ne lit que `saves`/`states`/`system` d'une installation RetroArch, d'où « Aucune sauvegarde, aucun état ni fichier système RetroArch trouvé dans le dossier choisi » ; l'import 3DS n'était proposé que dans Consoles › Nintendo 3DS › Réglages système. Plan : `docs/build452-plan.md` ; détail : `docs/libretro-3ds-system-settings.md` § 10.
- Règles posées : le menu d'import de la console 3DS propose « BIOS et fichiers système 3DS », qui ouvre la page Nintendo 3DS avec son assistant lancé ; la copie RetroArch reconnaît un dossier Azahar, Citra ou Lime3DS (`nand` ou `sysdata` à deux niveaux au plus) et, sans rien à copier, l'explique et ouvre l'import 3DS au lieu de dire « rien trouvé » (bibliothèque et vérificateur de BIOS). L'import 3DS lui-même ne change pas.
- Livraison 452 : source `1594e78cdb2170c5e07b61af1eacc6733d61bd87`, run `38350634341` (périmètre `full`, `checks`, `native` et `cold` réussis), artefact `11791821126` (212 106 141 octets, archive SHA-256 `85a91eb1f5b7de4c5a1c945ad5043c520de06fcb934894f719168fe6d4efa0da`, conservé jusqu'au 27 octobre 2026), chiffré pour `build-utils/delivery-424-recipient.pem`. IPA `NeoStation-Build452-1594e78c…-cold.ipa`, 211 852 843 octets, SHA-256 `d76463d124d2f9faecd0215b480b41abc4b6a6afb67f6c5685ca82489473fd21`, égal à `SHA256SUMS` et à `signed-payload-identity.json` ; version 0.0.7 (452). Déchiffrée sur le PC du mainteneur ; copie `C:\Users\Coren\Downloads\NeoStation-Build452-1594e78.ipa`. Aucune validation sur iPhone. Ne pas réutiliser le numéro 452.

## Décision du mainteneur — sonde simulateur PPSSPP, 13 octobre 2026

- Le lancement PSP est corrigé : `d4de3c76` (réservation de la fenêtre mémoire de PPSSPP au lancement) et `54147b97` (arène placée sous la plage des vues de RAM) sont toujours présents. Ne plus le présenter comme un problème restant à résoudre.
- Classement permanent de l'échec du scénario automatisé `ppsspp-crowded` (et `ppsspp-crowded-prx`) : **« limitation connue de la sonde simulateur — aucune régression de lancement démontrée »** ; statut : limitation de la sonde connue et hors périmètre du chantier actuel. Le scénario exige que PPSSPP utilise précisément l'adresse réservée, alors que sa préparation ne garantit pas que les autres adresses soient inutilisables : l'échec de cette assertion, quand le contenu PSP démarre et se ferme correctement, ne démontre pas une régression du lancement PSP. Détail : `docs/build450-plan.md`, `docs/libretro-touch-skins-audit.md`.
- Ne pas répéter ce point dans les résumés de livraison, les notes de mise à jour ou les propositions de correction sans élément nouveau. Conserver les tests et leurs résultats : ne pas les supprimer, ne pas les désactiver, ne pas affaiblir leurs vérifications pour obtenir du vert. Dans un rapport de CI, indiquer honnêtement l'échec connu, sans le présenter comme une panne de l'application.
- Ne rouvrir le sujet que sur un élément nouveau et vérifiable : échec réel du démarrage, disparition ou dysfonctionnement démontré de la réservation, fuite mémoire confirmée, ou autre anomalie distincte. La simple répétition du même échec d'assertion ne justifie pas de relancer ce chantier.

## Précision du mainteneur — 9 octobre 2026, 13 h

- L'état fonctionnel confirmé est NeoStation Build 422 : bibliothèque visible et lancement RetroArch lorsque l'application externe reste en arrière-plan. Conserver ces sources de lancement/synchronisation ; ne pas prendre le récepteur autonome 781 pour une mise à jour NeoStation.
- Aucun plafond arbitraire du nombre de dossiers de ROM n'est souhaité. La liaison doit enregistrer chaque dossier demandé et permettre son scan. La limite silencieuse de cinq racines a été retrouvée alors que la base fournie en contient sept ; le correctif 423 retire uniquement ce plafond et empêche d'afficher un succès d'enregistrement après un échec de persistance. Le scanner lui-même, les moteurs, la base et les métadonnées de jeux ne font l'objet d'aucune migration.

## Corriger avant de compiler

- Le retour demandé au comportement de bibliothèque Build 419 est prioritaire : aucune nouvelle migration, réparation automatique, remise à zéro ou dissimulation de doublons. Une réparation de données persistées se documente séparément et ne s'applique pas à cette livraison. Corriger uniquement la liaison RetroArch établie et distinguer demande envoyée, application ouverte et jeu effectivement démarré.
- Ne plus superposer les correctifs. Les sources canoniques suivies par Git doivent contenir directement les corrections. La CI ne doit pas rejouer une succession de patches historiques VPN, RPCS3 ou Dolphin pour fabriquer des sources différentes de celles examinées.
- La migration des anciennes couches doit être une opération ponctuelle de mise à plat des sources, revue et commitée, jamais une nouvelle étape cachée exécutée à chaque compilation.
- Ne pas reconstruire ni modifier des cœurs, helpers JIT, scripts de débogage ou réglages d'émulation sans lien établi avec le défaut traité. Conserver et vérifier leurs identités lorsqu'ils doivent rester inchangés.

## Empêcher le retour des régressions

- Consigne explicite du 8 octobre 2026 : ne pas répéter pendant la compilation les tests déjà réussis lorsque leurs entrées sont inchangées. Réutiliser les résultats en conservant SHA testé, run, outils, dépendances et comparaison des entrées ; ne jamais les présenter comme exécutés à nouveau. Relancer les tests concernés par une modification, y compris les dépendances transitives. Sans preuve de succès et d'identité des entrées, la réutilisation est refusée.
- Réutiliser les moteurs, helpers et artefacts validés par leur identité ; ne reconstruire que les éléments modifiés ou les interfaces de compilation réellement manquantes. Mesurer les temps observés et les restaurations/sauvegardes de cache ; préserver Release et les contrôles de signature. L'installation habituelle du mainteneur est SideStore, confirmée le 8 octobre 2026 : une signature ad hoc de préparation ne remplace pas la signature Apple et le provisioning appliqués par SideStore.

- Chaque défaut corrigé doit avoir une vérification de non-régression appropriée. Préférer des tests de comportement aux seules recherches de chaînes dans le code.
- Couvrir notamment : premier lancement et relancement ; alternance DolphiniOS/RPCS3 ; échec de route puis récupération ; absence de double lancement ; expiration et callbacks tardifs ; retour au premier plan ; fermeture de la seule fenêtre appartenant au lancement ; conservation de l'erreur technique réelle.
- Séparer strictement disponibilité TCP, authentification RemotePairing, état du helper, attachement au PID attendu, préparation mémoire et réussite effective du JIT. Aucun de ces états ne doit être déduit de la seule présence d'une route ou d'un succès antérieur.
- Bloquer la compilation candidate lorsque l'analyse ou les tests obligatoires échouent. Ne pas supprimer un test ni affaiblir une assertion pour obtenir artificiellement un résultat vert ; remplacer un contrat retiré par le test du nouveau comportement et expliquer ce changement.
- Ne pas altérer les sauvegardes, bibliothèques, firmware, caches ou fichiers de pairing comme moyen de contourner un défaut de cycle de vie.

## Validation et communication

- Distinguer les défauts confirmés dans les sources, les hypothèses, les tests exécutés, les tests ignorés et la validation sur iPhone.
- Une compilation réussie ou un test simulé ne démontre pas la stabilité sur iOS. Ne jamais annoncer un correctif « définitif », « stable » ou empêchant toute récidive sans preuve correspondante.
- Garder le même cycle de correction jusqu'à validation, avec un historique clair des résultats et des éventuels blocages. Ne pas envoyer une nouvelle IPA seulement pour tenter une autre hypothèse non vérifiée.
- Observation du 9 octobre 2026 : le mainteneur confirme la Build 422 installée sans doublons, mais des relancements RetroArch intermittents. Les vidéos montrent des jeux effectivement démarrés, et aussi une première demande à froid perdue. Des échecs à chaud sont également signalés : ne pas les attribuer automatiquement au défaut de scène froide. Voir `docs/retroarch-relaunch-2026-10-09.md` ; le patch proposé concerne le récepteur RetroArch et n'est pas appliqué au TestFlight installé.
- Comparaison supplémentaire 411–412–419 : les fichiers de liaison RetroArch, dépendances et générateurs de schémas iOS examinés ont les mêmes blobs Git. Le scanner est également identique à la livraison 422. La source publique RetroArch ajoute les scènes dans `630b36bd774c873b73bfaa59183822837dbc9aac` en omettant les URL initiales ; la classe demeure identique au SHA public `a7363feb909391c3217b91c30e81547e8208d6d5`. Cela établit un défaut public, pas l'identité du TestFlight 780 installé. Ne pas présenter une nouvelle URL, une fixture, ou une IPA NeoStation inchangée comme l'installation d'un correctif du récepteur tiers. Voir `docs/retroarch-411-412-comparison.md`.
- Candidat du récepteur réellement produit le 9 octobre 2026 : RetroArch privé 781, source de construction `560472630fb1064134d6feca27d6f7cb4e0efb64`, run `37918345079`, IPA SHA-256 `6d3b5dc86a39ef48398df83d56cddced0e01072b6f7a58d5c7bb3acbc877da11`, 190 470 031 octets, 126 cœurs précompilés, 129 signatures ad hoc vérifiées. Il s'utilise après re-signature Apple par SideStore ; il ne modifie pas le TestFlight installé et n'a pas été testé sur l'iPhone. Ne pas installer en supposant un routage déterministe entre deux applications enregistrant `retroarch://`, ni supprimer des données pour essayer le candidat. La préparation du conteneur et le choix d'installation doivent rester explicites. Voir `docs/retroarch-receiver-sidestore.md` pour les cœurs exclus/indisponibles et les durées observées. Les sources NeoStation restent identiques à la livraison 422, avec la bibliothèque de baseline 419.

## Traductions obligatoires — consigne du mainteneur du 23 septembre 2026

- Toute option, commande, description, notification, aide, erreur ou libellé d’accessibilité ajouté ou modifié dans NeoStation doit être traduit dans les douze langues prises en charge : `en`, `es`, `ru`, `zh`, `zh_Hant`, `pt`, `fr`, `de`, `it`, `id`, `ja`, `ko`.
- Utiliser les catalogues de traduction du projet. Ne pas ajouter de branche français/anglais ni afficher directement un message natif en anglais comme message utilisateur. Les noms de produits, identifiants, chemins et diagnostics techniques bruts restent inchangés, séparés de l’explication traduite.
- Pour chaque surface modifiée, vérifier automatiquement la présence de toutes les clés dans les douze langues, la conservation des paramètres de substitution et la sélection du chinois traditionnel. Un repli anglais ne remplace pas une traduction manquante dans une langue officiellement prise en charge.
- Inclure ces vérifications dans les tests obligatoires avant toute nouvelle IPA. Cette règle reste applicable aux interventions suivantes, sans nouveau rappel du mainteneur.

## Build 453 — Azahar FastInterp, 13 octobre 2026

- Demande du mainteneur : remplacer le cœur 3DS dans le moteur libretro embarqué,
  exposer Fast Interpreter activé/désactivé et produire une IPA valide.
- Candidate 0.0.7+453 par-dessus la 452 (1594e78c), sur Claude.
- Azahar officiel 2127.0-alpha1 iOS ARM64, sources 5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6,
  GPLv3+. Paquet de cœurs 8b9e87ba, run 38352378859. Les 13 autres cœurs,
  MoltenVK et ressources système sont conservés octet par octet.
- Option native citra_use_fastinterp, enabled/disabled, défaut activé et choix
  utilisateur persistant ; menu en jeu › Réglages d’émulation. Le libellé traduit
  demande de fermer et relancer le jeu : un simple reset ne garantit pas la
  reconstruction des processeurs avec la nouvelle valeur.
- Les JIT CPU et shader sont compilés désactivés sous IOS et leurs anciennes
  clés ne sont plus déclarées : aucun override fictif ajouté au nouveau cœur.
- Identité, contrôles et limites : docs/build453-plan.md. Aucun gain de FPS ni
  fonctionnement sur iPhone ne doit être annoncé comme mesuré sans test réel.

## Build 454 — vérification de session de l'import 3DS, 13 octobre 2026

- Demande du mainteneur, avec vidéo (Build 453) : choisir le dossier Azahar puis les fichiers de `sysdata` affichait « Impossible de vérifier si un jeu est en cours », code `isSessionActive probe failed: type 'int' is not a subtype of type 'bool?' in type cast`, avant toute analyse. Cause démontrée : `@(self.session.active || self.launching)` dans `LibretroInternalBridgePlugin.m` (Objective-C : `||` donne un `int`, encapsulé par `numberWithInt:`), envoyé en int32 par le codec de Flutter iOS. Les fichiers BIOS du mainteneur n'étaient pas en cause. Plan, cause, tests et limites : `docs/build454-plan.md` ; détail : `docs/libretro-3ds-system-settings.md` § 11.
- Règles posées :
  - une réponse de canal attendue booléenne s'envoie avec `@YES`/`@NO` ou une variable `BOOL`, jamais `@(expression logique ou de comparaison)` dans un fichier `.m` ;
  - côté Dart, un état de session n'est connu que par un booléen : réponse absente, `null`, d'un autre type, ou erreur du canal = état inconnu, jamais « aucun jeu » ; le moniteur de lancement ne termine une session embarquée que sur un `false` explicite ;
  - un test de canal natif utilise les octets que le moteur iOS envoie réellement (`test/libretro_session_envelopes.dart`, vérifiés par `test/libretro_channel_codec_test.py` dans le Simulateur iOS avec le vrai `Flutter.framework` du SDK épinglé), pas des valeurs Dart ;
  - une archive ZIP rangée dans le dossier ou le ZIP choisi n'est pas ouverte et n'est jamais présentée comme une archive non prise en charge (`nestedArchive`, texte en douze langues).
- Conséquence établie dans les sources, non observée sur iPhone : jusqu'à la 453, la session Flutter d'un jeu libretro se fermait environ 4 s après son lancement (sondeur du `GameLaunchManager` arrêté par la même `TypeError`) ; depuis la 454 elle dure jusqu'à la fin réelle du jeu.
- Livraison 454 : source `6dcdfd1aa903c8efb28d5d4bc4cd04464f395255`, run `38370668542` (périmètre `full`, `checks`, `native` avec le test d'encodage et `cold` réussis), artefact `11799289148` (211 053 981 octets, archive SHA-256 `5d0cb69bad10537383b650c47604573b6a70f5f4f64c17563021e6b409c1b2d8`, conservé jusqu'au 27 octobre 2026), chiffré pour `build-utils/delivery-424-recipient.pem`. IPA validée avant scellement `29c4d0a6c1612cdc0a65ab81eec0ca5eb97cd5d61f68e92a0d3ffc41eeebb973` (206 619 559 octets), version 0.0.7 (454) ; SHA-256 de l'IPA scellée à relever après déchiffrement (PC du mainteneur hors ligne au moment de la livraison). Aucune validation sur iPhone. Ne pas réutiliser le numéro 454.

## Build 455 — résolution interne du moteur libretro intégré, 13 octobre 2026

- Demande du mainteneur : un réglage d'augmentation de résolution pour les cœurs du moteur libretro intégré, extensible aux futurs cœurs, puis une IPA vérifiée en précisant les essais réellement effectués. Base : Build 454 (`6dcdfd1a`). Architecture, sources amont et règles : `docs/libretro-resolution.md` ; plan et résultats : `docs/build455-plan.md`.
- Règles posées :
  - une valeur n'est offerte que si le cœur la déclare et qu'elle est applicable (natif et au-delà, une par facteur, limites du profil, 8192 px au plus sur le grand côté de l'image) ; résolution interne, agrandissement de l'image et filtrage restent distincts, et un cœur sans résolution interne est expliqué, jamais masqué ;
  - « en direct » seulement quand la source du cœur prouve qu'il relit l'option en jeu et redessine à la nouvelle taille ; sinon, et pour tout cœur reconnu par son seul nom, « au prochain lancement » : la valeur en cours est gardée pour la session ;
  - les profils de `LibretroResolution` (Dart, envoyés au natif et figés dans `test/fixtures/libretro_resolution/native_rules.json`) font la correspondance des noms de paramètres ; les deux lecteurs de valeurs (Dart, `LibretroResolution.m`) passent les mêmes cas (`value_cases.json`) ;
  - natif par défaut ; un choix pour tous les jeux d'un cœur va dans `Config/<bibliothèque>.json`, un choix pour un jeu dans `Config/Games/<bibliothèque>.json` (entrée du jeu seule réécrite, autres jeux et clés inconnues conservés) et passe avant celui du cœur ; les réglages de console n'écrivent jamais la valeur d'un jeu et sont refusés pendant un jeu ;
  - `test/libretro_core_options_test.py --cores` vérifie dans chaque binaire épinglé la clé, les valeurs, le défaut et le nom de bibliothèque déclarés (`LibretroCore.resolution`) ;
  - un profil nomme les moteurs de rendu (`renderers` : `gles`, `vulkan`, `software`) pour lesquels sa source a été lue ; une fois le contenu chargé, un profil dont le moteur ne correspond pas ne s'applique pas. PPSSPP dans son propre contexte logiciel (sans contexte OpenGL ES, cas du Simulateur) dessine en 480 × 272 quelle que soit l'option, et un changement en jeu y appelle `ContextReset` sur un contexte qui n'est pas matériel (comportement indéfini dans `check_variables`, plantage de la sonde, run `38385450271`) : rien n'y est proposé, et un cœur qui a l'option sans qu'elle s'applique est expliqué comme tel (`resolutionInapplicableFooter`, `inapplicableKey` de `Config/Resolution/<cœur>.json`).
- Changement de comportement assumé : Mupen64Plus-Next et PPSSPP démarrent en natif quand aucun choix n'est enregistré (auparavant 640 × 480 et 960 × 544).
- Vérifié en CI (source produit `6865f458`) : test hôte macOS (52 vérifications de résolution), compilation iPhone, tests Dart et contrats ; sonde simulateur avec le vrai DeSmuME (×2 en jeu : 256 × 384 → 512 × 768, enregistré pour le cœur, relancement à ×2, natif pour un seul jeu) et PPSSPP en rendu logiciel (choix refusé, pas de plantage). Le changement en jeu de PPSSPP avec OpenGL ES, de Beetle PSX et d'Azahar n'est exécuté par aucun essai automatique.
- Livraison 455 : source `a12f075906ef452885decbef78fefd6517ce0fe0` (arbre produit de `6865f458`), run `38393178533` (périmètre `full`, `checks`, `native` et `cold` réussis), artefact `11812355580` (211 121 053 octets, archive SHA-256 `e35c8e13d125a0d302d840d297abe396eb6a15512d51d2bc1cdfb36d3bbc99ee`, conservé jusqu'au 27 octobre 2026), chiffré pour `build-utils/delivery-424-recipient.pem`. IPA validée avant scellement `7926a48c863cf38f7015f84f21b68353ccf0f91ce02b7e21f9c4e9c8c5ab2745` (206 686 562 octets), version 0.0.7 (455) ; SHA-256 de l'IPA scellée à relever après déchiffrement. Aucune validation sur iPhone. Ne pas réutiliser le numéro 455.

## GitHub publication language — maintainer preference, 13 October 2026

- Write and publish NeoStation GitHub release notes and announcements in English only. Do not append a French translation or a bilingual version unless the maintainer explicitly requests an exception.
- Use concise, natural wording with a modern, appealing presentation. Avoid generic promotional filler and excessive emojis.
- This is a permanent preference for future GitHub publications. It does not change the app's twelve-language localization requirements.

## Diagnostic preferences — maintainer instruction, 14 October 2026

- The maintainer has no iOS `.ips` reports. Do not request these files again.
- Permanent maintainer instruction, 17 October 2026: never ask for `.ips`, Jetsam or watchdog reports for NeoStation. Do not make diagnosis, corrections or IPA delivery depend on these files. Continue with source evidence, application journals, executable reproductions and diagnostics captured automatically by the app. Keep the distinction between a proven source defect and the unconfirmed mechanism of a device termination.
- Continue diagnosis using source evidence, regression tests, and available NeoStation logs. Clearly distinguish a demonstrated source defect from an unconfirmed explanation of a device crash; absence of an `.ips` file does not justify claiming a cause or stopping the authorized work.


## Private Build 456 — shader candidate, 14 October 2026

- The maintainer authorized a private IPA for physical iPhone tests. No public release was requested. Candidate `6346df7dcbe9f2a40caea058bc67321f6f72e85f`, workflow run `38591125638`: checks, native and cold iPhone build passed; benchmark disabled.
- Output version **0.0.7 (456)**; do not reuse build number 456. Public recipient `build-utils/delivery-456-recipient.pem`; private key remains outside Git. Encrypted artifact `11909445866`, expires 28 October 2026.
- Sealed IPA SHA-256 `5dc0cf7e798a95eb001f093533dbb590a0d3b08738a412e8a03313a8e0a86b35`, 211,140,422 bytes. Final app/extensions versions, source identity, native shader markers, both catalogs and all 43 Dolphin shader files were independently checked. Details: `docs/build456-plan.md`.
- This is a test delivery, not evidence of the original device crash cause or GameCube/Wii shader rendering in the integrated Dolphin engine. Mattias redistribution remains unresolved; no Mattias shader file is bundled.

## RetroArch shader crash — maintainer's Build 456 test, 14 October 2026

- The maintainer confirms Dolphin effects work on GameCube/Wii and requests that they remain unchanged. Build 456 still closes immediately on RetroArch catalog Apply.
- Supplied application journal: 0.0.7 (456), Azure Dreams, Beetle PSX HW 0.9.44.1-GLES3 10e4b0c, software renderer, `reshade/handheld-color-LUTs/PSP-2020.slangp`; stops before compilation completes. Do not claim that this application journal alone identifies an iOS exception or jetsam.
- Native reproduction loads the actual pinned old Dolphin/new kit compiler sources in Runner's order. LLDB demonstrates the new parser calling the old weak `addSwizzle<int>`, then the old pool allocator crashing with `EXC_BAD_ACCESS`. Five official presets fail before isolation and compile after it. See `docs/retroarch-shader-compiler-2026-10-14.md`.
- Correction `d457c8ff`: isolate glslang/SPIRV-Cross behind the kit's public Objective-C API at link time. Do not remove this boundary or consider public headers alone sufficient isolation. Final IPA export-trie validation rejects the faulty Build 456 layout. No Dolphin/core source is changed.
- Private Build 457 candidate/run and exact evidence identities are recorded in `docs/build457-plan.md`. No physical test of this correction is yet claimed; private IPA authorization does not authorize a public GitHub release.

## Consoles de l'onglet Consoles dans le moteur libretro intégré — lot 1, 14 octobre 2026

- Demande du mainteneur : intégrer au moteur libretro intégré les cœurs compatibles iOS des consoles déjà listées par l'onglet Consoles mais lancées seulement par l'application RetroArch, par lots, sans nouvelle plateforme, sans toucher Dolphin, RPCS3, ARMSX2 ni Azahar, sans activer de shader, sans fournir de BIOS, licences vérifiées et crédits conservés. Inventaire, choix, limites et consoles en attente : `docs/libretro-consoles-lot1.md`.
- Lot 1 : 21 consoles (PC Engine, TurboGrafx-16, PC Engine-CD, TurboGrafx-CD, WonderSwan, WonderSwan Color, NeoGeo Pocket, NeoGeo Pocket Color, Lynx, Virtual Boy, Atari 2600, 7800, 5200, ColecoVision, Pokémon Mini, Game & Watch, Mega Duck, Supervision, Arduboy, WASM-4, Uzebox), 16 cœurs officiels du buildbot iOS ARM64 ajoutés sans modification à la collection épinglée (`build-utils/libretro/add_cores.py`, artefact `LibretroCores-df0124b8…`, run `38627332377`) ; les 14 cœurs précédents, MoltenVK et les fichiers système sont recopiés octet pour octet.
- Règles posées :
  - une console qui passe de RetroArch au moteur intégré garde l'identifiant et le nom qu'elle avait dans l'onglet (consoles ajoutées, interrupteurs et masquages conservés sans migration) ; deux révisions d'un matériel restent deux consoles, comme Game Boy et Game Boy Color ;
  - un cœur n'entre dans un lot que s'il figure dans la liste App Store iOS de RetroArch ou que son absence de JIT est établie par ses sources ; un cœur qui exige le JIT (Flycast) ou dont le binaire iOS du buildbot déclare une autre plateforme (Hatari) reste documenté comme incompatible, sans intégration forcée ;
  - les jeux importés vont dans un dossier que le scanner reconnaît pour le système (`LibretroCoreCatalog.importFolderFor`) ;
  - un cœur n'est annoncé fonctionnel qu'après son lancement réel en CI (sonde simulateur `--lot1` sur des programmes de test écrits par la sonde, aucun contenu tiers) ; le simulateur n'est pas l'iPhone.
- Livraison 458 (lot 1 seul) : source `99914407242163c6637fe42fba50a3aca877bb5f`, run `38636877971` (`checks`, `native` et `cold` réussis), cœurs `LibretroCores-df0124b8…` run `38627332377`, artefact `11930360072` (214 262 173 octets, archive SHA-256 `c60b1f8ce622cb71b016eb6bf5620893058c44948cbbc7c35a5e4491da53366b`, conservé jusqu'au 28 octobre 2026), chiffré pour `build-utils/delivery-424-recipient.pem`. IPA validée avant scellement `fea5c6fe41ce3b5696fe928105f401d7ed90b6362e63d529eaf020f734a9c946` (209 620 749 octets), version 0.0.7 (458) ; SHA-256 de l'IPA scellée à relever après déchiffrement. Aucune validation sur iPhone. Ne pas réutiliser le numéro 458.

## Consoles de l'onglet Consoles — lot 2, 14 octobre 2026

- Lot 2 : Fairchild Channel F (FreeChaF), Intellivision (FreeIntv), Magnavox Odyssey 2 (O2EM), NEC PC-FX (Beetle PC-FX), mêmes règles que le lot 1. Paquet `LibretroCores-fdeaef56…`, run `38638115521` (34 cœurs), construit sur celui du lot 1 recopié octet pour octet. Détails, commandes, BIOS et consoles en attente : `docs/libretro-consoles-lot2.md`.
- **Consigne du mainteneur du 14 octobre 2026 : « Il ne faut jamais fournir les BIOS. »** Aucun BIOS ni firmware de console, ni dans le dépôt, ni dans le paquet de cœurs, ni dans l'IPA, ni par téléchargement. Un cœur dont le binaire embarque un firmware d'origine (vecx : ROM système Vectrex ; Virtual Jaguar : ROM de démarrage et BIOS CD Atari) n'est pas empaqueté, tout le paquet étant copié dans l'IPA. Seuls les remplacements libres écrits par leurs communautés et sous licence libre (AltirraOS d'a5200, FreeBIOS de PokeMini, chargeurs Cathy3K d'Ardens, code HLE) restent admis, crédités. L'utilisateur fournit lui-même ses BIOS dans Fichiers › NeoStation › Libretro › System.
- Règles posées :
  - un cœur qui exige plusieurs fichiers BIOS et charge quand même un jeu sans eux (FreeIntv) les déclare dans `LibretroCore.biosAllOf` ; le lancement est refusé avec `LIBRETRO_BIOS_MISSING_ALL` en nommant les fichiers manquants ; les messages de BIOS manquant remplissent toujours `{files}` ;
  - les images de BIOS de substitution de la sonde simulateur (une instruction qui saute sur elle-même) ne sont écrites que dans l'application de sonde, jamais dans le paquet ni dans l'IPA ;
  - NeoCD et Opera (clauses non commerciales) attendent la décision du mainteneur, comme Snes9x, PicoDrive et FBNeo ; Yabause attend une mesure de performances sur iPhone ; EasyRPG reste incompatible tant que l'hôte n'offre pas `RETRO_ENVIRONMENT_SET_AUDIO_CALLBACK`.
- Livraison 459 (lots 1 et 2) : source `e5400cbeacf850328a6d069be46dbf0479eb7a4a`, run `38642923272` (`checks`, `native` et `cold` réussis), cœurs `LibretroCores-fdeaef56…` run `38638115521`, artefact `11932985033` (215 447 453 octets, archive SHA-256 `d2378c2607941fb5a57710897f26c355f1c34f888170e9c876b9fcdaae087654`, conservé jusqu'au 28 octobre 2026), chiffré pour `build-utils/delivery-424-recipient.pem`. IPA `NeoStation-Build459-e5400cbe…-cold.ipa`, 215 167 326 octets, SHA-256 `e72d9163b4b3c02f8d96f8294c18de9c547f729a41bdd4d67ed8060a53bbb513`, égal à `SHA256SUMS` et à `signed-payload-identity.json` ; version 0.0.7 (459), 34 cœurs libretro. Déchiffrée sur le PC du mainteneur ; copie `C:\Users\Coren\Downloads\NeoStation-Build459-e5400cb.ipa`. Aucune validation sur iPhone. Ne pas réutiliser le numéro 459.

## Build 460 — enfoncement des contrôles libretro, 15 octobre 2026

- Demande du mainteneur : pousser les correctifs de skins et livrer une IPA privée pour test. Produit testé `d6cb962d` (neuf sessions simulées, 270 vérifications), candidate de livraison `b92ff6e984d9086bd7da2d7361fe477804ce86aa`, run `38708722521` (`checks`, `native`, `cold` réussis). Les sources produit restent identiques à `d6cb962d` ; les 34 cœurs, Dolphin, RPCS3 et ARMSX2 conservent leurs identités. Diagnostic et limites : `docs/libretro-skin-press.md` ; livraison : `docs/build460-plan.md`.
- Les graphismes séparés s'enfoncent au contact ; les fonds simples fiables sont découpés et masqués en mémoire. Les skins texturés/translucides non isolables nécessitent une variante adaptée : ne pas annoncer une compatibilité complète. `asset.selected` n'est jamais un état d'appui.
- IPA **0.0.7 (460)**, 215 173 379 octets, SHA-256 `a4734d95ff7c833d6fe17caadf732048bf545e7c42620323193a9315e48085fd`, égale aux deux rapports d'intégrité. Artefact chiffré `11960198085` (clé publique `build-utils/delivery-460-recipient.pem`, clé privée sur le PC), archive SHA-256 `c1ea1e22ea031b62c5d8c4188609ecb2e894195e1fc8c54be01785cdc01503f7`. Déchiffrée et vérifiée sur le PC, remise dans Téléchargements sous `NeoStation-Build460-b92ff6e.ipa` pour re-signature SideStore. Ne pas réutiliser le numéro 460.
- Aucune validation sur iPhone physique ou manette matérielle ; ne pas la déduire des contacts UIKit scriptés, de la manette virtuelle ni de la compilation. Aucun BIOS ni graphisme Manic ajouté au produit ; Manic EMU est une référence de format/rendu, pas un émulateur intégré.

## Directional skin pressure — 15 October 2026

- Authorized refinement after Build 460: shared per-arm pressure for monobloc D-pads, local composite deformation and validated Delta `_pressed` siblings. Product source `9e19d947a9dd5595cf09701fcf3c08024b3787c4`, run `38724927589`: native and skin-press jobs passed. Details, failures retained, evidence identity and limitations: `docs/libretro-directional-pressure.md`.
- Keep D-pad parent transforms unchanged. Visual direction bits must come from the existing touch tracker; each diagonal activates exactly two prepared regions. Preserve source image coordinates, sampling aprons and physical-pixel-aligned masks/opacity groups to avoid alpha seams. Clear image readiness on replacement/reload; stale readiness must not bypass an authored image after cache eviction.
- `_pressed` means an actual validated sibling of the chosen background resource, never a fictional universal JSON field or Manic `asset.selected`. Overlapping/ambiguous or over-budget regions may remain static; do not claim universal contour inference. The exact Atomic Pink archive remains untested.
- Final evidence: 17 simulated sessions, 891 checks, 104 directional pixel comparisons with zero changes outside active regions and zero rest differences; 71 iPhone bridge sources compiled/linked. The 16 portable test executables (720 pressure and 6,025 tracker checks) were reused with closed-input/toolchain identity from the successful native phase of run `38719706135`; that run's separate UIKit failure remains recorded. Never turn phase reuse into a claim of re-execution.
- No new IPA or physical-device/controller validation in this cycle. Build 460 does not include these refinements. Keep the unchanged 34-core package, console mappings, settings and baseline library identities.

## Build 461 — overlapping and asymmetric skins, 15 October 2026

- The maintainer authorized the next refinement and a new private IPA on `Claude`. Product changes stay in the common libretro renderer/pressure module: exclusive visual fragments for overlaps, bounded alpha-cross geometry, prepared 12-state release with an 8-state fallback under the existing 32 MiB budget. Keep shared pixels static, keep touch margins separate from artwork, and do not infer arbitrary contours or a universal pressed-state field.
- Atomic Pink is now tested from the actual `GBC-AtomicPink.deltaskin` archive, pinned to `delta-skins/delta-skins.github.io` revision `61dad28f552051bc05f519f968e913bf243d22eb`, SHA-256 `d870e53c3728c6b84aeb163b489e03e8ab903ad0927f18ce27dd3235ddcfec84`. Its four PDFs have no `_pressed` variant; landscape A+B is a real drawn control. iPad uses the phone fallback. Artwork is CI-only, never bundled in the IPA.
- UIKit source `7c05e44f89cb5f5095e9c1f4c4c745e36e2bde0e`, run `38731165154`: successful rendering job, 23 sessions, 1,380 checks, 152 directional comparisons, no changed pixels outside active regions. Its separate macOS test-name collision remains a recorded failure, corrected by renaming the test helper; never describe that whole run as successful.
- Delivery source `fa2014171e23771d1abd1a5d80c243813af771c2`, run `38732938115`: `checks`, `native`, `cold` succeeded; 16 native executables actually run, 998 pressure checks, 6,025 tracker checks, 71 iPhone bridge sources actually compiled/linked. Rendering provenance compares 2,554 closed source/dependency inputs before packaging. Delivery and focused-skin push workflows now support `Claude`; delivery still requires its explicit commit marker or dispatch.
- IPA **0.0.7 (461)**, 215,189,456 bytes, SHA-256 `f799f5512ee558bbd3a10e98cbf35cba11bfe93a109cff839616de702ed541ab`; decrypted from artifact `11974260046` and independently checked against both integrity reports, all 76 sealed-image fingerprints, five extension versions, 34 unchanged cores and the new renderer markers. Public recipient `build-utils/delivery-461-recipient.pem`; private key is outside Git. The PC was offline; deliver the verified IPA as a downloadable file for SideStore. Do not reuse 461.
- Details, limits and the physical-iPhone checklist: `docs/build461-plan.md`. No physical-device, hardware-controller, end-to-end touch-latency or ProMotion validation is claimed. Preserve all other engine, settings, catalogue and baseline-library identities; no BIOS added.

## Build 462 — tactile depth and intensity, 15 October 2026

- The maintainer requested visibly stronger mechanical depression for all mapped Delta buttons and every source's D-pads, with no new intermediate approval. Work stays on `Claude` and in the common libretro renderer. Product commits `2d161d71` and `99ee2376`: size-aware four-level depth/compression/occlusion profiles, Pronounced default, local authored-texture handling, bounded separate-alpha-arm detection, conservative neighbour protection and prepared damped release. The in-game Skins preference is translated in all twelve languages and stored per console/game without changing remaps or selected skins.
- Corrected probe source `06143ac80815c5f125b20e18c47c2d6291eeb117`, focused run `38743904734`: native and UIKit passed. Actual native executions: 16 files, 1,133 pressure checks, 6,025 touch-tracker checks, 71 iPhone sources compiled/linked. UIKit: 25 Simulator sessions, 2,367 checks, including Atomic Pink, all four intensity choices in the live menu, diagonals, simultaneous buttons and virtual-controller handoff. Earlier failed runs and the probe lifecycle correction are retained in `docs/build462-plan.md`.
- Build **0.0.7 (462)** successfully produced from `a2862cb43303dd5bb3e709e002d061cf3d5a58ec`, delivery run `38748215667`: checks, native and cold Release succeeded; warm benchmark skipped. The rendering gate verifies 2,554 exact inputs; delivery native reuse keeps the genuine successful phases/source/toolchain separate from the earlier failed overall workflow. CI passed package/version, 34-core identity, ZIP and strict on-disk signature validation.
- The execution environment and PC recovered on 15 October; the existing build was delivered without recompilation. Encrypted artifact `11981077900` (215,788,957 bytes, archive SHA-256 `e092b31d60e9e9981406f330435561fe36f13d5057249661cec98b77392841f2`), recipient `build-utils/delivery-461-recipient.pem`; the private key remains outside Git. Final sealed IPA: **215,191,633 bytes**, SHA-256 `9d5ea68cb204e167815c18edd05f3c07999ffa5a5d45745565d3b8e8cf37e736`, independently matched to both integrity manifests, all 76 payload fingerprints, app/five extension versions, source identity, 34 cores and new renderer symbols. The earlier `5d8b4f7e…` CI checksum precedes sealing and is not the delivered hash.
- `NeoStation-Build462-a2862cb4.ipa` is available privately in the conversation and copied to `C:\Users\Coren\Downloads\NeoStation-Build462-a2862cb4.ipa`; the Windows copy has the same verified sealed SHA-256. Successful UIKit artifact `11978678277` was downloaded and checked: 168 directional pixel comparisons, zero outside changes, maximum resting channel difference 1, maximum prepared resources 26,716,272 bytes. The delivered before/after comparison uses these final captures, not earlier failed candidates.
- **Do not reuse 462 for another code version.** SideStore re-signing/provisioning and physical iPhone, hardware controllers, latency, ProMotion and thermal behaviour remain manual checks; no device installation is claimed. Preserve other engines and the library baseline; no BIOS added. Details and checklist: `docs/build462-plan.md`.


## Build 463 candidate — Libretro previews and opt-in cheat catalogues, 15 October 2026

- The maintainer authorized corrections on `Claude`, prioritizing reported Ignited crashes, complete Libretro overlay previews and a multi-source cheat manager. Build 462 remains a distinct delivered binary; the next delivery number is 463. Preserve the 34-core package, other engines and library baseline.
- Preview conversion and gameplay use the same normalized/full-screen overlay geometry. Real Flat PSX and RGPAD Modern fixtures are pinned with their CC BY 4.0 licence; empty overlay-navigation placeholders are ignored, missing assets refuse partial conversion. Skin assets are preflighted, live texture estimates bounded, and the previous working layout retained on failure.
- Original NES Ignited Orange is tested against its immutable archive and actual Nestopia binary. Supplied iPhone logs do not identify an exception or jetsam cause. Do not claim the reported physical-device crash is reproduced or fixed from successful Simulator rendering or malformed-PDF fallback tests.
- Two reviewed opt-in sources: `libretro/libretro-database@12c21cf7` (CC BY-SA 4.0) and `skyzyx/openemu-cheat-database@5f1af616` (Unlicense). Verify reviewed licence and data hashes, retain source attribution and region/version titles, require manual confirmation for uncertain identities. Never enable codes on download/import/session launch; remembered selections require explicit restoration. Handler-1 memory operations and unreviewed core formats remain disabled. Six initial core profiles are not support for all 34 cores.
- Exact candidate `bcb6d6e90e92de11bc960929a3fc3db3e016caef`: focused run `38771763641` succeeded (38 parser, 23 source/offline, 15 live-download checks; 151 UIKit checks including actual Nestopia/Snes9x memory effects, import/consent/preferences, corrupted-Ignited fallback and four complete overlay previews). Directional native job `116549101178` succeeded: 18 executables actually run, 1,133 pressure-pixel checks, 6,025 touch-tracker checks, 74 iPhone sources compiled/linked. Full rendering results and delivery identity are recorded only once complete in `docs/libretro-overlays-cheats-build463.md`.
- The cancellation probe checks immediate contact/visual/model release and then zero delivery after at least four actual core polls within a bounded deadline. Never replace this with waiting for the expected button value. This changes test observation, not product input logic.
- Final menu review `c93f493a` also replaces arithmetic switch tags with current-row identity and restores the disabled switch before activation consent; UIKit tests cover row 1001, disabled/stale dispatch and cancellation. Final `c93f493a` suites passed: directional run `38774454891` (25 sessions / 2,457 checks, native passed), focused run `38774454871` (155 UIKit and 76 parser/catalogue/network checks), and all engine jobs in `38774454885`. Repeated suites are not additional distinct scenarios. See the report for the separately recorded broad-probe failures and delivery identity.
- Physical iPhone gameplay, the reported two commercial-ROM terminations, hardware controllers, latency, ProMotion and sustained memory/thermal behaviour remain manual checks. Private IPA authorization is not public-release authorization.

- Build 463 successfully produced from `73b0aabc81ffec7e14873b1e466c294980ea28fc`, delivery run `38779178451` (`checks`, `native`, cold Release passed; warm benchmark skipped). Final sealed IPA: 215,255,436 bytes, SHA-256 `0912ddc8e7cf5594363f39a04c486bf3e2851b6f504aabae13007231bc5afba6`. Both integrity reports, 76 sealed payload fingerprints, app/five extension versions, 34 cores and new cheat/validation/menu markers independently checked. SideStore Apple re-signing remains required; minimum iOS 18.0, no physical-device installation claimed. **Do not reuse 463.** The broad final simulator workflow also passed after the unchanged official-shader job rerun; earlier failed attempts remain in the report.

- Verified Windows delivery: `C:\Users\Coren\Downloads\NeoStation-Build463-73b0aabc.ipa`, same final SHA-256 and byte count. Existing build files retained. No physical iPhone test or installation is implied by the PC copy.

## Build 464 candidate — installed skin regression, 15 October 2026

- The maintainer reports an actual 463 regression: DualShocked – Gray remains installed and selected in Flutter, but native gameplay falls back and its menu loses the entry. Correction and private IPA are authorized on `Claude`. Preserve pressure, intensity, touch input, all 34 cores and other engines.
- Original starvingartist archive SHA-256 `05878738f250279bfae6e27b9b597f182562b4dcfb71f86ab286d49c0c7f59c4` contains a deliberately empty portrait `asset.normal`. The new 463 activation validator wrongly promoted advisory whole-skin warnings to failure, then blacklisted the identifier and removed its model. Correct per-layout resource requirements instead of resetting selections or forcing default. See `docs/build464-skin-loading-regression.md`.
- Keep already installed ids, metadata, game/console priority and separate orientations. Errors in one layout must not hide a usable installed skin; late asynchronous results must identify their own layout/generation. Confirm a previous working renderer only after required images are ready. The exact negative reproduction uses the unchanged 463 sources; original art is CI-only with credit.
- Test results and build identity are pending, not implied by this entry. Actual Azure Dreams/iPhone upgrade and hardware input remain manual. Do not reuse 463.

- Build 464 tested candidate `12574f598e30bb2476e7cc969ce92cc955dd8daf`: loading run `38807637925` / job `116672537707` succeeded (unchanged 463 rejects original DualShocked, 3 assertions; candidate 53 upgrade/menu/orientation/fallback and 10 relaunch checks). Directional run `38807496814` succeeded: native job `116672023752` ran 18 executables, 1,133 pressure and 6,025 tracker checks, compiled/linked 74 iPhone sources; skin-press job `116672024338` passed 27 sessions / 2,786 checks, including exact combined input after observed core frames. Catalogue/core run `38807496808` / job `116672024072` succeeded (38 parser, 23 source/offline, 15 live-source and 160 UIKit/core/preview checks).
- Earlier 4cf pressure attempt retained one failed iPad combination assertion after a fixed 250 ms delay; actual contact diagnostics were correct. 12574f59 strengthens that test with four observed core polls, a bounded deadline and exact button/visual/direction comparisons. Runtime input and pressure source files remain unchanged. See the report for retained earlier compile/startup/test failures; do not call them passes.
- Private Build 464 delivery may proceed using these exact source closures and successful gates. Final IPA identity and Downloads receipt remain to be recorded; no physical iPhone/Azure Dreams test is implied by Simulator results. Keep Build 463 as a distinct previous delivered binary and never reuse its number.

- Build 464 delivered from `b4c385036dfc89e1d795a7b54474911358f80819`, run `38810224933`: checks, native and cold iPhone Release all succeeded; warm benchmark intentionally skipped. Encrypted artifact `12008918114`, 216,496,541 bytes, ZIP SHA-256 `6e3d7bda6689742f136e01ffde6bff7ee4e707e671333418ed3c7bf1701fee13`. Final sealed IPA: 215,260,715 bytes, SHA-256 `dedd79d1ca6291da7c0e4825faa9bac58531e3a9395c096bb89c82ad60a3bc0e`, version 0.0.7 (464). Independent verification confirms both integrity records, 76 payload fingerprints, app/five extension versions, 34 cores and new scoped-validation/readiness/diagnostic selectors. SideStore Apple re-signing remains required; no physical iPhone test is claimed. **Do not reuse 464.**
- Windows copy verified after transfer: `C:\Users\Coren\Downloads\NeoStation-Build464-b4c38503.ipa`, same bytes and SHA-256. Existing previous builds retained. IPA and four original Simulator captures were saved for the maintainer. Actual upgrade/Azure Dreams/physical-controller/latency validation remains manual. Detailed report: `docs/build464-skin-loading-regression.md`.

## Build 465 candidate — PocketArch and Provenance, 16 October 2026

- The maintainer confirms installed skins work again in 464 and authorizes catalogue corrections and a private test IPA on `Claude`. Preserve all 464 native loading/rendering/pressure/input sources, all installed files/selections and all 34 cores.
- PocketArch's common failure is double percent-encoding of repository paths containing spaces. Build raw URI path segments exactly once. Keep the 26 complete originals; the two PSP originals reference five absent images each and are excluded individually. Do not remove installed user files.
- Provenance currently lists eight PSX entries, all credited to DeltaStyles. Retain index membership independently from author-host attribution and through deduplication; show Provenance only where candidates remain, subject to the real native verdict. Platform candidates use the central console registry, including default-hidden consoles; never force an unsupported or empty platform.
- Original configuration/resource audit, source-filter and native-preview checks, exact results and delivery identity: `docs/build465-catalog-audit.md`. Tests and IPA are pending until actual successful CI evidence is recorded. No physical-device validation is implied.

- Build 465 source `a0f1b291951008a141e0b857800c091660c2b855`, delivery run `38822682091`: checks, native and cold iPhone Release succeeded; warm benchmark intentionally skipped. Final sealed IPA 0.0.7 (465), 215,262,198 bytes, SHA-256 `e5b49390d78f2ad9f340c057be694cb0773b8888f1b6a5f44c748ffc980d48ad`; encrypted artifact `12013744858`, ZIP SHA-256 `a8b7bb96c62deb71c4156d6a3dc687e5450e3ffc008a3e86621c93312aebf735`. Independently verified both integrity records, all 76 compiled payload fingerprints, five extension versions, 34 cores, and the exact corrected embedded catalogue. SideStore Apple re-signing is required; **do not reuse 465**.
- Regression source `6f3f017c2ff0ca7bcb24acad2c6253f6b8ce5e99`: full pressure run `38819105153` passed 27 sessions / 2,840 checks, focused flat NES/iPhone run `38819107430` passed 110. Catalogue run `38819113652` passed 109 Flutter tests plus 39 original PocketArch associations / 78 orientations. Loading run `38819110606` attempt 2 passed exact 463 rejection plus 53 upgrade and 10 relaunch checks; attempt 1's late simulator startup and the earlier single fixed-delay observer failure remain documented, not counted as successes. Cheat/preview run `38819105076` passed. Product changes remain confined to four catalogue paths; all 464 native sources and installed user files/selections are preserved. No physical iPhone or hardware-controller validation is claimed; see the report for complete evidence and limits.


## Build 466 — delivered automatic cheat discovery, 16 October 2026

- The maintainer authorizes auditing, fixing, testing, pushing and a private IPA on `Claude`, preserving the delivered 464/465 skin corrections. Confirmed rupture: installed source indices never automatically populated the game's cheat records. Candidate design, reviewed sources, bounds and validation: `docs/build466-automatic-cheats.md`.
- Bundled source/console indices and original complementary XML are allowed by the latest request. Preserve source licences/attribution separately; hash-derived canonical titles retain regions/revisions. Uncertain identity still needs confirmation before activation. Discovery and session launch never enable codes.
- Shared catalogue/UI for current and future cores; activation requires an explicit bounded adapter, never just presence of mandatory ABI symbols. Handler-1 memory operations and unreviewed formats remain disabled. All added labels use the twelve-language catalogue.
- Successful checks and the exact private IPA identity are recorded below. Do not claim physical-device gameplay validation. No public release is authorized by this request.

- Build 466 delivered from `ff70cc9df1fe30a28cf1fc53e7dfdc2c56738624`, run `38835740295`
  (`full`; checks, native and cold iPhone Release succeeded; optional warm
  benchmark disabled). Final sealed IPA 0.0.7 (466): 218,599,277 bytes,
  SHA-256 `1eabef6e3ac7b6b0d47ec591cc18a335d583acf39eeff1f7ead3744b51167d3e`. Encrypted artifact
  `12019654684`, ZIP SHA-256 `b89d5c1cb7311fcb3ee5bec21bf21ad4c42d5a861136b6a2d553b0b694f8927d`.
- Independent final-IPA verification confirms both integrity records, exact
  source stamps, app/five extension versions, all 76 payload fingerprints,
  34 unchanged cores, six new cheat runtime markers and the 34 reviewed
  catalogue/licence resources (12,260,537 bytes). Windows Downloads copy
  `C:\Users\Coren\Downloads\NeoStation-Build466-ff70cc9d.ipa` has the same hash.
- Final runtime/data/test source `cc594d40a751be462dad0e3ef437c4ade5e2fc80`:
  engine `38832178562` passed native/Dart plus 27 skin sessions / 2,840 checks;
  loading `38832181302` passed exact 463 rejection + 53 upgrade and 10 relaunch
  checks; catalogue `38832183687` passed 109 Flutter / 78 native checks. Cheat
  run `38832175806` attempt 2 passed 38/23/49/15 native/live checks and actual
  NES/SNES/DS activation/disable, automatic UI/CUE migration and second-process
  persistence. Attempt 1 reached no app progress before Simulator deadlines;
  retained separately, not counted as a pass. Full evidence and format/container
  limits: `docs/build466-automatic-cheats.md`. SideStore Apple re-signing remains
  required; no physical iPhone test is claimed. **Do not reuse 466.**

## Build 467 candidate — PS1 search follow-up, 16 October 2026

- The maintainer reports no PS1/FFVII cheat results in delivered 466 and requests a direct search-to-toggle experience. Correct on `Claude`, preserving the delivered skins and all cores/other engines. Do not reuse 466.
- Carry the session's existing game title as an uncertain hint; read bounded ISO9660 SYSTEM.CNF serials for uncompressed discs and retain reviewed RDB serial metadata. Hash/serial region identity outranks title hints. CHD/PBP raw hashes do not establish game identity.
- Root search must name available sources and reach game/version results without requiring catalogue selection. Clearly distinguish filtering loaded codes. Catalogue data absent for a region must never be invented or replaced automatically by USA codes. FFVII reference coverage is USA only; 17 of its 19 programs use the reviewed simple writes.
- Tests and IPA pending actual results; see `docs/build467-ps1-cheats.md`. No physical iPhone or commercial PS1 gameplay effect is claimed by metadata/UIKit dispatch checks.

- Build 467 final tested runtime/data source `6a7ddb54568e9048a7b66682c6fcdd9889f9f9ef`: all four gates passed. Engine `38887228314` passed 19 native executables, 1,133 pressure / 6,025 tracker checks, 74 iPhone objects and codec; Dart 578+245+4; 27 skin sessions / 2,840 checks. Catalogue `38887225249` passed 109 Flutter / 78 native checks. Loading `38887222398` attempt 2 passed exact 463 rejection + 53 upgrade and 10 relaunch checks; attempt 1 reached no reference-app result. Cheat `38887218980` attempt 2 passed 38/23/74/23 native/live and 128/49/10/4/4 UI/core checks plus four actual second-process persistence checks; attempt 1 passed its first process but reached no second-process result. Earlier failed/superseded runs remain recorded in `docs/build467-ps1-cheats.md`, not counted as passes.
- The exact regenerated reference retains 3,978 PS1 serial-bearing rows (4,345 total PS1 identities); do not collapse per-release aliases by name/hash. A valid empty old downloaded index must not suppress a verified nonempty bundled reference. User-initiated background queues and cached patterns keep discovery responsive during emulation; test deadlines remain unchanged.
- Build 467 private delivery may proceed with exact closed inputs and these successful gates. Final sealed IPA identity is recorded below. No physical iPhone or commercial PS1 code effect is claimed; PS1 metadata/UIKit/dispatch and real NES/SNES/DS RAM effects are distinguished. Preserve all 34 cores and delivered skin behaviour.

- Build 467 delivered from `3e943d3e7adddd5d7d1160c02d5e6b2d66ce104a`, run `38890710447`: checks/native/cold Release succeeded; optional warm skipped. Final sealed IPA 0.0.7 (467), **218,623,618 bytes**, SHA-256 `6d7a5807a2b1d9532be3c7b6f4dde5d752d5950744e856f8afd5632971701d84`. Encrypted artifact `12042815582`, ZIP SHA-256 `34ac9887fb635b72c2658b5c61f42671d5e01f2592db117a6f0f4d76182e70b5`, recipient 424. Independent verification confirms both integrity records, source stamps, six versions, all 76 sealed payload fingerprints, 34 cores, new PS1/search selectors and all 34 cheat resources (12,348,053 bytes). Native validation reused exact successful 6a inputs/toolchain; not re-executed.
- Private downloadable IPA and Windows `C:\Users\Coren\Downloads\NeoStation-Build467-3e943d3e.ipa` have the same verified hash. **Do not reuse 467.** SideStore Apple re-signing remains required; no physical iPhone or commercial PS1 gameplay validation is claimed. Full evidence, retained failures, source licences, regional/format/container limits: `docs/build467-ps1-cheats.md`.


## Validation reuse — permanent maintainer instruction, 18 October 2026

- Do not multiply or repeat validations that have already passed when their tested inputs are unchanged. Reuse the recorded successful evidence and advance toward the requested testable IPA.
- After a targeted fix, run only the checks affected by that fix. A relevant new failure or changed tested input may justify a targeted rerun; it does not justify restarting every previously successful suite.
- Reuse unchanged precompiled emulator cores and native components. Passing tests permit delivery of a clearly identified candidate for the maintainer to test; do not keep delivery blocked by redundant validation or present Simulator success as physical-device proof.


## Private Build 470 — targeted ARC ownership fix, 18 October 2026

- The maintainer reports Build 469 still crashes; do not treat its 37 Simulator sessions as physical validation. Investigation proved a separate retained-owner defect: in `__weak LibretroMenuPage *_visiblePage, *_rootPage`, ARC makes only the first pointer weak. `_rootPage` was strong and closed a Menu/page/row-action cycle, retaining one catalogue per closed session. Product fix `6b1aaba9dd8b6e7cdb50de5730fbd6f51dd0a9eb` splits this into two explicitly weak declarations. No cheat feature/data/preferences or valid skin was disabled.
- Targeted witness `2ca52ba233e5acaf3b8848dc3a21b78719a74e87`, run `39077361583`, passed Apple Clang ownership proof and the changed iPhone source, 20 sessions with zero tracked owners after each close, 99 actual NES cheat/menu checks and four independent-process persistence checks. Final footprint 50.26 MiB versus baseline 131.10 MiB with 20 retained menus; this establishes the retention fix, not the original iPhone termination mechanism.
- The earlier successful 100 launches + ten independent process starts, 12 bridge ASAN sessions, journal TSAN, engine/skin/catalogue/loading results were reused for unchanged inputs. Full Dart checks `38962439914` / source `fc1ef43a` passed before unrelated jobs were cancelled; Build 469's accepted cache records this exact source. All 107 NeoSwap native inputs remain byte-identical and their 469 tests were reused. Do not repeat these validations without changed tested inputs or a relevant new failure.
- Private IPA **0.0.7 (470)** built from `a43a570412ed2bf382d2df3acc0a9ce9ca88c27c`, run `39078262825`: checks/native/cold pass, optional warm skipped. Final file `NeoStation-Build470-a43a5704.ipa`, **218,634,697 bytes**, SHA-256 **c240faf5ec816243fd9b595e7fae1c07118e8e71a5db3f1abb394e9242bceb60**. Encrypted artifact `12118192232` / ZIP SHA-256 `77262a977f7d19a67a61bbb2d6aa9569dcf08ca6b929a527c428039ab97ee3b9`; recipient `docs/delivery/recipients/neostation-470-skins-recipient.pem`. Do not reuse build 470.
- Actual IPA inspection verifies six versions, 34 cores, 76 sealed code/data/ABI image identities and 79 CI ad hoc signatures. Compiled Menu weak layout `f0 52` proves both page pointers weak (offsets 168 and 176); the new bytes are actually present. Windows `C:\Users\Coren\Downloads\NeoStation-Build470-a43a5704.ipa` has the same verified hash; old IPA preserved. No public release, physical iPhone or commercial 10-Yard Fight test is claimed. SideStore Apple re-signing remains required. The maintainer can now test this candidate; do not block it with redundant validations. Full evidence and limits: `docs/build470-investigation.md`.

## Build 471 — maintainer's native Nestopia startup fault, 18 October 2026

- The maintainer confirms 470 still crashes immediately and supplies application journals and a video. Native fault session `C419A406-62F6-4088-AA4B-AE83C56D9B1F` is SIGSEGV, PC `0x15e375cc8`; Nestopia image base `0x15e330000`, UUID `AB4FBC0A-FF62-367B-A96B-01480A9B8DAF`, exactly matches the actual 470 IPA. Offset `0x45cc8` is the first background-color lookup in `FilterNtsc::BlitType<unsigned int,32>`. The video separately shows Adventures of Lolo; the matching native journal concerns 10-Yard Fight. Do not conflate the sessions or diagnose the older PSX logs from this Nestopia trace.
- Proven source defect: `Ppu::Output::bgColor` is not initialized by construction/reset. Before a game's first palette write, the NTSC filter indexes its table with heap residue. An original test ROM reproduces the same function's SIGSEGV on nonzero Linux heap and passes after one line initializes the field from the current palette in `Ppu::Reset`. Canonical fix and exact upstream/source hashes: `native/nestopia/reset-background.patch`, `native/nestopia/source.json`; upstream revision remains 135dfa6. No valid skin/filter, cheat, preference or console feature is disabled.
- Compile Nestopia alone and preserve the other 33 cores, MoltenVK and system assets byte-for-byte. The targeted CI requires the exact old iPhone fault offset with the original ARM64 binary and nonzero heap initialization, five corrected video modes/reset, and six original-skin/native-control sessions. Record actual outcomes in `docs/build471-nestopia-reset.md`; compilation or historical 470 launch counts are not hardware validation. The separate 470 ARC retention correction remains in place.
- Continue reusing successful checks of unchanged app/skin/cheat/other-engine inputs. New evidence justifies the focused Nestopia regression, not a repeat of all previous suites. Do not request system crash reports. Run `39081741396` / test source `a518034e826258b1e2aa20f7abddb00d750411b4` passed the exact original ARM64 SIGSEGV at `0x45cc8`, all five corrected video modes with 120 frames/reset each (600 frames), and six production skin/native-control sessions with deterministic pre-construction allocation poisoning. Reuse this acquired evidence; do not repeat it. Compiled core source remains `c3408821b2b9c47c6e31ae25b45c113aa9fd3f74`, SHA-256 `1a04f99e5ae2c10aa5b3c75b002e212e894c2e7934cc46232deb50da62c0e16d`; after this artifact was preserved, subsequent test-harness corrections reused it without rebuilding any core. Private IPA **0.0.7 (471)** delivered from `9429a1627a2f72dddc07a5fe3c4cda35cdbd7db9`, run `39082560152`: checks/native/cold succeeded; warm skipped. File `NeoStation-Build471-9429a162.ipa`, 218,606,105 bytes, SHA-256 `8484d2003a35de7c4ddedc199f9be9c80d540222b3fe2ca3e21e09c0f123682c`, verified locally and at `C:\Users\Coren\Downloads\NeoStation-Build471-9429a162.ipa`; older IPAs retained. Actual packaged Nestopia UUID `2321DDEC-E187-3AC6-80FD-C94C63C718C0` matches the corrected tested code/data/ABI. All 33 other core payloads and MoltenVK remain unchanged. No physical iPhone validation or public release is claimed; SideStore re-signing remains required. **Do not reuse 471.** Full results, preparation failures, artifact identities and limits: `docs/build471-nestopia-reset.md`.


## Build 472 — common embedded return label, 18 October 2026

- The maintainer confirms the Build 471 Nestopia startup crash correction on their iPhone. The apparent inactive skins were caused by a connected controller; no skin/input change is needed.
- New video shows the common Flutter launch dialog displaying `Jeu en cours` when a native game view disappears. The sole product fix prepares the existing `closingGame` translation behind embedded iOS sessions, preserving actual session phases, native stop, cleanup, route removal and audio ownership. External game sessions keep their playing label.
- Product source `9b6d120e`; unchanged product with corrected harness `a5e8fe6ee42c53bd20a2ce6f8b96a763f59a262e`, successful run `39086239948` / job `117553304499`: 13 sequential return cases (six old controls, six corrected embedded returns, one external return), deferred cleanup/route/audio checks and 12 existing translations. First harness run `39085427665` timed out between isolated FakeAsync zones and is not accepted validation. Details: `docs/build472-close-status.md`.
- Reuse the exact delivered 471 native cores and previous unchanged evidence; do not rebuild cores or rerun successful unrelated suites. No physical device run of 472 is claimed. The requested next IPA is Build 472; final delivery identity is recorded after verification.

- Build 472 delivered privately from `02550f923dd2d086227e9f379a896c23ef6670ac`, run `39086364895`: checks/native/cold Release success, optional warm skipped. Final IPA `NeoStation-Build472-02550f92.ipa`, 218,606,012 bytes, SHA-256 `b47d59188f28b5c6e70de11207b77fe7a81f91f13ebecc5a53d08c5c49455b26`. Actual IPA verification confirms new Dart AOT, all six versions, 76 sealed thin images, 79 CI ad hoc signatures, all 34 Libretro cores and RPCS3/Dolphin/ARMSX2 identities preserved from 471. Windows Downloads copy has the same hash and preserves old IPAs. No physical 472 run or public release claimed. **Do not reuse build 472.**


## Build 473 — optional first-run iOS library, 18 October 2026

- The maintainer requests a visible skip action for users without RetroArch. The only product file is `lib/widgets/setup_wizard.dart`: expose the existing twelve-language Skip action on the iOS folder step, keep the established scan/next/finish flow and do not register an arbitrary external folder. Block touch/gamepad Skip during a pending picker/import/download/save and cancel the post-frame scan after disposal.
- Run only the new setup-navigation proof. Reuse Build 472's common return-label evidence and all previously validated unchanged emulator/native/skin/cheat inputs. Do not rebuild any core. Delivery source, CI and actual IPA identity are recorded in `docs/build473-optional-setup.md` after verification; do not reuse number 473 once delivered.

- Private Build 473 delivered from `881c8df6bcffbdd0e4c3f5a32fd66492830f6dd1`, run `39088132898`: checks/native/cold Release succeeded; optional warm skipped. First-run proof `97fdd006`, run `39088013240` / job `117558563397`, passed all seven scenario groups and twelve skip labels. Final `NeoStation-Build473-881c8df6.ipa`, 218,615,292 bytes, SHA-256 `ab4ca98e5aa7221a824591c39fb7e277cda3c1e7df6ca14c44c4922205376054`, independently verified locally and in Windows Downloads. New Dart AOT is present; six bundle versions, 76 sealed thin images and 79 CI signatures pass. All 34 Libretro cores, RPCS3/Dolphin/ARMSX2/MoltenVK code/data/ABI stay identical to 472. No physical iPhone validation or public release is claimed. **Do not reuse 473.** Full evidence and the guarded local download/decryption sequencing error are recorded in `docs/build473-optional-setup.md`.

## Unified cheat catalogue integration — 18 October 2026

- The maintainer authorizes the full researched source list and fourteen complements on `Claude`, explicitly including ARMSX2, RPCS3 and Dolphin iOS alongside Libretro. Provide the reviewable inventory of sources actually unified before publishing a new IPA, as requested. Successful catalogue CI alone is not an IPA delivery receipt.
- Shared service/browser: `packages/neo_cheat_catalog`. Publish the deterministic `native/cheats/catalogue/manifest.json.gz` and its verified packs; the raw JSON is a build intermediate. One install/update action covers all published packs and retains partial successes. Keep source authors, licences, revision scopes, whole ordered programs and dependencies. Display download and estimated offline storage sizes.
- Latest steering: unavailable catalogues may be removed; before removing incompatible catalogues, try real format conversions or adapters for the engines present in NeoStation and record the concrete result. Keep usable portions of partial sources. Research history, attempted adaptations and remaining exclusion reasons belong in the audit; unimplemented engines and non-executable programs must not inflate the active download.
- Use typed identities and their exact hash schemes. A known conflicting region, language, revision or comparable hash is read-only; uncertain editions require confirmation. Never activate cheats during download/import/session launch. Unimplemented engines, ambiguous parameters and oversized programs remain explicitly unavailable rather than truncated.
- Existing native Core payloads are reused. RPCS3 uses optional exports already present in the pinned ABI 30 binary and applies explicitly selected patches at the next launch; preserve personal patch files and recover journaled global files. The delivered Azahar cheat entry points are no-ops and are not enabled by this catalogue. PPSSPP activation uses session overrides only, starts disabled before initialization, and must not leak into saved options.
- Run `.github/workflows/unified-cheats.yml` for changed data, identity/adapters, actual Apple SDK/Foundation/UIKit and the new PPSSPP/N64 RAM probes. A commit tagged `[unified-cheats]` uses those focused gates and reuses the recorded successful unchanged skin/shader/other-engine checks. Do not count a skipped historical job as a fresh pass. Source pins, real results and limits belong in `docs/unified-cheats-integration.md`; do not claim iPhone gameplay from compilation or Simulator results.


## Build 474 — unified cheat catalogue private IPA, 18 October 2026

- After reviewing the 70-source inventory and fourteen complements, the maintainer explicitly authorized the next private IPA. Build 474 includes the unified catalogue for Libretro, ARMSX2, RPCS3 and Dolphin iOS; no public release is authorized.
- Delivered source `b3c83af81e362718a63c73b048d797d8c21654cf`, run `39097173122`: checks/native provenance/cold Release succeeded, warm skipped. Exactly one device IPA compiled (305 seconds); successful prior component suites were reused by exact source and toolchain identity.
- Final `NeoStation-Build474-b3c83af8.ipa`, **225,395,532 bytes**, SHA-256 `d752791907aeffbab0a70e679b5d3e51e6e4168c8f81a015ab564835276c0dce`. Encrypted artifact `12125610664`, ZIP SHA-256 `5e0aa74c19c3921898af8004cfc345e8c6fa59a257eb49d44214d7a881f73696`; recipient `build-utils/delivery-474-recipient.pem`, private key outside Git. The verified IPA was saved as a downloadable file for the maintainer. **Do not reuse 474.**
- Actual IPA inspection passed both checksum records, six bundle versions, 77 sealed thin-image fingerprints and the exact final unified index; CI verified 80 ad hoc signatures. The shared implementation and all four compiled consumers are present. All 34 Libretro cores and the other engine artifact pins remain identical to delivered 473; no Core rebuilt.
- The old RPCS3 input guard encountered the new optional host declarations. A temporary exact input view now isolates only the SDK-tested optional block, requires the remaining header and every other published Core input to match the original pin, and preserves the authentic identity. Main-ABI/storage mutation controls were rejected. Earlier preparation failures, all source/run identities and the final fingerprint ledger are retained in `docs/build474-unified-cheats.md`.
- SideStore Apple re-signing remains required. No physical iPhone or catalogue-wide commercial gameplay validation is claimed; compilation and metadata/UI/decoder proofs remain distinct.

## Build 475 candidate — direct per-game cheats, 18 October 2026

- The maintainer explicitly authorized the simplified cheat architecture and delivery of a new private IPA. Final application/manual-import snapshot `f7c2d70b9e97c59d03f357185308e19399364d64` passed actual SDK/UIKit run `39101802667`; product/data snapshot `fabbdebda0761cb819cd250baee6dfc8f686fb25`; native adapter/binding snapshot `b157f557fe13b077d92afdd4ef1146c60982235d`; active/retired transport fixture corrected at `6b56a8b5bb7b1b0c13e232f61e48c41908c840d2`. Work remains on `Claude`; no public release is authorized.
- Direct named switches and only bulk-download/import actions replace the manual catalogue browser in the native flow. PS2 gameplay and graphical patches are separated; FBNeo prepares exact-driver installed INI before first option declaration. Imports remain disabled. RPCS3 captures the retained Core's exact PPU executable log and stages changes for the next boot, without live JIT writes or a Core rebuild.
- Coverage now includes authored GoW3 01.00 programs, same-PPU 01.03 static ports and four reviewed Bladestorm 01.00 static instruction programs (BLES00113/BLUS30070), with real observed-PPU binding and candidate confirmation where source proof is incomplete. No generic NCL pointer/freeze interpreter is claimed. Source inventory, exact scope and limits: `docs/unified-cheats-direct-build475.md`.
- Frozen publication: 2,353,283 programs/variants, 44,789 transport parts, 43,647 identity groups, 858 packs. Index SHA-256 `ff64b3b92225f5ab6960e1931fadaf4509665864a4470fb36908cc2faf22d792`; full audit `032950997212a242fb584db4f6de72dc562522c532c8ad9336f79b2d04b4b93f`, zero anomalies. Retired immutable pack members are hash checked but never selectable or counted as active programs. Twelve-language product labels remain mandatory.
- Preserve all pinned Core/native helper identities and the protected library/NeoSwap sources. Reuse successful unchanged components; initial failed UIKit and retired-member fixture results remain recorded, with their corrected targeted successors. Automatic/Simulator checks are not physical iPhone gameplay validation.

- Build 475 delivered privately from `69dd419030024e18457464d6a4b0e580bd5f6058`, run `39102171744`: checks/native/cold Release succeeded; optional warm skipped. Exactly one device IPA compiled (183 seconds), no Core rebuilt. Final `NeoStation-Build475-69dd4190.ipa`, **225,470,910 bytes**, SHA-256 `cc69b5dc8c04a3217db2dd3374d81384e5ae365e7198907464888817428b4cf9`; encrypted artifact `12126798816`, ZIP SHA-256 `4abf1148ff735dde66284618631b094665940b05285fe9f8307a109f984f5429`. Actual IPA inspection passed both checksum records, six versions, all 77 sealed thin-image fingerprints, final index/MIT notice/direct lists/PPU binding/arcade discovery; CI verified 80 ad hoc signatures. The 34 Libretro cores and other engine/helper pins are preserved. Details: `docs/build475-direct-cheats.md`, `docs/evidence/unified-cheats-direct475.json`. SideStore Apple re-signing remains required. No physical iPhone gameplay or public release claimed. **Do not reuse 475.**

## Build 476 — PS2/PS3 catalogue follow-up, 18 October 2026

- The maintainer reports empty PS2/PS3 direct lists and ineffective download actions in 475, with three screenshots. Correct the runtime on `Claude` and provide a private test candidate; no public release is authorized.
- Confirmed PS2 rupture: PCSX2's formatted disc serial and the normalized PNACH serial were rejected as different by the catalogue. Normalize only valid typed PS2 disc serials, preserving different serial/CRC/version/hash rejection.
- Confirmed upgrade rupture: a nonempty old downloaded index indefinitely hides newer bundled PS3 entries. Adopt each bundle publication once, retain later explicit remote updates, preserve installed chunks and user patch files, and avoid retaining two full parsed index trees during an emulated game.
- The in-game action uses the validated local index, prioritizes matching packs, reuses verified offline files and exposes progress/failure in the visible row. Refresh current-game codes before the entire bulk download completes. A protected PS3 mutation route must disable switches with its existing translated explanation, rather than conceal matching installed codes.
- Exact-source negative reproduction, Foundation PS2/PS3 downloads and offline/upgrade checks, changed iPhone SDK compilation and seven targeted UIKit cases are required. Preserve all published data and pinned cores/helpers; reuse unchanged successful 475 checks. Simulator or compilation success is not physical iPhone gameplay proof. Coverage gaps in Budokai 2/Dynasty Warriors 5 and other editions are not fixed by inventing source identities or applying another region's codes. Report the concrete remaining coverage limits.
- Source/run/artifact receipt and any retained failures belong in `docs/build476-ps2-ps3-cheats.md`. Reserve 476 for this candidate; final delivery is recorded only after actual IPA verification.

- Private Build 476 delivered from `314da5e0b40602c50621eb73ec740eb7c9b4da4f`, run `39106631911`: checks/native/cold Release succeeded, optional warm skipped. One IPA compiled in 292.666 seconds, no Core rebuilt. Final `NeoStation-Build476-314da5e0.ipa`, 0.0.7 (476), **225,475,478 bytes**, SHA-256 **c6055f9a6ba6a5353a42404e420dffa066e8df63680031a439123d3e3b19d052**. Encrypted artifact `12129216361`, ZIP SHA-256 `30a6652e24d9a59661d7a02d71d73c0cc374cfa8b65dc83f068f730ad10bb43b`; recipient 476. The downloadable file and Windows Downloads copy have the same independently verified identity; temporary task files were removed and older IPAs preserved.
- Actual IPA inspection passed both checksum records, six versions, packaged source stamps, all 77 sealed code/data/ABI fingerprints, unchanged final index/MIT notice and compiled follow-up selectors; CI verified 80 ad hoc signatures. The 34 Libretro cores, four other Core frameworks, RPCS3 Core and MoltenVK remain unchanged from 475. Final targeted service run `39106305814` passed 250 Foundation checks and changed iPhone SDK compilation; unchanged guarded UIKit source reuses seven passing tests from `39106115226`, menus/API reuse `39105809611`. No skipped step is a fresh pass. SideStore Apple re-signing remains required; no physical iPhone or public release claimed. Budokai 2/Dynasty Warriors 5 and unsupported PS2 editions remain coverage gaps. **Do not reuse 476.** Full receipt and retained preparation failure: `docs/build476-ps2-ps3-cheats.md`, `docs/evidence/cheats476-delivery.json`.

## Build 477 — common installation and missing PS2/PS3 editions, 18 October 2026

- The maintainer confirms GoW3 codes are detected in 476, while Bladestorm/PS2 remain empty and another console again proposes downloading the catalogue. Correct on `Claude` and deliver a new private IPA. The maintainer explicitly authorizes additional PS2/PS3 source research. No public release is authorized.
- One installed catalogue and one running download are common to all hosts. Recover actual existing files after an interrupted metadata checkpoint, expose a shared completed/running/partial state, block duplicate completed/running actions, and resume only missing content. Retain verified files and source identities; no duplicate download or expansion per immutable pack when bulk and current-game requests coincide. Give the newly opened game priority without blocking ready-code reads.
- Test the exact delivered 476 negative control and the real published Bladestorm/PS2 chunk bytes, common state across independent menus/relaunch, no second network/pack/file work, missing-only recovery and guarded native mutations. Run only changed checks; reuse successful unchanged 476 core/helper/library/NeoSwap/skin evidence. Do not rebuild emulator cores.
- Research and add only source-attested editions and executable complete programs. Preserve known serial/CRC/region/version/PPU conflict rejection and explicit uncertain-edition confirmation. Source review, actual outcomes and the final delivery receipt belong in `docs/build477-global-cheats.md`. Reserve 477; record delivery only after inspecting the actual sealed IPA.

- Build 477 service source `448c02cb72f50b4b5213a866655886221a8efc1a`, run `39109127858`, passed 352 accumulated Foundation checks, changed iPhone SDK compile/link and eleven UIKit cases. Final source/data/UI `49413f433031435affc70e2f04889eeb7ebf449c`, run `39109829873`, passed exact sixteen-program/five-edition native discovery/import/staging, changed iPhone SDK compilation and eleven final UIKit tests. Eleven repeated UIKit cases are not 22 distinct scenarios. Full-index memory result (44,794 rows, zero rejected, +16,384 bytes after ten menu reads) is reused from the identical service/index at `db6b9bc9`, job `117622682323`; later fixture expectation failures in that run and its successor remain documented.
- Reviewed supplement: source-declared RAW for European Budokai 2 SLES51839, GoW SCES53133, GoW II SCES54206, Hobbit SLES51723 (eleven programs), plus Artemis Bladestorm BLJM60009/01.00 (five static instruction programs). All 44,789 previous rows and 858 packs retain their identities; one new 4,720-byte pack. New index SHA-256 `46c4ada5ae6275e57a921f7651d8c3983022b0e5d812587120000c02a8f94f7f`: 44,794 rows, 859 packs, 2,353,299 programs, 39 contributing sources. No CRC/PPU is invented. Known different versions remain excluded; French Dynasty Warriors 5 and unsupported Bladestorm revisions remain gaps.
- Private Build 477 may proceed using exact closed proofs and unchanged successful 476 core/helper/library/skin evidence. Final sealed IPA identity and Downloads receipt follow after verification. No public release is authorized; no physical iPhone gameplay validation is claimed.

- Private Build 477 delivered from `38b3c681c575c7b9f0c05e01ef5a0f708cdd09f8`, run `39110222254`: checks/native/cold Release succeeded; optional warm skipped. One IPA compiled in 321.093 seconds, no Core rebuilt. Final `NeoStation-Build477-38b3c681.ipa`, 0.0.7 (477), **225,574,054 bytes**, SHA-256 **113347572e2c7b6b8699275d1f716d8276c97dcc2bdb15dda597af17ee534d8c**. Encrypted artifact `12129928423`, ZIP SHA-256 `9924d77f1da6bbe7f05211798114ce11c59133ae99dafa27be836217b320e968`; recipient 477. Both checksum records, six versions, source stamps, all 77 sealed fingerprints, actual updated index/common-state markers and 80 CI ad hoc signatures pass. The 34 Libretro cores/four other Core frameworks/RPCS3 Core/MoltenVK (40 images) remain identical to 476; only Runner/shared catalogue fingerprints changed.
- Downloadable IPA and Windows `C:\Users\Coren\Downloads\NeoStation-Build477-38b3c681.ipa` have the same independently verified identity. PC task files removed; older IPAs retained. SideStore Apple re-signing is required. No physical iPhone gameplay or public release claimed. Bladestorm 01.00 editions are covered; other revisions and French Dynasty Warriors 5 remain gaps. **Do not reuse 477.** Full receipt, source inventory and retained fixture failures: `docs/build477-global-cheats.md`, `docs/evidence/cheats477-delivery.json`.

## Build 478 — broader PS2/PS3 gameplay sources, 18 October 2026

- The maintainer requests a substantially broader PS2/PS3 cheat database and identifies the still-empty PS3 game as Bladestorm BLES00113. Work only on Claude. Preserve delivered 477 as a distinct binary and reserve 478 if a new private IPA is necessary for the changed bundled index or UI. No public release.
- Audit the exact BLES00113 path and source revision: the existing four public static programs are labeled 01.00; the actual installed APP_VER has not been supplied. More duplicate mirrors are not a fix for an edition mismatch. Do not port offsets or source versions by guess, invent CRC/PPU identities, weaken known-conflict rejection, execute unsupported NCL freeze/pointer/AoB instructions, or claim physical gameplay from native import checks.
- Integrate the maximum useful reviewed whole programs from source-attested PNACH collections and bounded static PS3 conversions. Preserve authorship, URLs, exact pins, complete conditional/payload boundaries and default-off behavior. Separate real gameplay codes from graphics-only packs; record unsupported bodies and source gaps honestly.
- Reuse all unchanged successful 477 core/helper/library/NeoSwap/skin evidence and precompiled engines. Avoid rebuilding/repartitioning unchanged catalogue files; only new missing content should download. Run focused source/data integrity, actual native acceptance and changed iPhone SDK/UIKit checks. Document sources, real counts, retained failures and exact delivery identity in docs/build478-source-expansion.md.

- The maintainer additionally requests available 60 FPS patches in Cheats for every embedded emulator. Preserve existing PSP/PS1/GC/Wii/N64/NDS coverage; add reviewed source-attested FPS selections and inventory the full publication. Do not present Azahar's no-op callback, unavailable Switch/Wii U/Flycast import paths, or configurable/unresolved patches as executable. Preserve source requirements and notes, no automatic emulator-setting change or activation.


- Private Build 478 delivered from `d0107bcdf15d08eaa2b3f72c5d97a87ef204f047`, run `39120442661`: checks/native/cold Release succeeded; optional warm skipped. One device IPA compiled in 264.228 seconds; no Core rebuilt. Final `NeoStation-Build478-d0107bcd.ipa`, **0.0.7 (478)**, **226,557,082 bytes**, SHA-256 **`c4114145aed4ea315a437efee14acb5d0e28d783e7d29d0e7ba4044a9a293700`**. Encrypted artifact `12134805502`, ZIP SHA-256 `9cab9137cca09baef0ba9826c5b8622cb0a87101ba27beb5d6549a6f0affffa2`; recipient 478. Actual archive passed both checksum records, six versions, source stamps, all 77 sealed fingerprints and 80 CI ad hoc signatures. Only Runner/shared catalogue/RPCS3 host bridge fingerprints change; all 40 precompiled engine images remain identical to 477. Downloadable IPA and independently verified Windows Downloads copy match; PC task files removed, older IPAs retained. SideStore re-signing required; no physical iPhone gameplay/public release. **Do not reuse 478.**
- Final 478 native/SDK/UIKit source `97bd841447263b0d345df7b1b98a345d7e838816`, run `39119945539`, passed all 42,250 new programs and fourteen distinct UIKit cases, with default-off source roundtrip and zero activation/Core mutation. Final index `a475a740a2e6251a5638077ffcce53c81afc125acd6fbcfaf97ff28d7602d1a1`: 2,395,549 program variants, 51,652 rows, 50,284 identity groups, 51 sources. Fifteen new packs/8,170,496 bytes; all 859 old packs and 44,794 old chunk hashes preserved. FPS inventory: 1,926 selections across PS1/PS2/PS3/PSP/GC/Wii/NDS, including 1,392 new selections. BLES00113 remains source-attested only for 01.00; other versions, French Dynasty Warriors 5 and unsupported engine paths remain gaps. Exact proof reuse, retained preparation failures, source inventory and final receipt: `docs/build478-source-expansion.md`, `docs/evidence/cheats478-delivery.json`.

## Build 479 — fast edition-specific cheats, 18 October 2026

- The maintainer confirms installed 478 detects Bladestorm BLES00113 as 1.01 and requests matching updated codes, much faster PS2/PS3 loading, no duplicates and only compatible regional/version results. Work on Claude; reserve 479 for a new private IPA. No public release. Preserve all precompiled engine/helper inputs, library, NeoSwap and the published 478 pack bytes.
- Eliminate the catalogue-wide per-file stat pass from installed-menu loading, index typed IDs, stop automatic title fallback once an ID is detected, and show ready complete programs incrementally without automatic activation. Keep known identifier/CRC/PPU/version/region/language conflict rejection. Consolidate only equivalent complete executable programs, retaining source data and requirements; do not erase active native imports or infer an edition from its title.
- Source research currently attests BLES00113 static programs only for 01.00. Do not relabel those addresses as 01.01 or present AoB/save-file instructions as an executable supported runtime patch. Record the gap if no actual 1.01 source is found. Focused old/new metadata/performance and native/UIKit proofs are required; unchanged source-program and Core/helper evidence is reused. Record exact source, outcomes and delivery in docs/build479-fast-cheats.md.

- Private Build 479 delivered from `ff28cf2a63695400ad09d1c61538059d96992cc1`, run `39127133775`: checks/native/cold Release succeeded, warm skipped. One device IPA compiled in 318.391414 s; no Core rebuilt. Final `NeoStation-Build479-ff28cf2a.ipa`, 0.0.7 (479), **226,564,742 bytes**, SHA-256 **`a1c44f59c80fa98f4d5a0fa7a59885e2b8269fc3666f40b23a805a0528f1b742`**. Encrypted artifact `12136797752`, ZIP SHA-256 `d0128803610876e153e71894c2acad029b1c20ce803d0de51141a4867ca36261`. Actual IPA passes both checksum records, six versions, source stamps, all 77 sealed fingerprints, the unchanged index/new lookup-streaming markers and 80 CI ad hoc signatures. Only Runner/shared catalogue fingerprints change; all 40 engine images remain identical to 478. Downloadable and Windows Downloads copies match; PC task files/private key removed, older IPAs retained. SideStore re-signing required; no physical iPhone or public release. **Do not reuse 479.**
- Final List/SDK/UIKit source `302f019e949e023fa23b5f94f30d2112c0feaaea`, run `39126577930` / job `117672864750`, passed changed iPhone compilation and all nineteen distinct targeted UIKit scenarios, with all 86 keys in twelve languages. Exact unchanged service source `ce585c6bef0f3f714a7dc0f5c005191f74df4c9a`, run `39125808369` / job `117670567809`, reuses only successful service/352-installation-check/full-index-memory components, not its failed UIKit result. Full 51,652-file metadata fixture: 6.336124 → 2.786468 s cold, 0.695685 → 0.222425 s for twelve warm lookups, 51,652 → zero initial per-file checks. These are macOS fixture measurements, not iPhone timings. Catalogue/program bytes/FPS inventory are unchanged; BLES00113 01.01 remains a coverage gap and source 01.00 codes stay excluded. Retained preparation failures and complete receipt: `docs/build479-fast-cheats.md`, `docs/evidence/cheats479-delivery.json`.


## Source credits and main promotion — maintainer authorization, 18 October 2026

- The maintainer explicitly requests all 51 unified cheat source entries in the README, proper source/author/license credit on GitHub, and promotion of the updated source tree to main without publishing an official release. Work is prepared on Claude, then main may be updated for this request. No tag, release asset change or new IPA is requested.
- Preserve the validated Build 479 runtime/catalogue and all main-only historical release records. Resolve obsolete main source conflicts with the newer delivered 479 implementations and preserve source notices; do not restore old core lists or replace the published 0.0.7 / Build 455 binary.
- The 51 entries are contributing import profiles, some sharing upstream projects. Source contributions overlap. Credit original code authors, preserve recorded rights and full license texts, and never treat unspecified cheat-data rights as a frontend GPL grant. The public English attribution register is docs/CHEAT_CATALOG_SOURCES.md.

## Source-rights follow-up — 18 October 2026

- The maintainer requests an actual resolution for Pokémon France, clearer embedded-engine provenance and missing overlay credits. Do not conceal attribution while retaining the same programs. Withhold that source pending established permission: remove its eight active programs and current raw excerpts, disable future publication and deny its source/import-tagged programs from older cached catalogue data. Keep historical credit and the explicit exclusion reason. Existing personal cheat files and previously distributed IPAs are not silently edited.
- The current publication has 50 active profiles, 2,395,541 programs, 50,282 identity groups and 51,650 transport records in 874 packs. Two packs are replaced, 872 and all unrelated chunk bytes remain unchanged. Receipt: docs/evidence/source-rights-withdrawal.json. Keep the 51-profile Build 479 figures historical.
- Overlay credits preserve all supplied CFG headers and applicable ancestor notices. New converted installations keep original CFG bytes, notice files and immutable source/license metadata. The attribution-only index refresh must preserve existing classifications, layouts and image lists. Runtime source evidence and remaining gaps are explicit in docs/EMBEDDED_RUNTIME_PROVENANCE.md; do not invent source pins for the 32 buildbot cores.
- Work on Claude and promote to main after the focused source-rights workflow succeeds. The commit carries [unified-cheats] [direct-rights]: the dedicated workflow runs real Apple Foundation + iPhone compilation and the affected Flutter/data checks; unrelated old native/UI/shader/engine suites are reused only as unchanged historical evidence. No new IPA or official release is requested.
## Build 480 — bounded scraping MD5, 18 October 2026

- The maintainer authorizes a targeted scraping crash correction and a new private IPA on Claude. The supplied app.log has five metadata-start / ROM-not-found / next-start sequences; the video stops at the first game's scanning phase. Its ISO copy is 3,363,110,912 bytes. The source defect is a complete native-file read before MD5. These observations do not prove the exact iPhone termination mechanism.
- Stream native file input through the existing crypto MD5 converter, preserve complete hashes, specialized console hashes and the Android SAF provider contract. Keep work off the UI isolate. Persist start/completion/failure diagnostics from the initialized caller logger. Do not require system crash reports; this existing permanent maintainer constraint also applies here.
- Run only changed hash/diagnostic checks: original-code whole-file-read rejection with a safe I/O guard, complete independent 3.36 GB reference digest and measured bounded RSS, concurrent workers, boundary/empty inputs and persistent app.log diagnostics. Reuse delivered 479 native/Core/helper/catalogue/skin evidence. Reserve 480; record actual test/IPA identities in docs/build480-scraping-md5.md. No public release.

- Build 480 final targeted source `fe610c9f92c62e5815950d1aecc460d1314ee87e`, run `39132169652` / job `117689389027`, succeeded. Original-code allocation control and corrected guard execute; four unchanged passed scenarios from `083d3deb`, run `39131858146` / job `117688482965`, are explicitly reused. That initial overall run remains failed due to the I/O wrapper's omitted File.open forwarding. The real 3,363,110,912-byte complete hash passed in 12,133 ms with +6,811,648 sampled RSS bytes on the Linux host; this is not an iPhone measurement. Preserve concurrent source-rights/provenance changes at `4c5eeba0` / `96459971` (successful rights run `39131701581`), including the reviewed post-withdrawal index and cached-source guard.

- Private Build 480 verified from `7493d9babe20be1b2939e21a1051a72da8fb5d01`, run `39132356516`: checks/native/cold Release success, warm skipped; one device IPA compiled in 320 seconds, no Core rebuilt. Final `NeoStation-Build480-7493d9ba.ipa`, **226,569,533 bytes**, SHA-256 **`a87c355491083f8e4c385f5c119f9a8e41ecd1738439747cd20dd38bdb2ba8f1`**. Encrypted artifact `12138711859`, ZIP SHA-256 `1c3276e895c66f07c9a94391f1ca5633eec492642e48e11025b907e0b1b20967`; recipient 480. Actual IPA passes both checksum records, source stamps, six versions, all 77 sealed fingerprints, AOT scraping markers, exact reviewed index and 80 CI ad hoc signatures. All 40 precompiled engine images remain identical to 479. SideStore re-signing required; no physical iPhone/Windows copy/public release claimed. Details and retained fixture failure: `docs/build480-scraping-md5.md`, `docs/evidence/scraping480-delivery.json`. **Do not reuse 480.**


## Public release 0.0.8 — maintainer authorization, 18 October 2026

- The maintainer confirms the Build 480 scraping correction resolved the reporter's problem and explicitly authorizes the approved English release message, public IPA and promotion to main. The final requested public version is **0.0.8**, not 0.8 or 0.08. This authorization supersedes historical private-only restrictions for this publication.
- Main was safely advanced from 8e966ca to 626a8e3 with the validated scraping fix and delivery receipt. Prepare release packaging on Claude and promote that reviewed commit to main. Preserve all previous releases and source histories.
- Repackage the exact verified Build 480 with marketing version 0.0.8 in the host and five extensions, retaining internal build 480, compiled host/native/AOT code, source identities, catalogue and resources. This is metadata/signature packaging of the same compiled build, not another code build numbered 480. Compare all 77 thin and three universal Mach-O images and verify final archive, signatures and versions. Reuse unchanged successful gameplay/component evidence; no core rebuild or redundant suite.
- Publish only after the packaging workflow succeeds, with the IPA, checksums, actual notices and source/packaging records. Keep the old 0.0.7 release and its assets intact. Documentation: docs/RELEASE_0.0.8_SOURCE_MANIFEST.md.

## Décision du mainteneur — Build 481, cache d'objets SPU ARM64 (RPCS3), 18 octobre 2026

- Mission : analyser l'IPA `ARMSX3-22185-00412bb6.ipa` (Harness, SHA-256 `69b71ae8…f177c`) et son annonce, porter ce qui réduit les saccades et augmente les FPS calculés de God of War III, livrer une IPA privée. Candidate : Build 481 par-dessus la 0.0.8 (Build 480, `7493d9ba`). Décisions, audit et protocole : `docs/build481-plan.md`.
- Établi : le cache d'objets SPU d'ARMSX3 est public (`ARMSX2/ARMSX3` `master` `58074a7c`, porté de ouroboros420/rpcsx) mais désactivé sur ARM64 par son auteur le 31 août 2026 (`457a932c7` : `IntToPtr(getInt64(&g_timebase_offs))` figeait une adresse hôte) ; la build iOS du 18 octobre (40 000 fichiers, éviction des plus anciens) vient d'un commit non publié (`00412bb6` ne résout aucun commit public). Notre traducteur ne figeait qu'une seule adresse hôte (`SPU_RdDec`) ; tous les autres renvois sont des symboles MCJIT. Le chemin PUTLLC 16 octets (Yahfz, RPCS3 PR #19568) est déjà dans nos sources ; notre cache pipeline Vulkan conserve déjà la copie disque au-delà de 128 Mio avec écriture atomique et validation d'en-tête : aucun changement. Les marqueurs `ARMSX3_*` sont des variables d'environnement d'expérimentation désactivées par défaut ; `ARMSX3_SPU_TSC_SCALE` n'a pas de source publique.
- Changements (Core seulement, patch canonique `bc63c5da2dc97dca0f205b132dfb078d53da3d87c6fcf546810468512dd37a33`) : symbole `spu_timebase_offs` ; garde de relocalisabilité (`spu_llvm_module_is_relocatable`, toute conversion en pointeur d'une constante ≥ 4 Gio refuse la persistance, compte `obj_nonreloc`) ; objets parsés et symbole d'entrée exigé avant MCJIT (fichier invalide supprimé, recompilation) ; un hit saute passes, abaissements ARM64 et vérification ; clé = format 6 + réglages + bits matériels + TSC + CPU + identité de codegen SPU (version LLVM, digest CMake `NEOSTATION_SPU_CODEGEN_ID` de 20 sources, attributs cibles) + révision ; répertoires d'autres clés supprimés ; bornes 40 000 fichiers et 512 Mio, éviction des plus anciens à 90 %, jamais de purge d'un cache valide ; suffixes `-notbl2`/`-nofma` ; réglage « Persistent SPU object cache » `Automatic` → activé sur ARM64 ; `JITPROF` gagne `spu_cache_read`/`spu_object_load`/`spu_cache_write`, `SPUPROF` gagne les champs `obj_*`. Module interpréteur non persisté ; compilation SPU différée toujours désactivée ; aucun changement StikJIT, ABI, NeoSwap, mode de shaders, profils, autres moteurs.
- Constat annexe non traité : le défaut global iOS du mode de shaders est « Legacy Recompiler (single-threaded) » ; God of War III est déjà asynchrone par son profil. Un changement global demande une mesure iPhone séparée.
- Preuves hôtes : `test/rpcs3_build481_spu_object_cache_test.py` (politique exécutée, preuve MCJIT en **deux processus** à adresses différentes avec le LLVM 22 du runner Core, câblage) ; test 444 étendu à 15 phases ; anciens ancrages de `rpcs3_spu_warmup_test.py` et `rpcs3_build258_runtime_resilience_test.py` déplacés vers le nouveau contrat (aucune assertion affaiblie). Le premier run Core `39142102313` s'est arrêté au préflight sur l'ancrage du test de préchauffage ; corrigé par `e731ed95`.
- Aucun journal ni appareil dans ce cycle : gains de démarrage et de saccades de compilation attendus à partir de la deuxième session, aucun gain de FPS en régime chaud prétendu. Retour arrière sans perte : réglage `Disabled` ou réinstallation de la 0.0.8 (son Core ignore `spuobj-v6-*`).
- Core 481 construit par `rpcs3-core.yml` run `39144244183` sur `5919be61` (préflight avec preuve de relocalisation en deux processus, LLVM 22.1.8 ; runs `39142102313`, `39142620900` et `39143262614` arrêtés sur d'anciens ancrages de tests, tous déplacés vers le nouveau contrat), identité SHA-256 `b249523453b3c3188b2f849b1bd87187d259511612170c9167b9420678aef01d`, identité de codegen SPU `72b3b9b3c7883b23`, épinglé dans `retroarch-delivery.yml` et `neoswap-ipa.yml`. La livraison passe par `.github/diagnostics/spucache481_delivery.py` (produit = 0.0.8, entrées du Core identiques à `5919be61`, preuve du préflight exigée).
- Livraison 481 vérifiée : source `839d114763e80a9945d162369e8d8f258bb82485`, run `39148545918` (`checks`, `native` réutilisés, `cold` réussi), artefact `12144109952` chiffré pour `build-utils/delivery-424-recipient.pem`, IPA **0.0.8 (481)** `NeoStation-Build481-839d1147.ipa`, **226 578 252 octets**, SHA-256 **`342f3c02d8bb0902008c6b4cd23d8312706b08860f976c17cd489f97ceac489f`**. Inspection indépendante : 31 sections du Core de l'IPA identiques au Core de l'artefact (seule la signature diffère), 72 images identiques à la 0.0.8 dont les 34 cœurs libretro et le code Dart, DolphinCore et les cinq extensions identiques hors signature. Aucune validation iPhone. Ne pas réutiliser le numéro 481. Voir `docs/build481-plan.md`.

## Build 482 — précision du blending PS2 (ARMSX2, ABI 7) et information Get More RAM avant le firmware PS3, 18 octobre 2026

- Demande du mainteneur : exposer le réglage « Blending Accuracy » d'ARMSX2 dans les paramètres graphiques PS2 et par jeu, uniquement avec les niveaux réellement pris en charge par le moteur embarqué ; afficher avant toute installation ou réinstallation du firmware PS3 l'information « installez l'application Get More RAM… puis revenez dans NeoStation » ; livrer une IPA privée. Candidate : Build 482 par-dessus la 481 (`839d1147`). Plan, sources amont lues, vérifications et identités : `docs/build482-ps2-blending-ps3-ram.md`.
- Établi dans les sources ARMSX2 `9d989ca9` : clé `EmuCore/GS` / `accurate_blending_unit` (0 Minimum … 5 Maximum, défaut Basic) ; sous `TARGET_OS_IPHONE` le device Metal n'a ni barrière de texture ni copie multidraw, donc **Medium rend exactement comme Basic** (`GSRendererHW::EmulateBlending`) : seuls Minimum, Basic, High, Full et Maximum sont offerts (`core/ARMSX2BlendingAccuracy.h`) ; une clé par jeu présente fait sauter les clamps GameDB (`PerGameOverrides.cpp`), d'où l'ordre défaut (`PCSX2.ini`) → profil GameDB → choix du jeu ; `applyGraphicsSettingsNow` → `VMManager::ApplySettings` applique en direct, sans redémarrage.
- Règles posées :
  - le Core est la seule autorité sur les niveaux offerts (`levels` du JSON) ; le menu n'ajoute jamais un niveau ; un niveau hors liste (Medium compris) est refusé par le Core sans écriture ; une valeur déjà écrite par un autre frontend est rapportée, jamais réécrite ;
  - les écritures passent exclusivement par les accesseurs INI amont (`setINIInt:` + `flushINISettings` pour le défaut, `setPerGameINIInt:`/`deletePerGameINIValue:` pour le jeu) sur le thread CPU ; jamais le pin global des hacks ; la ligne « Appliquée actuellement » lit `EmuConfig.GS.AccurateBlendingUnit` après la GameDB ;
  - l'ABI ARMSX2 passe à 7 ; un Core 6 est refusé ; le workflow `armsx2-core.yml` compile l'adaptateur de blending (test Foundation/MRC à deux jeux) et le menu réel sur UIKit avec les classes du catalogue de cheats ; sa vérification de syntaxe prépare les en-têtes des pods (`stage_dependency_headers`) ;
  - le dialogue PS3 (`showRpcs3FirmwarePreflight`, douze langues dans `rpcs3_firmware_locale.dart`) précède chaque sélecteur de firmware (porte de bibliothèque, menu Importer, écran RPCS3) ; Continuer n'est qu'une prise de connaissance et le texte le dit : NeoStation ne vérifie pas la capacité « Increased Memory Limit » ; Get More RAM (`https://github.com/hugeBlack/GetMoreRam`, README vérifié) est distingué du fichier `PS3UPDAT.PUP`.
- Livraison 482 vérifiée : source `c676b31710c50cfc60ca3e356aecd49995fe0a76` (source testée `da091fa7`, Core ARMSX2 run `39155495662`, contrôles ciblés run `39155497540`), run `39157242359` (`checks` et `native` réutilisés, `cold` réussi), artefact `12147865982` chiffré pour `build-utils/delivery-424-recipient.pem`, IPA **0.0.8 (482)** `NeoStation-Build482-c676b317…-cold.ipa`, **226 608 707 octets**, SHA-256 **`1a220c8ae64ce7cb1ba46bb3595c6d58ea5cc9fe426366284bb5c8d87c6d2f6b`**, égal à `SHA256SUMS` et à `signed-payload-identity.json` ; Core ARMSX2 de l'IPA identique section par section (36/36) au framework de l'artefact du run Core ; copie `C:\Users\Coren\Downloads\NeoStation-Build482-c676b317.ipa`. Aucune validation iPhone. Ne pas réutiliser le numéro 482. Voir `docs/build482-ps2-blending-ps3-ram.md`.

## Décision du mainteneur — Build 483, pipelines LLVM des recompilateurs RPCS3 (God of War III), 18 octobre 2026

- Mission : campagne d'optimisation LLVM pour les scènes lourdes de God of War III (traducteurs PPU/SPU, pipelines IR, backend ARM64, chemins chauds), au moins trois pistes, sémantique PS3 préservée, caches cohérents, variantes sélectionnables avec retour à la référence, IPA de test. Candidate : Build 483 par-dessus la 482 (`c676b317`, Core 481). Contraintes : travail sur `Claude`, aucune release ni poussée sur `main` sans accord ; diagnostics internes de NeoStation seulement ; chemin différé de la Build 435 toujours désactivé. Audit, pistes, mesures, protocole et retour arrière : `docs/build483-llvm-pipelines.md`.
- Établi dans les sources : la seule différence de pipeline IR entre la build iOS d'ARMSX3 et la nôtre est **InstCombine sur les blocs SPU** (amont RPCS3 `eda7621f` « Restore SPU InstCombine with matching helper calling conventions », ARMSX3 `ab53473f7`) ; notre base ne l'exécutait pas et appelait `m_test_state` sans la convention `PreserveMost`/`PreserveAll` de sa définition. InstCombine efface un appel direct dont la convention diffère de celle de la fonction définie (store vers poison, « unreachable non terminal », `InstCombineCalls.cpp` identique de LLVM 18 à 22) : le contrôle d'état SPU disparaîtrait. Côté PPU, ni l'amont (`#ifdef ARCH_X64 // TODO` de kd-11 `56cc5d93`) ni ARMSX3 n'exécutent de passe IR sur ARM64.
- Changements (Core seulement, patch canonique `0fd83bccbdcfbe079236b47e1e3ebd674c70ecb06a2092f426cc88d0b769d843`, marqueur `NEOSTATION_BUILD483_LLVM_PIPELINES_V1`) : réglage **SPU LLVM pipeline** (`Upstream InstCombine` par défaut = EarlyCSE, SimplifyCFG, InstCombine, DSE, LICM, ADCE ; `Reference 481` = pipeline précédent) avec les deux appels `m_test_state` portant la convention de leur cible et le pipeline plié dans la clé du cache d'objets 481 ; réglage **PPU LLVM pipeline (ARM64)** (`Upstream ARM64` par défaut = aucune passe ; `EarlyCSE` = booléen 444, toujours accepté ; `Extended` = pipeline SPU) nommant ses objets par les bits `arm64_ir_passes`/`arm64_ir_passes_extended`, `PPUThread.cpp` ajouté au digest PPU ; `JITPROF … ppu_pipeline= ppu_ir_passes= spu_pipeline=`. Catalogue du Core en anglais comme ses autres entrées. Aucun changement de backend, de CPU cible, d'attributs ni de `fast-math` ; compilation SPU différée toujours désactivée.
- Conséquence certaine : un premier démarrage long par titre après l'installation (identités PPU et SPU changées : recompilation complète, nouveau répertoire `spuobj-v6-<clé>/`, l'ancien restant sur place jusqu'à suppression manuelle). Retour arrière sans perte : `Reference 481` / `Upstream ARM64` dans les réglages, ou réinstallation de la 482.
- Preuves hôtes : `test/rpcs3_build483_llvm_pipeline_test.py` + `test/native/rpcs3_llvm_pipeline_harness.cpp` sur le runner Core (LLVM 22.1.8) : `cc-hazard` (InstCombine seul efface l'appel non apparié, le pipeline complet n'en laisse aucun, l'appel apparié survit) et `kernels` (sept noyaux synthétiques × cinq pipelines : vérification, comptes IR et AArch64 `apple-m4`, exécution MCJIT bit-exacte) ; câblage ; test 444 déplacé vers le sélecteur 483 ; balayage d'ancrages sans occurrence. Runs Core `39161571672` (ligne `define` du module `cc-hazard`) et `39162137490` (détecteur cherchant `unreachable` au lieu du store vers poison) arrêtés au préflight du harnais lui-même ; aucun test de Core affaibli. **Rien n'est mesuré sur l'iPhone** : les comptes d'instructions des noyaux sont des mesures hôte, pas des FPS.
- Core 483 construit par `rpcs3-core.yml` run `39163125594` sur `1b4f65e2` (préflight : preuve 481 en deux processus, porte de syntaxe iOS, harnais 483 réussi ; 72 min de construction, LLVM 22.1.8), identité SHA-256 `8db85fa174c8639b35be581fe3b8dca03ee996502f5e5ace3f169867f44a5b8e`, ABI 30, 69 entrées épinglées, identités de codegen PPU `8288754769446e6d` et SPU `36eabce56a6bbd8e` (toutes deux nouvelles : recompilation complète au premier démarrage de chaque titre). Épinglé dans `retroarch-delivery.yml` et `neoswap-ipa.yml` ; la livraison passe par `.github/diagnostics/llvmpipe483_delivery.py` (produit = Build 482 livrée, entrées du Core identiques à `1b4f65e2`, preuves 481 et 483 relues depuis l'artefact du run).
- Séquencement avec l'autre session : pendant la construction du Core, la branche `Claude` a reçu les commits de la Build 484 (éditeur de commandes tactiles, autre session). Le commit d'épinglage 483 est donc sur `Claude` **rebasé** par-dessus eux (`3eae482c`), et l'IPA 483 est produite depuis le **tag `build-483`** = commit `2c0e022f` (`1b4f65e2` + le même épinglage, même diff), pour que la 483 reste « application 482 + Core 483 » sans les changements 484 non validés. Aucune branche de travail créée, aucune force-push ; la 484 hérite du pin par la branche.
- Livraison 483 vérifiée : source `2c0e022f8cf0f95f732cc749d7a47444eb28d3f9` (tag `build-483`), run `39169474336` (`checks`, `native` réutilisés, `cold` réussi en 17 min, `warm` ignoré), artefact `12152521608` chiffré pour `build-utils/delivery-424-recipient.pem`, IPA **0.0.8 (483)** `NeoStation-Build483-2c0e022f…-cold.ipa`, **227 199 943 octets**, SHA-256 **`bb8c0f8efeaaf7d719670757624fb23fc595a754dba6680b8b02d9cd95e6e86c`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build483-2c0e022f.ipa` ; 80 signatures ad hoc, iOS 18.0 minimum, re-signature SideStore requise. Inspection indépendante contre l'IPA 482 : hôte et cinq extensions 0.0.8 (483), 31 sections du Core de l'IPA identiques au Core de l'artefact (seule la signature diffère), 72 images identiques à la 482 (34 cœurs libretro, code Dart, Core ARMSX2 ABI 7), DolphinCore et extensions identiques hors signature, Runner identique hors `__TEXT,__const`. Reçu : `docs/evidence/llvmpipe483-delivery.json` ; mesures hôte : `docs/evidence/llvm-pipeline-kernels-483.json`. Aucune validation iPhone. Ne pas réutiliser le numéro 483 (ni 484, pris par l'autre session).

## Build 484 — éditeur des commandes tactiles et masquage avec une manette (Dolphin, ARMSX2, RPCS3), 18 octobre 2026

- Demande du mainteneur : éditeur visuel des commandes tactiles de Dolphin iOS (GameCube et Wii, dispositions distinctes), ARMSX2 (PS2) et RPCS3 (PS3) — déplacer, redimensionner, opacité, masquer/afficher chaque élément, sticks indépendants, aperçu à taille réelle, enregistrer, annuler, rétablir — depuis les réglages de chaque émulateur et le menu pause ; dispositions par console, portrait/paysage, générale et par jeu ; option « Masquer les commandes tactiles lorsqu'une manette est connectée », activée par défaut ; une IPA de test. Aucune release, rien sur `main`. Construite par-dessus la Build 483 livrée (`2c0e022f`). Plan, vérifications, limites et protocole iPhone : `docs/build484-touch-controls.md`.
- Règles posées :
  - pod partagé `packages/neo_touch_layout` : une seule transformation par commande (échelle autour du centre, puis translation), donc dessin et zone tactile restent le même rectangle ; positions relatives à la zone sûre ; un utilisateur qui ne personnalise rien garde exactement les commandes actuelles, et une commande ni déplacée ni redimensionnée garde exactement la place que lui donne le moteur (aucune borne) ;
  - dispositions `Library/Application Support/NeoStation/TouchControls/<gc|wii|wii-classic|ps2|ps3>.json` (écriture atomique, clés inconnues conservées, fichier illisible mis de côté, jamais écrasé) ; préférence `NeoStation.TouchControls.<console>.HideWithControllerConnected`, activée par défaut ;
  - manette compatible = `GCController` avec profil `extendedGamepad`, non instantané ; règle commune `NeoTouchControlsShouldHide` (jamais masqué pendant l'édition) ; masquer, tourner, éditer ou fermer relâche toutes les touches et recentre les sticks ; pendant l'édition, aucune entrée n'atteint le jeu (Dolphin et ARMSX2 en pause, RPCS3 reçoit un pad neutre) ;
  - Dolphin refait sa mise en page (au plus trois fois de suite) quand le nib bouge une commande après sa mesure et prévient l'éditeur (`NeoTouchLayoutHostDidRelayoutNotification`) ; la garde de livraison de l'en-tête `DolphinSessionMenu.h` admet exactement le bloc des rappels de la page Commandes tactiles, le reste devant rester égal ;
  - 48 textes dans les douze langues (`tools/touch_layout/strings.json`, `--check` en CI). Aucun cœur reconstruit.
- Harnais réparés à la demande du mainteneur : `dolphin_recording_sdk`, `dolphin_touch_shake_ui`, `dolphin_pacing362_ui`, `dolphin_external_display_ui`, `cheat_editor361_ui` échouaient avant tout test depuis la Build 474 (`<neo_cheat_catalog/...>` non fourni, bundle `.xcresult` partagé non remplacé). Le harnais partagé `dolphin_account_267_test.py` prépare les en-têtes de tous les pods du pont, compile le catalogue sans Flutter et remplace le bundle existant ; aucune assertion retirée ni affaiblie. `external_display_ui_test.py` n'est exécuté par aucune porte (`external-display-check` s'arrête avant lui sur l'échec déjà présent de `external_display_host_plist_test.py`).
- Preuves ciblées (`touch-layout-checks.yml`, `test/build484_targeted_test.py`) sur la source testée `1ff09e96` : hôte run `39175673497` (40 vérifications, 113 entrées), natif run `39175671512` (12 vérifications, toutes réussies sans comparaison avec la base) ; UIKit run `39174427738` sur `79968b07` (35 tests en 3 processus, persistance relue par un autre processus) réutilisé, ses 60 entrées étant identiques. Les 13 scripts `PRE_EXISTING` et un cas de `dolphin_import_ui_test.dart` échouent identiquement sur la base.
- Livraison 484 : source `e76f40b77fb45e8ce23f161d5d4f4b0dd6fbf3f3`, run `39177384518` (`checks`, `native` réutilisés, `cold` réussi, `warm` ignoré ; premier essai `39176954590` arrêté par la garde de l'en-tête Dolphin, corrigée), artefact `12155081702` (227 601 821 octets, archive SHA-256 `4c9f743a7660ad8b2e582abf1dffa345c5d5e4821f859263fa0bce2676084598`, conservé jusqu'au 1er novembre 2026), chiffré pour `build-utils/delivery-424-recipient.pem`. IPA validée avant scellement `d6754b73f6d0fcb8bd34e7e6b01533013b34527ea463bdb09e9018cd80173964`, version 0.0.8 (484) ; SHA-256 de l'IPA scellée à relever après déchiffrement. Reçu : `docs/evidence/touch484-delivery.json`. Aucune validation sur iPhone ni avec une manette physique. Ne pas réutiliser le numéro 484.

## Build 485 — packs de textures HD PS2 (ARMSX2 embarqué, ABI 8), 19 octobre 2026

- Demande du mainteneur : importer et appliquer des packs de textures HD pour les jeux PS2 d'ARMSX2 embarqué, distincts des shaders, de la résolution interne et des patchs PNACH ; réutiliser le code du moteur ; activation réelle par jeu ; stabilité ; douze langues ; IPA de test après les autres compilations ; rien sur `main`, aucune release. Candidate : Build 485 par-dessus la 484. Sources, conception, vérifications et limites : `docs/build485-hd-textures.md`.
- Établi dans les sources ARMSX2 `9d989ca9` : le remplacement existe (`GSTextureReplacements`, `EmuFolders::Textures/<série>/replacements`, chargement asynchrone, budget `os_proc_available_memory()/2`, 16 Mo d'upload par image, changement appliqué en jeu par `GSUpdateConfig`) ; NeoStation n'y donnait aucun accès jusqu'à la 484.
- Règles posées :
  - un pack s'installe uniquement dans `ARMSX2/textures/<série>/replacements` résolu depuis la racine ARMSX2 de NeoStation ; seul ce dossier est remplacé ou supprimé (jamais `dumps`, jeux, sauvegardes, cartes mémoire ni états) ; préparation à part puis renommage atomique ; un échec ou une annulation laisse le pack en place ;
  - lecture en flux (jamais d'archive entière en mémoire), chemins refusés hors du dossier, espace vérifié avec 512 Mio laissés libres, bornes 100 000 entrées et 512 Mio par fichier, formats reconnus par leurs octets (PNG, DDS BC1–BC3/BC7/non compressé, ASTC, KTX ASTC) ;
  - avant toute écriture, l'utilisateur confirme un pack d'un autre numéro de série, d'une autre région ou d'un autre CRC cités dans les noms, ou un numéro de série déduit du seul nom de fichier ; aucune compatibilité n'est déduite d'un nom ;
  - l'interrupteur écrit `LoadTextureReplacements` dans l'INI du jeu par les accesseurs amont (activation : chargement asynchrone, jamais de préchargement complet) ; depuis la bibliothèque il s'applique au démarrage (écrit par le Core avant la première image), depuis le menu en jeu immédiatement ;
  - l'interface sépare pack installé, fonction activée et textures reconnues/chargées rapportées par le moteur (menu en jeu seulement) ; un import réussi ne prouve que les fichiers ;
  - `.tar.zst` seulement depuis le menu en jeu (décodeur du moteur) ; les deux en-têtes amont copiés tels quels sont épinglés et crédités.
- Core ABI 8 : `armsx2-core.yml` run `39178893158` sur `1343906f` (tests du magasin et de l'adaptateur sous Foundation, menu UIKit, Core SHA-256 `65df97dd253eca2d08bcf638e5fd2de40000579483d4321f585ef7d266319779`), épinglé dans `retroarch-delivery.yml` et `neoswap-ipa.yml` ; contrôles ciblés run `39181081216` sur `587a9d9d` ; la livraison passe par `.github/diagnostics/hdtex485_delivery.py` (produit = Build 484 livrée + fichiers 485, entrées du Core identiques à `1343906f`). Résultats, échecs déjà présents et identités : `docs/build485-hd-textures.md` § 7.
- Livraison 485 vérifiée : source `85a28e9013eaf7613da0338b4bc44f5ab7268f10`, run `39182252832` (`checks`, `native` réutilisés, `cold` réussi, `warm` ignoré), artefact `12157440577` (227 849 117 octets, archive SHA-256 `660a1b7c7c7f19bc3d8cf9e9fdf635957f5196ea4ccf7e51e0a8314c8677c92a`, conservé jusqu'au 2 novembre 2026) chiffré pour `build-utils/delivery-424-recipient.pem`. IPA **0.0.8 (485)** `NeoStation-Build485-85a28e90…-cold.ipa`, **227 624 632 octets**, SHA-256 **`e0d04987a1dcf6ce74f807edde5096975012ec0480b8e0495ae0c9867eaf522c`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build485-85a28e90.ipa`. Inspection indépendante : six bundles 0.0.8 (485) ; face à la 483, 72 images identiques (34 cœurs libretro, Core RPCS3, Dolphin, Dusklight, MoltenVK, helpers) ; changent Runner, `ARMSX2Core`, le pont ARMSX2 et les éléments de la 484 ; marqueurs 485 présents dans le Core, le pont et le code Dart, absents de la 483. Reçu : `docs/evidence/hdtex485-delivery.json`. Aucune validation sur iPhone, aucune texture affichée en jeu ; re-signature SideStore requise. Ne pas réutiliser le numéro 485.

## Build 486 — catalogue unifié de textures HD (ARMSX2, Dolphin, PPSSPP, Azahar), 19 octobre 2026

- Demande du mainteneur : un catalogue unifié de packs de textures HD téléchargeables, aussi simple que les cheats, pour la PS2, le GameCube, la Wii, la PSP et la 3DS des moteurs embarqués ; un menu « Textures HD » commun (bibliothèque de la console, options du jeu, menu en jeu) ; des catalogues réels vérifiés, crédités, sans réhébergement ; une IPA de test après les autres compilations ; rien sur `main`, aucune release. Candidate : Build 486 par-dessus la 485 livrée (`85a28e90`). Conception, vérifications et limites : `docs/build486-hd-textures-catalogue.md` ; inventaire généré des packs, auteurs, conditions et exclusions : `docs/HD_TEXTURE_CATALOG_SOURCES.md`.
- Règles posées :
  - un seul système par moteur : le pod `neo_texture_catalog` télécharge et vérifie ; la PS2 installe, active et supprime par le magasin de la Build 485 (`ARMSX2TexturePackStore`, atteint par le runtime) ; les ponts ouvrent la page par son nom et gardent leur ancienne page en repli ;
  - aucun fichier de texture n'est hébergé ni redistribué par NeoStation : un pack « en un geste » est le fichier de l'auteur, vérifié par taille et SHA-256 mesurés ; un auteur qui publie ailleurs (MEGA, Drive, Dropbox, forums, GameBanana, Patreon) n'a qu'un lien manuel ; une compilation sans permission déclarée n'est pas téléchargée automatiquement ;
  - un pack n'est proposé en un geste que si `tools/textures/verify_packs.py` a installé le vrai fichier avec le code de l'application (`tools/textures/verified.jsonl`) ; `tools/textures/build_catalogue.py --check` applique les règles de l'application ; l'index hébergé (`native/textures/catalogue/manifest.json.gz`) et l'index embarqué sont identiques à l'octet ;
  - les filtres d'installation reproduisent exactement ce que lit chaque moteur (Dolphin `tex1_*.png|dds` et marqueurs `<GameID|ID3|all>.txt` en majuscules, Azahar extension exacte et trois parties au plus, PPSSPP `textures.ini` à la racine) ; un dossier sans texture (marqueur, `textures.ini` ou `pack.json` seul) est refusé ;
  - correspondance par identifiants typés : une autre région ou révision n'est jamais supposée compatible, un titre seul n'est jamais exact, des identifiants issus d'une base de jeux (`confirm`) demandent une confirmation ; un rafraîchissement échoué n'efface jamais le dernier index valide et n'est jamais présenté comme « aucun pack » ;
  - l'interrupteur est le réglage réel du moteur pour le jeu (`HiresTextures` + `CacheHiresTextures = False` Dolphin, `ppsspp_texture_replacement` et `citra_custom_textures` par jeu, `LoadTextureReplacements` du magasin 485) ; un pack installé n'est jamais présenté comme chargé ;
  - les packs publiés en archives de dépôt (codeload) sont vérifiés sur les runners CI (`hd-textures.yml`, partie `repositories`, run `39188364133` : 64 packs réussis) ; leurs enregistrements, recopiés depuis le journal, sont contrôlés contre les artefacts du run par `tools/textures/check_ci_records.py` (`tools/textures/ci-records.json`) ; l'IPA livrée est inspectée par `build-utils/validate_hd_textures_ipa.py` (index embarqué identique à l'index hébergé, aucun pack embarqué, points d'entrée des trois ponts).
- Catalogue `2026-10-19.c38f84a2c654` : 170 packs (PS2 55, GameCube 19, Wii 22, PSP 57, 3DS 17), 144 en un geste, 26 liens manuels, 128 sources.
- Source testée `16a2b896f6fb6cc1cd803625700f1a9055fff7df`, run `hd-textures.yml` `39194576112` : parties host, native et uikit réussies ; la correspondance d'un pack se recalcule toujours depuis le pack et le jeu (`+[NeoTextureCatalog pack:matchedTo:]`), jamais depuis ce que transmet l'appelant. Détail : `docs/build486-hd-textures-catalogue.md` § 7.
- Livraison 486 vérifiée : source `b18c30cd884f915950ee03cb8d5a182de1cd9028`, run `39195753114` (`checks`, `native` réutilisés, `cold` réussi, `warm` ignoré), artefact `12161679895` (228 242 845 octets, archive SHA-256 `ce694b3f00c0bd16307a3e8cba21156056ef7bb8718b62599c8d0507202bd5b9`, conservé jusqu'au 2 novembre 2026) chiffré pour `build-utils/delivery-424-recipient.pem`. IPA **0.0.8 (486)** `NeoStation-Build486-b18c30cd…-cold.ipa`, **227 996 758 octets**, SHA-256 **`eef1553e73d115753df92455c42bec9ededc3cacb1c37980568bce9f2cedc607`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build486-b18c30cd.ipa`. Inspection indépendante : six bundles 0.0.8 (486) ; face à la 485, 76 des 82 images identiques (34 cœurs libretro, tous les autres moteurs, helpers, extensions) ; changent Runner, le code Dart et les ponts ARMSX2, Dolphin et libretro ; `neo_texture_catalog` est nouveau ; index embarqué identique à l'index hébergé, aucun pack dans l'IPA. Reçu : `docs/evidence/hdcat486-delivery.json`. Aucune validation sur iPhone, aucune texture affichée en jeu ; re-signature SideStore requise. Ne pas réutiliser le numéro 486.

## Audit des goulots RPCS3 sur l'iPhone — journaux du 18 octobre 2026 (Build 482), 19 octobre 2026

- Demande du mainteneur : établir, à partir des fichiers RPCS3 « testés sur GOW3 et GTA V », la cause des goulots et les moyens de rendre le jeu nettement plus fluide (LLVM). Audit seul, sans modification de produit ni IPA : `docs/rpcs3-bottleneck-audit-2026-10-18.md`. Les fichiers fournis couvrent en réalité **GTA V (BLES01807)** et **Fallout 3 (BLES00738)** en Build 482 ; God of War III n'y figure que par ses jalons Build 481. Les deux `RPCS3-diagnostic_1.log` sont identiques.
- Établi : la fenêtre GTA V (441 s, minutes 23–30 de la session) est une **recompilation LLVM de modules PPU après un redémarrage depuis un état de sauvegarde exécuté dans le Core** (22:48:38 UTC) : PPU et SPU à 0 ms pendant 441 s, groupe JIT = 1,4–2,85 cœurs (`jit_ms` est en ms **par image présentée**, pas par fenêtre), les « 30 fps » sont les présentations de la boîte de progression native (16,6 ms de cadence minimale), `rsx = 100 %` est une valeur figée. Tout démarrage depuis un état relance l'analyse PPU sur la mémoire restaurée (rien du module n'est sérialisé, `PPUAnalyser.h:275`) : ré-édition de liens complète au minimum, recompilation possible par construction (`applied_patches` vide, `seg0_code_end` éventuellement nul) ; 30 démarrages de ce type dans l'historique des jalons (15 processus). La thermique est mesurée (état 2 pendant 155 s) mais sans effet observable dans la fenêtre ; les 16 refus directs NeoSwap s'expliquent par `relay_ready = 0`. Fallout 3 : aucune scène lourde ; le thread RSX brûle ≈ 0,85 cœur en boucle `yield` sur FIFO vide (occupation FIFO 0–1 %) ; gel à 39,29 s coïncidant avec `sys_mutex_destroy → CELL_EBUSY` (propriétaire = dernier acquéreur, jamais effacé à la sortie d'un thread), puis ≈ 4,9 cœurs dont ≥ 3 dans les threads SPU, PPU quasi inactifs, `COREPROF` muet dès qu'aucune image n'est présentée. Sur ARM64, `busy_wait(300)` ≈ 125 ns et le seuil de sommeil GETLLAR (400 000 ticks) ≈ 16,7 ms (compteur 24 MHz, `init_arm_timer_scale()` jamais appelé sur iOS).
- Établi : **le profil God of War III n'a été en vigueur à aucun des 19 démarrages observables** (24 lignes `boot_policy`, Builds 412 → 481 : `fifo=1024 getllar=0 gow3_mlaa=0`, jalon `gow3_mlaa_bypass` jamais écrit ; démontré pour ces trois clés) alors que la base publiée est valide et acceptée ; cause la plus probable (hypothèse) : un fichier de configuration complet hérité qui fait ignorer la base GameDB (`System.cpp:1808-1835`). Aucune mesure passée des leviers GoW III (mode asynchrone, Mega, FIFO 4 Kio, GETLLAR, MLAA) n'est donc attribuable. Le plugin rejette toute notice du Core : `JITPROF`, « Applying database config », « Compiling module » et les événements d'état n'atteignent jamais `RPCS3-diagnostic.log`, qui est en outre tronqué toutes les ≈ 13 min.
- Règles posées :
  - avant toute nouvelle mesure : exporter `JITPROF` et les notices LLVM/SPU/config (liste blanche du plugin, hôte seul) ; ajouter `emu_state`, `boot_progress`, `guest_frames` et `native_ui` aux échantillons ; colonne `other_ms` et cinq threads les plus actifs dans `COREPROF`, émis même sans image ; jalon `Config layers` reflétant la couche de configuration réellement active ; jalons pour chaque redémarrage interne (réglage, création/chargement d'état) et, sur un démarrage depuis un état, les entrées de l'analyse PPU puis `ppu_cache_hits/misses` (D10) ;
  - ne jamais comparer deux captures d'états thermiques différents ; refuser les captures de référence à l'état ≥ 2 (jamais les lancements ordinaires) ; exclure les fenêtres de compilation (`ppu_ms = 0` et `jit_ms > 0`) ;
  - tout A/B d'un réglage SPU « clé » (taille de bloc, XFloat, réservations, états compatibles, pipeline 483) exige deux processus par variante, le premier jeté : les répertoires `spuobj-*` des autres clés sont supprimés au démarrage (`SPUCommonRecompiler.cpp:2046-2063`), contrairement à ce qu'écrit `docs/build483-llvm-pipelines.md` § 3/§ 9 ;
  - `Thread Scheduler Mode` et `mobile_spu_scheduling` sont inertes sur cet appareil ; `clocks_scale` et `spu_delay_penalty` ne sont pas des leviers de fluidité ; la compilation différée 435 reste interdite.
- Leviers ordonnés (hypothèses à mesurer, § 5.2 et § 6 de l'audit) : seuils de spin SPU en temps plutôt qu'en ticks / `GETLLAR Mobile Backoff` ; attente bloquante bornée du thread RSX sur FIFO vide ; pipelines 483 ; conservation de N répertoires `spuobj-*` ; `SPU Block Size` Mega ; `Max SPURS Threads` ; QoS des threads auxiliaires ; préchauffage SPU pour tous les titres à métadonnées. Aucun gain n'est annoncé comme mesuré ; aucune validation iPhone.

## Build 487 — correctifs de l'audit des goulots RPCS3 (diagnostics et leviers sélectionnables), 19 octobre 2026

- Demande du mainteneur après l'audit : « établis tes correctifs suite à l'audit ». Candidate : Build 487 par-dessus la 486 livrée (`b18c30cd`, Core RPCS3 483). Plan, vérifications, protocole iPhone et identités : `docs/build487-plan.md`. Aucune release, rien sur `main`.
- Diagnostics (Core `NEOSTATION_BUILD487_DIAGNOSTICS_V1`, pont `NEOSTATION_BUILD487_HOST_DIAGNOSTICS_V1`), sans effet sur le jeu :
  - `rpcs3_ios_performance_metrics` passe de 48 à 72 octets sous `struct_size` (images du jeu, interface native réellement visible, état de l'émulateur, progression du démarrage ; bits 4 à 7) ; ABI principale 30 inchangée ; un hôte ou un Core plus ancien garde le préfixe exact ;
  - lignes `CONFIG_LAYERS`, `NEOSTATION_RESTART`, `JITPROF_BOOT` (deux lignes), `SAVESTATE_BOOT`, `FREEZE_DUMP` (64 lignes, une fois par 30 s, verrous seulement essayés), `MUTEX_DESTROY_BUSY` (64 puis 1/1024) ; `COREPROF` ajoute `other_ms`, les cœurs par groupe, les cinq threads les plus actifs, `rsx_fifo_busy`, `rsx_thread_cpu` et s'émet aussi sans image ; `RANGELOCKPROF` ajoute le maintien maximal ;
  - le pont laisse passer ces lignes et `JITPROF`, les reflète en jalons, ajoute `emu_state boot_progress guest_frames native_ui` à `performance_sample`, fait tourner `RPCS3-diagnostic.log` vers `RPCS3-diagnostic.1.log` et n'écrit `neoswap_guest_sample_ext` (phase `sample`) que sur changement ou toutes les 60 s.
- Leviers (catalogue du Core en anglais), défauts = comportement de jeu de la 483 : `SPU Spin Timing` (Reference ; Calibrated convertit seulement les trois seuils GETLLAR, `init_arm_timer_scale()` reste à 1 sous 30 MHz), `RSX FIFO Idle Wait` (Yield ; nouvelle valeur Bounded sleep de 100 µs), `SPU Warmup Scope` (God of War III ; All titles with metadata) ; `SPU Object Cache Retained Keys` (2, politique de cache seulement : répertoires du même Core, de la même identité de codegen SPU et du même CPU, marqueur `neostation-build.id`, bornes communes 40 000 fichiers / 512 Mio).
- Règles posées :
  - les sources de génération de code (traducteurs, `CPUTranslator.h`, `JIT.h`, `JITLLVM.cpp`, passerelles AArch64, `PPUAnalyser.cpp`) et les lignes de clé du cache SPU et du nom d'objet PPU restent identiques à la 483 (`test/rpcs3_build487_core_diagnostics_test.py`) ;
  - conséquence certaine : les empreintes de codegen PPU et SPU changent (`PPUThread.cpp`, `JITPhaseProfile.h`, `SPUCommonRecompiler.cpp`) ; chaque titre recompile une fois après l'installation, premier démarrage à écarter de toute mesure ;
  - le delta canonique se régénère avec `build-utils/rpcs3/regenerate_canonical_delta.py` (en octets : les fins de ligne CRLF amont sont conservées) puis se prouve sur un clone amont vierge ; ne jamais régénérer en mode texte ;
  - la compilation SPU différée de la 435 reste désactivée ; aucun gain de fluidité n'est annoncé avant la capture iPhone décrite au § 6 du plan.
- Vérifié dans le conteneur : vérification syntaxique différentielle de 17 fichiers Core (clang 18, en-têtes amont réels, x86-64 et aarch64 : aucune erreur nouvelle par rapport à la 483) ; tests Core et hôte 487 ; 33 tests Core existants identiques à la 483. Core 487 : `rpcs3-core.yml` run `39251938919` sur `1cf02197` (réussi à la tentative 2 ; tentative 1 arrêtée sur l'expiration de la fixture Minecraft inchangée), Core SHA-256 `6b64fe7aeca17325592f478a8eb97d08187721127a586bd6f007f71cbdd11c73`, ABI 30, artefact `12191176025`, diagnostics lus par l'identifiant `12191576064` (deux artefacts de diagnostics portent le même nom dans ce run). Livraison 487 vérifiée : source `fad5eac6f793672240d2cb5f3559da73a40226f8` (tête de `Claude` ; poussée du tag `build-487` refusée par le proxy Git de la session, non contournée), run `39262042654` (`checks`, `native` réutilisés, `cold` réussi, `warm` ignoré), artefact `12192460455` (228 261 789 octets, archive SHA-256 `3e1808c21442d4d69aa5614f5a5c2c034e5654a11c2d81ce0788a00c747dcc05`, conservé jusqu'au 2 novembre 2026) chiffré pour `build-utils/delivery-424-recipient.pem`. IPA **0.0.8 (487)** `NeoStation-Build487-fad5eac6…-cold.ipa`, **228 039 548 octets**, SHA-256 **`bd59a616d8f6f02a969ea9de71e9803b9f7156df250eb36d56559462b1551759`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build487-fad5eac6.ipa`. Inspection indépendante contre la 486 : 78 des 82 images identiques ; changent le Core RPCS3 et son pont (marqueurs 487 présents), `Runner` (`__TEXT,__const` seulement) et les stubs du pont ARMSX2 (deux emplacements GOT de `_objc_msgSend` permutés par l'éditeur de liens, code identique, aucun effet). Reçu : `docs/evidence/rpcs3diag487-delivery.json`. Aucune validation sur iPhone ; re-signature SideStore requise. Ne pas réutiliser le numéro 487.

## Build 488 — catalogue de textures HD étendu (800+) et Nintendo 64 (Mupen64Plus-Next), 19 octobre 2026

- Demande du mainteneur : étendre massivement le catalogue unifié de la Build 486 (objectif 800 packs distincts, réels, vérifiés, crédités, idéalement en un geste), étudier N64/NES/PS1/Dreamcast, outiller découverte et contrôle des liens ; branche `Claude` seule, rien sur `main`, aucune release, IPA seulement après les compilations concurrentes. Candidate : Build 488 par-dessus la 487 livrée (`fad5eac6`, run `39262042654`). Conception, sources, vérifications et limites : `docs/hd-textures-expansion-2026-10-19.md` ; inventaire généré : `docs/HD_TEXTURE_CATALOG_SOURCES.md`.
- Catalogue `2026-10-19.72e26f767470` : 857 packs (PS2 696, GameCube 24, Wii 25, PSP 72, 3DS 19, N64 21), 189 en un geste, 668 liens manuels, 910 identifiants, 275 sources ; aucun pack retiré. Aucun pack n'a été chargé dans un jeu : « archive et installation vérifiées, rendu non testé ».
- Règles posées :
  - les 637 liens manuels PS2 viennent de `ps2ktxpak/catalog` (MIT, commit `807733e5`) par `tools/textures/import_ps2ktxpak.py` : seulement gratuits, crédités, avec une page d'annonce du créateur ; numéros de série de la PCSX2 GameIndex marqués « à confirmer » ; la notice MIT est livrée dans `NeoTextureCatalog.bundle` (`ps2ktxpak-LICENSE.txt`) et contrôlée octet pour octet dans l'IPA ;
  - N64 : identité `n64-rom-name-hex` (nom d'en-tête en hexadécimal), filtre exact de GLideN64, dossier `<système>/Mupen64plus/hires_texture/<nom ROM>`, interrupteur par jeu `mupen64plus-txHiresEnable` avec `-txHiresFullAlphaChannel` et `-EnableEnhancedHighResStorage` ; GLideNHQ réutilise `<nom ROM>_HIRESTEXTURES.htc|.hts` sans relire le pack : le magasin appelle `-didChangePackFolder:` après chaque installation, remplacement, import ou suppression, et l'adaptateur N64 supprime ces deux fichiers de ce seul nom ;
  - NES (HD Packs de Mesen), PS1 (Beetle PSX : option donnée instable par ses auteurs, rendu logiciel observé), Dreamcast (Flycast non embarqué) et les fichiers Basis Universal de PPSSPP ne sont pas ouverts ;
  - un hôte qui refuse un contrôle automatique (632 pages gbatemp.net, HTTP 403) n'est ni contourné ni compté comme cassé ; les fichiers `excluded-<origine>.json` d'autres sessions sont lus comme exclusions.
- Vérifié : hôte (identités 40 images, installation 67 vérifications, libellés 158 clés, porte de l'IPA 13 refus) ; `hd-textures.yml` run `39265084257` sur `f4834ce5` (host 46 vérifications et 86 tests Dart, native avec le test Foundation N64 et la compilation iPhone, uikit 7 tests dont la page N64) ; archives de dépôt sur CI (88 enregistrements contrôlés contre leurs artefacts). Une IPA seulement après la fin de la livraison 487.
- Livraison 488 vérifiée : source `2bdca0d4b7a353af17016c528d2cf38ecacc9e9b` (porte `.github/diagnostics/hdtex488_delivery.py`), run `39267021460` (`checks`, `native` réutilisés, `cold` réussi, `warm` ignoré), artefact `12193569615` (228 349 853 octets, archive SHA-256 `e274853149b0fd041f92b676f5e42676cb76244b0ffb08a4c86bdde5a222ffd6`, conservé jusqu'au 2 novembre 2026) chiffré pour `build-utils/delivery-424-recipient.pem`. IPA **0.0.8 (488)** `NeoStation-Build488-2bdca0d4…-cold.ipa`, **228 109 916 octets**, SHA-256 **`8405f8c42b121ea891fdbd98e4bc866e1e071239b98acd4d5fc9aa0d7040e2c5`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build488-2bdca0d4.ipa`. Inspection indépendante : six bundles 0.0.8 (488) ; face à la 487, 78 des 82 images identiques ; changent le code Dart, le pont libretro, `neo_texture_catalog` et `Runner` (numéro de build) ; bundle du catalogue identique au commit livré, notice ps2ktxpak présente. Reçu : `docs/evidence/hdtex488-delivery.json`. Aucune validation sur iPhone ; re-signature SideStore requise. Ne pas réutiliser le numéro 488 ; la session Beetle PSX/PS1 prévoit la 489 par-dessus.

## Build 489 — catalogue HD étendu (GameCube, Wii, 3DS) et Beetle PSX HW en Vulkan, 19 octobre 2026

- Demande du mainteneur : extension massive du catalogue unifié (priorités GameCube, Wii et 3DS, puis PSP et PS2 ; plus de 800 packs distincts valides ; N0 figé, au moins 3 × N0 au total et pour chacune des trois priorités, écart publié), exploration des 386 références et des autres projets de leurs auteurs, Beetle PSX HW avec son rendu Vulkan (MoltenVK) et l'état réel affiché, IPA de test. Branche `Claude`, rien sur `main`, aucune release. Plan, comptage, sources, vérifications et limites : `docs/build489-hd-catalogue-ps1-vulkan.md` ; inventaire généré : `docs/HD_TEXTURE_CATALOG_SOURCES.md`.
- Résultat (`tools/textures/count_packs.py`, une famille par pack) : N0 144 → 280 familles installables ; GameCube 21 → 76, Wii 13 → 39, 3DS 10 → 37 (3 × N0 atteint), PSP 56 → 82, PS2 32 → 33, N64 14, PS1 1 ; total −152 sous 3 × N0 ; l'objectif de 800 packs valides n'est atteint qu'en comptant 672 liens sans fichier vérifié (dont 637 liens PS2 de ps2ktxpak). Index `2026-10-19.85092338c53c` (1 034 entrées : 194 en un geste, 168 manuelles à fichier vérifié). Rendu vérifié en jeu : 0 pack.
- Règles posées :
  - un pack manuel (MEGA, Google Drive, Dropbox, MediaFire, GameBanana, archive.org) n'est installable que si le fichier exact de l'auteur a été récupéré une fois sur un runner (job `hosts`, liens publics seulement ; quota, connexion, CAPTCHA, défi anti-robot jamais contournés), installé par le code de l'application et décrit dans l'index (`download.verified` : taille, SHA-256) ; l'application n'accepte que ce fichier ; NeoStation n'héberge rien ;
  - les enregistrements recopiés des journaux sont comparés à leurs artefacts par `check_ci_records.py` ; un pack revérifié marque l'ancien enregistrement `superseded` ; un transfert MEGA est borné à 45 minutes (`quota`) ;
  - une famille par pack : résolutions, formats, éditions, styles de boutons, mises à jour, miroirs et add-ons comptent une fois ; portée `complete`/`partial`/`ui` ; chaque archive sondée a une décision (entrée, exclusion motivée ou candidat listé) ;
  - Beetle PSX HW : contexte Vulkan demandé, un seul repli sur le rendu logiciel sans périphérique Vulkan ; garde `A1R5G5B5` (capacités réelles du format lues avant `loadCore`, trame et vue VRAM verrouillées sans elles) ; pack dans `<contenu>-texture-replacements` du dossier de sauvegarde (cartes mémoire intactes, un dossier pour tout un M3U) ; dossier `save`, aucun dump, cache paresseux, budgets 512 Mo verrouillés ; « reconnus » comptés par l'hôte selon la règle du cœur dans le dossier `save` (le compte du cœur visait le dossier du contenu) ; jamais « HD actif » sur le rendu logiciel ; packs DuckStation ni convertis ni proposés.
- Vérifié sur la source figée `7c6a86e4` : `hd-textures` host `39337036938` (51 vérifications, 290 enregistrements CI conformes à leurs artefacts, 130 tests Flutter), native `39337040395`, uikit `39337043258` ; Beetle dans le Simulateur `39337045728` (trois scénarios en Vulkan, `recognized=5` avec remplacement, 13 vérifications de cycle de vie). Le Metal du Simulateur refuse les copies CPU→VRAM de Beetle : remplacement à l'écran, chargement d'état, changement de disque et cartes mémoire pendant un remplacement restent à vérifier sur l'iPhone.
- Livraison 489 vérifiée : tag `build-489` = `a8065a993c0a9f791c40bad75c44726fa63e161d` (`041d1d55` + épinglage du contrôle `hdtex489_delivery.py` ; poussé depuis le PC du mainteneur à sa demande, le proxy de session refusant les tags ; les commits postérieurs d'autres sessions sur `Claude` en sont exclus), run `39340720047` (`checks`, `native`, `cold` réussis, `warm` ignoré), artefact `12229302711` (228 425 629 octets, archive SHA-256 `e58988ba16c4227a7fd485f53ae4f75a9bb4f64f32fb8805fc2890e4619a2d7b`, conservé jusqu'au 2 novembre 2026) chiffré pour `build-utils/delivery-424-recipient.pem`. IPA **0.0.8 (489)** `NeoStation-Build489-a8065a99…-cold.ipa`, **228 181 989 octets**, SHA-256 **`4aba0ca44a6a95052bd4082c710bf3dfb343a23b045e11c321517ddcdca76fe0`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build489-a8065a99.ipa` ; index du catalogue dans l'IPA identique à l'index figé. Reçu : `docs/evidence/hdtex489-delivery.json`. Aucune validation sur iPhone ; re-signature SideStore requise. Ne pas réutiliser le numéro 489.

## System Art — Canvas (ES-DE), 19 October 2026

- Maintainer request: add https://github.com/zenandiko/canvas-es-de as a source of main-menu system icons in Settings › System Art. Curated external pack `CanvasESDE` (« Canvas (ES-DE) »), like RiiSU: images stay hosted upstream and are downloaded only when selected, never bundled. Details: `docs/system-art/Canvas-ES-DE.md`.
- Pinned revision `12d03b1856b892497a3fa1c943888c1f542f9236`, `theme/flat/webp` only. ES-DE capsule names are mapped from every `assets/systems` alias by `tools/system_art/canvas_es_de.py` (generated `lib/services/system_art/canvas_es_de_capsules.dart`, `--check` in CI); an uncovered system is never requested. Credit zenandiko, Siddy212 and fagnerpc; upstream states personal, non-commercial use (`assets/legal/Canvas-ES-DE-ATTRIBUTION.md`).
- Position du mainteneur : respecter les sources. NeoStation est gratuit et n'est pas vendu ; proposer ce pack n'est pas le vendre comme source, mais rendre le projet d'origine accessible publiquement au plus grand nombre, auteurs crédités, images laissées sur leur dépôt.
- IPA demandée seulement après la fin des compilations en cours (489 livrée, 490 de l'autre session) ; ne pas réutiliser leurs numéros.

## Décision du mainteneur — retrait complet de KartPad, 19 octobre 2026

- Décision : « Retire complètement Mario Kart Pad. Vu qu'il contient du code, et que c'est un port, c'est à l'utilisateur de le construire lui-même et de l'installer en tant qu'IPA unique. » Elle remplace les choix précédents du cycle (donneur 0.5.1 gardé, moteur 0.8.3 sans jeu intégré, ajout d'un pack personnel à l'IPA NeoStation). Détail, garanties et procédure joueur : `docs/kartpad-removal-2026-10-19.md` ; audit qui l'a précédée : `docs/kartpad-online-dusklight-audit-2026-10-19.md`.
- Établi : le donneur `v0.5.1-experimental.1` (`KartPadRuntime` `ad5c00a0…`) contient du code de Mario Kart Wii traduit (29 065 fonctions `func_8…`, `RVL_SDK`, classes du jeu) ; depuis la 0.7, KartPad ne publie plus de code de jeu pour iPhone.
- Règles posées :
  - NeoStation ne contient, ne compile, ne télécharge et n'embarque plus aucune partie de KartPad (moteur, pont, hôte, pack personnel, ressources racine `wii_bootstrap/`, `initial_pipeline_cache.db`, `dsp_coef.bin`) ; ne pas réintroduire de port contenant du code de jeu traduit ;
  - toute livraison récupère le donneur natif Build 350 par `build-utils/fetch_native_donor_subset.py` (aucun octet d'un membre KartPad demandé), le contrôle par `build-utils/game_content_gate.py`, et valide l'IPA par `build-utils/validate_no_kartpad_ipa.py` ; ne jamais retélécharger l'IPA Build 350 entière en CI ;
  - les données du joueur dans `Ports/KartPad` (jeu, sauvegardes, identité de console, données préparées) ne sont ni déplacées ni supprimées ; l'outil de stockage continue de les reconnaître ; un jeu encore listé est refusé avec le message `kartpadRemoved` (douze langues), jamais transmis à Dusklight ;
  - exception autorisée sur les fichiers verrouillés 419 : seules les lignes de la racine d'analyse `Ports/KartPad` sont retirées de `sqlite_config_provider.dart` et `scanning.dart`, reconstruites par `test/retroarch_baseline_scope_test.py` (`KARTPAD_REMOVAL_EDITS`) ; `native/kartpad` doit rester absent ;
  - la valeur d'ABI `NEOSWAP_KARTPAD = 4`, le patch RPCS3 épinglé, les anciens portails de livraison et les anciennes releases (dont la 0.0.1) restent inchangés ; l'historique Git n'est pas réécrit.
- Le chantier « jeu en ligne Retro Rewind » ne passe plus par KartPad. À la demande du mainteneur (« Reprendre l'audit », 20 octobre 2026), l'audit en lecture seule de la voie Dolphin + Retro Rewind est rendu : `docs/dolphin-retro-rewind-online-audit-2026-10-20.md`. Établi : Riivolution est compilé et exporté par le `DolphinCore` verrouillé (identité 350, DolphiniOS `7cac5416` sur Dolphin 2509), mais le pont NeoStation compilé dans ce cœur n'accepte qu'une vraie image Wii (`neostation_dolphin_validate_image`) et relance le même chemin sans correctifs : aucun descripteur `.json` ni réglage ne déclenche Riivolution ; le réseau (pile IOS, `/dev/dolphin`, redirection HTTP du pack, clés Dolphin par défaut acceptées par Retro WFC) ne demande rien de plus ; la base 2509 n'a pas les correctifs de sécurité de 2606a.
- Règles posées : aucun changement du cœur Dolphin sans accord du mainteneur (B1 : `validate_image` accepte un descripteur `.json` confiné et vérifié, nouvelle identité `DolphinCore` et régression complète ; B3 : rebase sur Dolphin ≥ 2606a) ; ne jamais réhéberger ni embarquer le pack Retro Rewind (éléments sans licence publiée) — téléchargement depuis le CDN officiel seulement avec l'accord écrit de l'équipe, sinon import par le joueur ; aucun appel direct aux exports C++ de Dolphin depuis le pont (contournerait JIT, Metal et l'état du lancement) ; Wiimmfi seulement avec une image patchée par le joueur lui-même. Aucun jeu en ligne n'est annoncé fonctionnel avant une vraie course sur iPhone (résultats et retour au salon).
- Vérifications et livraison : `launch-ui-checks.yml` (analyse Flutter complète, tests Dart et contrats du retrait), `neoplay-check.yml` (tâche `native`). L'IPA du retrait se construit après les compilations en cours (Build 490), sous un nouveau numéro, avec sa propre porte de livraison. Dusklight reste en v2.0.3, sans reconstruction.

## Build 490 — boîtiers 3D de la vue Jaquette, lecture du dos en douze langues et ouverture au lancement, 20 octobre 2026

- Demande du mainteneur (19 octobre 2026) : vue Jaquette avec un boîtier en volume adapté à la console et au support, manipulable à 360°, dos lisible dans les douze langues (scan localisé de l'édition, sinon reconnaissance et traduction mises en cache), ouverture sur la cartouche ou le disque au lancement, médias étendus et hors ligne ; précision : « Il faut que les jaquettes soient réalistes. Des vraies jaquettes de PlayStation 1, pour exemple. » IPA de test, aucune release. Conception, sources, limites : `docs/game-box-3d.md` ; plan, vérifications, livraison et protocole iPhone : `docs/build490-plan.md`.
- Règles posées :
  - le style de carte « Boîte » du carrousel seul change ; vues Liste, Grille et Fanart, fichiers verrouillés 419, lancement (`launch_flow.dart`, `game_launch_utils.dart`, `game_launch_service.dart`), moteurs et réglages d'émulation inchangés ; un échec de rendu ou de média ne bloque jamais le lancement, la porte `GameBoxLaunchGate` empêche tout double lancement et la visionneuse ne quitte l'écran qu'une fois le lancement réellement en cours ;
  - le dos n'est jamais une copie de la face avant et aucun texte n'est inventé : sans scan, dos neutre avec mention discrète ; l'identification du jeu n'est jamais modifiée par le choix d'une édition de lecture ;
  - les faces viennent de ScreenScraper par le client du scraper (identifiants MD5/nom, `jeuid`, région, jeton `media`), dans `box2dback`, `box2dside`, `support2d`, `box2dback-editions`, avec un manifeste `boxmeta` sans identifiants de connexion ;
  - lecture : Vision et NaturalLanguage sur l'appareil, traduction par Apple Translation (modèles iOS, téléchargement proposé par le système), cache `Application Support/NeoStation/BoxText/<SHA-256 du scan>` ; traduction automatique signalée, texte d'origine toujours accessible ; plugin `packages/neo_box_reader` lié statiquement (aucun framework ajouté) ;
  - préférences `NeoStation.GameBox.OpeningAnimation`, `.ReadingLanguage`, `.ReaderTextScale` ; 106 textes dans les douze langues (`tools/game_box/strings.json`, `--check`).
- Livraison : tag `build-490` = source 489 livrée `a8065a99` + les seuls commits 490 (`d152e5a270037484a435d641e04acd3a2ccaf3a6`, arbre `f1028924`, poussé depuis le PC du mainteneur, le proxy du conteneur refusant les tags) ; les commits postérieurs d'autres sessions sur `Claude` n'en font pas partie. Contrôles ciblés sur ce commit exact, `game-box-checks.yml` run `39345297065` : Flutter 136 tests réussis (1 ignoré, réservé à macOS), analyse, douze langues ; Vision 12/12 sur macOS 15.7 et sur le simulateur iOS 26.2, Translation disponible sur macOS, indisponible dans le simulateur. Porte `.github/diagnostics/gamebox490_delivery.py`, run `39346406673` (`checks`, `native` réutilisés, `cold` réussi, `warm` ignoré), artefact `12232290380` (228 643 741 octets, archive SHA-256 `85e9d9ba1e810f88dbf8b6921647180af4bda40b2c13a56fdd3b1f68132ac405`, conservé jusqu'au 3 novembre 2026) chiffré pour `build-utils/delivery-424-recipient.pem`. IPA **0.0.8 (490)** `NeoStation-Build490-d152e5a2…-cold.ipa`, **228 399 609 octets**, SHA-256 **`7ceb97311b4de5db570d520a4dc67b3af8c7e0eceb499f445615ce6da4b3897b`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build490-d152e5a2.ipa`. Inspection indépendante contre la 489 : 79 des 82 images identiques ; changent le code Dart, `Runner` (plugin statique) et les stubs de `libretro_internal_bridge` (deux emplacements GOT voisins permutés par l'éditeur de liens, chaque stub vise le même symbole, sources identiques). La 490 contient encore KartPad, identique à la 489 : l'IPA du retrait décidé le 19 octobre vient après, sous un nouveau numéro. Reçu : `docs/evidence/gamebox490-delivery.json`. Aucune validation sur iPhone ; re-signature SideStore requise. Ne pas réutiliser le numéro 490.

## Build 491 — Build 490 + Canvas (ES-DE) + retrait de KartPad, 20 octobre 2026

- Choix du mainteneur : « 490 + Canvas + retrait ». Produit = Build 490 livrée (`d152e5a2`) + les fichiers Canvas (ES-DE) et ceux du retrait de KartPad ; aucun Core reconstruit, aucune entrée des moteurs, helpers, skins, triches, textures ni boîtiers 3D modifiée. Plan, contrôles et identités : `docs/build491-plan.md`.
- Règles posées : contrôles ciblés `build491-checks.yml` + `test/build491_targeted_test.py`, dont chaque partie refuse d'abord tout fichier modifié depuis la 490 qu'elle ne déclare pas comme entrée ; la suite Dart de l'hôte est lue dans `retroarch-delivery.yml` (identique ligne pour ligne) ; porte `.github/diagnostics/kartpad491_delivery.py`. Un workflow neuf ne peut pas être lancé à la main tant qu'il n'est pas sur la branche par défaut : il se déclenche par la poussée de ses propres fichiers sur `Claude`.
- Contrôles : run `39349740393` sur `59bec98c` (hôte : analyse complète sans constat, suite Dart de livraison, retrait, Canvas, douze contrats Python ; natif : NeoPlay NPCheck, Simulateur iOS 18). Livraison : run `39350746416` sur `Claude` @ `59bec98c31741c010d827dd2b58949244eb93431` (`checks`, `native` réutilisés, `cold` réussi, `warm` ignoré) ; IPA contrôlée sans KartPad ni fichier d'origine jeu (4 521 membres) ; IPA validée avant scellement `c02024fc…f7a3` ; artefact `12233906099` (186 674 077 octets, archive SHA-256 `12f989d5…962c`, conservé jusqu'au 3 novembre 2026), chiffré pour `build-utils/delivery-424-recipient.pem`.
- Le mainteneur a supprimé la clé privée 424 : le premier artefact (`12233906099`, run `39350746416`) n'est pas remis et ne peut plus être déchiffré. Livraison remise : run `39353891715` sur `Claude` @ `9faa3f9b` (même produit ; la porte accepte les contrôles d'un ancêtre qui ne diffère que par la documentation ou le câblage de livraison, entrées testées comparées à l'octet), artefact `12235290471` (186 674 205 octets, archive SHA-256 `7d1c001c…5e64`) chiffré pour `build-utils/delivery-491-recipient.pem` ; seule l'enveloppe a été déchiffrée dans le conteneur, puis la clé privée 491 supprimée. IPA **0.0.8 (491)** **186 428 464 octets**, SHA-256 **`ad3963793fc4ca19b89f46613f9cdf139ec5c5bfa202d0132e7698413aeb894e`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build491-9faa3f9b.ipa` ; inspection sur le PC : aucun KartPad ni fichier d'origine jeu (4 661 membres), six bundles 0.0.8 (491), marqueurs Canvas et `kartpadRemoved` présents, canaux KartPad absents. Reçu : `docs/evidence/kartpad491-delivery.json`. Re-signature SideStore requise ; aucune validation sur iPhone. Ne pas réutiliser le numéro 491.

## Build 492 — retrait de Dusklight et de la playlist Ports, 20 octobre 2026

- Demande du mainteneur (« Suppression complète de Dusklight et de la section ports ») : pour des raisons de risque juridique, Dusklight (réimplémentation de Twilight Princess construite sur sa décompilation) quitte le code, l'interface et toute IPA future, ainsi que la playlist Ports du menu principal ; « Retirer aussi KartPad » (déjà fait par la Build 491, conservé). Aucun autre portage de Twilight Princess ne le remplace : Dolphin reste la voie pour les versions GameCube et Wii. Candidate : Build 492 par-dessus la 491 livrée (`9faa3f9b`, run `39353891715`, produit de `59bec98c`). Décision, contenu retiré, données, vérifications et protocole : `docs/ports-removal-2026-10-20.md`.
- Règles posées :
  - NeoStation ne contient, ne compile, ne télécharge et n'embarque plus aucune partie de Dusklight (Core, pont, hôte, ressources, notices, identité) ni la playlist Ports ; ne pas réintroduire de portage de jeu décompilé sans demande explicite du mainteneur ; toute IPA passe `build-utils/validate_no_dusklight_ipa.py` à côté de `validate_no_kartpad_ipa.py` (seules exceptions : notices texte de `Legal/` et `assets/legal/`, une occurrence dans la table des propriétaires du binaire NeoSwap) ;
  - le donneur natif Build 350 se récupère sans aucun membre Dusklight (2 656 membres, agrégat `2f73382b…`) ; `prepare_fast_native_runtime.py` refuse un donneur qui en contient ;
  - les fichiers des joueurs (`Ports/Dusklight`, `Ports/KartPad`) ne sont ni déplacés ni supprimés ; les lignes `ports` de `data.sqlite` ne quittent la base qu'après une copie vérifiée (`RetiredPortsBackup`, `Support/NeoStation/Maintenance/data-before-ports-removal-*.sqlite`, classe « jamais ») ; sans copie, rien n'est retiré, la playlist reste masquée et un ancien jeu Ports est refusé (« Émulateur non configuré », douze langues) sans passer par un autre émulateur, RetroArch ou la feuille de partage ;
  - exception autorisée sur les fichiers verrouillés 419 (`sqlite_config_provider.dart`, `scanning.dart`, `sqlite_service.dart`, `sqlite_database_service.dart`, `scraper_repository.dart`, `system_repository.dart`), reconstruite par `test/retroarch_baseline_scope_test.py` (`PORTS_REMOVAL_EDITS`, blocs `RETIRED_PORTS_*`) ;
  - la valeur d'ABI `NEOSWAP_DUSKLIGHT = 3`, le patch RPCS3 épinglé, les documents et reçus des builds antérieures et les anciennes releases restent inchangés ; l'historique Git n'est pas réécrit.
- Vérifications : `build492-checks.yml` run `39355430653` sur `b1ca2a97` (hôte : analyse, suite Dart de livraison, nouveaux tests, 13 contrats Python, preuves de sources ; natif : syntaxe iPhone d'`external_display`, NPCheck 32/32) ; porte `.github/diagnostics/portsremoval492_delivery.py`.
- Livraison 492 vérifiée : run `39356466695` sur `3349513a` (= `b1ca2a97` + reçu 491, documents seuls ; `checks`, `native` réutilisés, `cold` réussi, `warm` ignoré), artefact `12236001799` (166 115 869 octets, archive SHA-256 `54a7acdb8d66d62cc2288e0551f4671a11cda3c5008e38f125ce1bf71c46df2c`, conservé jusqu'au 3 novembre 2026) chiffré pour `build-utils/delivery-492-recipient.pem` (clé privée créée sur le PC du mainteneur et supprimée après la remise). IPA **0.0.8 (492)**, **165 863 534 octets**, SHA-256 **`56eb53f31f3ee131ea7048ccac5f4f1f5ebd3ef23b41c282249932f7de3fbb79`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build492-3349513a.ipa`. Inspection indépendante : 4 082 membres sans Dusklight ni Ports, six bundles 0.0.8 (492), 34 cœurs libretro, Dolphin, ARMSX2 et RPCS3 présents. Reçu : `docs/evidence/portsremoval492-delivery.json`. Aucune validation sur iPhone ; re-signature SideStore requise. Ne pas réutiliser le numéro 492.

## Build 493 — boîtiers 3D dans les trois vues, notice dans le boîtier et Retour, 20 octobre 2026

- Demande du mainteneur : généraliser les boîtiers 3D de la 490 aux vues Carrousel, Grille et Liste ; retirer le halo lumineux autour des boîtiers et le garder uniquement sur le nom du jeu sélectionné en vue Liste ; bouton Retour dans la visionneuse ; dos lisible (zoom, déplacement, recentrage, vue plane haute résolution, lecture multilingue conservée) ; « Ouvrir la boîte » sans lancer le jeu, avec le support et la notice PDF déjà téléchargée, prise et lue dans le lecteur existant ; animation d'ouverture conservée au lancement ; IPA testable, aucune release. Candidate : Build 493 par-dessus la 492 (retrait de Dusklight et des Ports, autre session). Conception et règles : `docs/game-box-3d.md` § 3 et § 11 ; plan, vérifications, livraison et protocole iPhone : `docs/build493-plan.md`.
- Règles posées :
  - une seule implémentation pour les trois vues : `GameBoxCard` (en grille et en liste décodé à la largeur de l'ancienne jaquette plate, une facette par coin), `GameBoxLibrary` (chemins mis en cache par jeu et version d'illustrations, profils, visionneuse, « Jouer » avec ouverture) et `GameBoxInspector` ; le style « Fanart » ne change pas ;
  - halo (`RainbowSelectionBorder`) : jamais autour d'un boîtier ; en Liste, seulement autour du titre sélectionné, à la longueur du titre, après la miniature 3D ; la sélection d'un boîtier se voit par sa taille (carrousel, grille +7 %) ;
  - la visionneuse remonte d'un niveau à chaque Retour (bouton en haut à gauche, B, geste du système) : notice → boîtier ouvert → boîtier fermé → bibliothèque, sans lancer le jeu ni changer la sélection, sans recharger la bibliothèque ;
  - la notice n'existe dans le boîtier que si son PDF est sur l'appareil, au chemin de Réglages du jeu › Notice (`GameModel.getManualPath` par le `FileProvider`, service commun `GameManualService`, aussi utilisé par l'onglet) ; aucun livret inventé, aucune copie ni second cache, aucun téléchargement à l'ouverture ; « Télécharger la notice » est volontaire et passe par l'appel ScreenScraper de l'onglet ; la première page n'est dessinée qu'à l'ouverture de la boîte et libérée avant un lancement ; la notice se lit dans `GameManualReaderScreen`, dans sa langue réelle, jamais présentée comme traduite ;
  - lancement, moteurs, fichiers 419, plugin `neo_box_reader` et toute entrée native inchangés ; 18 textes ajoutés dans les douze langues (`tools/game_box/strings.json`, 123 textes).
- Vérifications : `build493-checks.yml` (`test/build493_targeted_test.py --part host` : couverture depuis la 492, textes, analyse complète, suite Dart de livraison, suites des boîtiers et des vues, contrats Python), runs `39356719105` (`ccf64b63`) et `39358091668` (`fba57251`, job `118417508989`, verdict `12236461913`) réussis ; porte `.github/diagnostics/gamebox493_delivery.py`. `game-box-checks.yml` ne se relance plus par poussée que si le plugin de lecture ou son lanceur change.
- Livraison 493 vérifiée : produit `f181a123`, source `013d32ed0238922dcabe57aca407a6e4b49c82f5` (= `fba57251` + reçu 492 de l'autre session, documents seuls), run `39359025363` (`checks` : tests Dart validés à `fba57251`, clé d'entrées vérifiée ; `native` réutilisé ; `cold` réussi ; `warm` ignoré), artefact `12237335582` (166 144 285 octets, archive SHA-256 `58c25bb001ada416c132650398821e28b08043983ce610aee2c31c8d75d3aaf0`, conservé jusqu'au 3 novembre 2026) chiffré pour `build-utils/delivery-493-recipient.pem` (clé privée créée dans le conteneur, jamais versionnée, détruite après la remise). IPA **0.0.8 (493)** `NeoStation-Build493-013d32ed…-cold.ipa`, **165 913 805 octets**, SHA-256 **`23bf3020a604a58733f4cc24631df84248cb5e9bb5aa2d30e991b98d82924a7c`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build493-013d32ed.ipa`. Inspection indépendante contre la 492 : 4 082 membres, aucun ajouté ni retiré, aucun nom Dusklight ou KartPad ; six bundles 0.0.8 (493) ; changent le code Dart (marqueurs 493 présents), `Runner` (`__TEXT,__const` : `Runner-493`) et les stubs du pont ARMSX2 (1 032 stubs décodés : mêmes symboles et sélecteurs) ; Dolphin, les JIT et NeoSwap identiques section par section ; tout le reste (34 cœurs libretro, ARMSX2Core, RPCS3, MoltenVK) identique à l'octet. Reçu : `docs/evidence/gamebox493-delivery.json`. Aucune validation sur iPhone ; re-signature SideStore requise. Ne pas réutiliser le numéro 493.

## Build 494 — netteté et lisibilité du texte des dos, 20 octobre 2026

- Demande du mainteneur : « améliore si tu peux encore la netteté et la lisibilité des textes à l'arrière des boîtes ». Candidate : Build 494 par-dessus la 493 livrée (`013d32ed`, run `39359025363`). Conception, mesures et limites : `docs/game-box-3d.md` § 12 ; plan, vérifications, livraison et protocole iPhone : `docs/build494-plan.md`.
- Règles posées :
  - le dos lu de face (boîtier immobile) et la vue à plat sont dessinés à la largeur exacte qu'ils couvrent à l'écran (`GameBoxSharpScan`, Mitchell-Netravali B = C = 1/3, choisi par mesure contre le modèle trilinéaire du GPU et Lanczos/Catmull-Rom) ; jamais au-delà de la taille du scan ; l'accentuation « Texte net » (`NeoStation.GameBox.SharpText`, activée par défaut) ne touche que la luminosité, au-dessus d'un seuil de 3/255 ; rien n'est ajouté au scan ; rendu libéré à la fermeture, avant un lancement, pendant la notice et au changement de scan ;
  - en portrait, le panneau de la visionneuse prend au plus 36 % de la hauteur (`portraitPanelShare`), boutons et notes défilant, « Jouer » toujours visible ; le paysage ne change pas ;
  - la lecture du dos reste exactement celle de la 493 ; une seconde passe (lignes jusqu'à 6 px, scans de moins de 1 800 px agrandis pour Vision seulement) n'ajoute que des lignes là où la première n'a rien lu, jamais à la place d'une ligne lue (une lecture unique ainsi réglée lisait moins bien certaines lignes, run `39378255052`) ; les transcriptions version 1 sont relues une fois (version 2), leurs traductions refaites ;
  - la seule entrée native modifiée est `BoxTextRecognizer.swift` (plugin lié statiquement) ; aucun Core reconstruit ; contrôles `build494-checks.yml` (host + native, recognizer de la 493 comme contrôle), porte `.github/diagnostics/gamebox494_delivery.py`.
- Contrôles : run `39378255052` sur `ed887b13` refusé (partie native : la lecture unique des petits caractères lisait moins bien trois blocs que la 493 ; aucun seuil modifié) ; correction `7126f4a5`, run `39380576904` réussi (host ; native : 60 blocs, aucun sous la 493, mentions de 6,6 px sur macOS lues 0,795 et 0,907 au lieu de rien, aucun gain dans le Simulateur iOS sur ces dos ; vérification de type contre le SDK iPhone). Le nom de la partie native (106 caractères) est listé par GitHub tronqué à 97 + « ... » : la porte le cherche sous ce nom (`f61e1b9a`, livraison seulement ; premier essai `39382247412` arrêté par la porte).
- Livraison 494 vérifiée : tag `build-494` = `f61e1b9ab41bbf09eef478346b131890285f4700` (= Build 493 livrée + les seuls fichiers 494 ; poussé depuis le PC du mainteneur, le proxy du conteneur refusant les tags, et déplacé deux fois avant toute livraison : `ed887b13` → `7126f4a5` → `f61e1b9a`), run `39382565199` (`checks`, `native` réutilisés, `cold` réussi, `warm` ignoré), artefact `12246303875` (166 168 861 octets, archive SHA-256 `36a825d944e4fe6cfc9c507de9808432f8285cc4841e3b78bba22ba494445fd0`, conservé jusqu'au 3 novembre 2026) chiffré pour `build-utils/delivery-494-recipient.pem` (clé privée créée dans le conteneur, jamais versionnée, détruite après la remise). IPA **0.0.8 (494)** `NeoStation-Build494-f61e1b9a…-cold.ipa`, **165 924 023 octets**, SHA-256 **`8b2fbf5fb9ae7c9d06bdd3bc84ff44a9ffdd521b85929d42fe130d9a66770e29`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build494-f61e1b9a.ipa`. Inspection indépendante contre la 493 : 4 082 membres, aucun ajouté ni retiré ; six bundles 0.0.8 (494) ; changent le code Dart (marqueurs 494 présents), `Runner` (plugin `neo_box_reader` lié statiquement : nouveau recognizer, sélecteur `setMinimumTextHeight:` présent, absent de la 493) et les stubs des ponts ARMSX2, Dolphin et libretro (mêmes symboles et sélecteurs décodés) ; DolphinCore, JIT et NeoSwap identiques section par section ; 34 cœurs libretro, ARMSX2Core, RPCS3 et MoltenVK identiques à l'octet. Reçu : `docs/evidence/gamebox494-delivery.json`. Aucune validation sur iPhone ; re-signature SideStore requise. Ne pas réutiliser le numéro 494.

## Build 495 candidate — NES HD packs through Mesen, 20 October 2026

- Maintainer request: new HD catalogue sources, HD packs for the Nintendo DS and every other retro console that has them. Established in the sources: neither the embedded DeSmuME nor melonDS replaces textures, so no DS pack exists or is announced; among the embedded cores only Mesen reads NES HD packs. Mesen (official iOS ARM64 buildbot binary, GPLv3, on RetroArch's App Store core list) is added unchanged as lot 3 to the delivered 34-core package (`LibretroCores-4c218620…`, run `39366986940`, 35 cores) as an alternative NES / Famicom / FDS engine; Nestopia stays the default. Design, sources, exclusions and checks: `docs/hd-textures-nes-mesen.md`.
- Rules set:
  - an NES pack is identified by the SHA-1 of the whole file Mesen loads (iNES header included, `nes-rom-sha1`) and installed in `<system>/HdPacks/<content name>`, with exactly what Mesen reads (`hires.txt` format 106 at most, a failing `<img>` refuses the pack, decoded images bounded by half of the memory the app can still allocate); switching a pack on for a Nestopia game goes through NeoStation's own per-game engine choice, never silently;
  - the libretro host sets the video, audio and input callbacks after `retro_init`, as RetroArch does (`runloop.c`, `core_init_libretro_cbs`): Mesen dereferences its console, created in `retro_init`, in those setters (SIGSEGV at `0xc0`, run `39370233922`). `test/libretro_host/host_test.m` requires none before and five after; the portable host test compiles again (pod headers staged, catalogue store compiled);
  - packs whose format needs Mesen 2 (≥ 107) or a modified Mesen fork, rehosted packs of other authors and links known only from third-party articles are excluded with their reason (`tools/textures/sources/excluded-nes-mesen.json`).
- Tested source `8d1429cf`: hd-textures run `39371944591` (on `31222605`, identical inputs), Simulator run `39373940448` (Mesen five scenarios; the probe job only has the classified crowded-window limitation), cores package run `39366986940`. The delivery waits for the other session's Build 494; gate `.github/diagnostics/hdtex495_delivery.py`. No device validation; no pack is claimed to render on iPhone.


## HD catalogue exploration — 20 October 2026 (catalogue data only)

- Maintainer request: deeper PSP/3DS/Wii/GameCube discovery, especially Fire Emblem and PSP Call of Duty Roads to Victory; future Switch references only. Work stays on `Claude`; no release or IPA requested/produced, no build number allocated and no native/core input changed.
- Baseline `6b0a905c` / index `2026-10-20.212eb2401253`: 1,050 entries, 287 installable families. Index `2026-10-20.809cfd2df68f`: 1,072 entries, 295 installable families; every pre-existing pack object unchanged. New sources: `*-exploration.json`; no second runtime catalogue. Report: `docs/hd-textures-exploration-2026-10-20.md`; evidence: `docs/evidence/hd-exploration-2026-10-20.json`.
- Eight new manual archives passed the production installer: Awakening AAHD **P1 only**, Fates Combined **Character Artwork only**, SoniPro, Fantasy Life LtTim 4x, SMT Strange Journey Redux, Wii Fit Plus, NSMB Wii custom title (one DDS), BioTes Star Wars Battlefront II. Family counts: GC 76 unchanged, Wii 39→41, 3DS 37→42, PSP 82→83. Manual RAR/page references do not count as verified installations.
- Host runs `39401863622` (`5a700c59`), `39403154413` (`b6a522ec`), `39403548138` (`230c6b95`), `39403837549` (`52edb48d`): 26 exact records retained, successful or not, compared against real artifact JSON and artifact ZIP digests. RAR listing run `39403843636` on `52edb48d`: AppleBoi PoR (4,470 DDS / GFEE01), Serbagz Radiant Historia (2,442 PNG / 00040000001C8F00), Brahian TF2 Spanish (ULES00925). Native RAR import is unsupported; external extraction + existing folder import is required, not counted as an installed archive. No iPhone rendering was validated.
- Preserve regional limits: no validated French/PAL Fire Emblem result. Sebastrion PAL is a research lead without verified original distribution permission; Thorn alias relationship is unresolved. Legacy Link_to_the_past PoR/RD UI remains outside runtime pending format evidence. EagleEyeValor Radiant Dawn HD text requires Riivolution + Graphics Mods and stays outside the plain texture adapter. No downloadable CoD Roads to Victory HD pack was validated. Tales font passes installation but lacks regional evidence; Mario & Luigi WIPs lack archive identity; Project X Zone / Huekage GoS downloads return 404: these remain research only.
- `tools/textures/research/future-switch.json` is metadata only (Engage Cobalt textures, Three Houses outline patch, Skyward Sword HD specialised Ryujinx injection), **never** an active source. All Switch flags false, zero Switch packs in either runtime manifest. Research ledger contains 33 findings, including adaptations/duplicates/blocked hosts. Do not activate these references or infer regional support from renamed folders.

## HD catalogue target 400 — 20 October 2026 (this verification pass complete)

- Maintainer asks for an attempt to reach **400 installable families**, continuing CoD Roads to Victory and Fire Emblem research. Index `2026-10-20.d64e1ff29d79` reaches **352 families** from 295 (+57 families, 60 installation profiles); **48 remain**. Count definition and `count_packs.py` unchanged: distinct projects, working one-tap profiles or exact verified ZIP/7z imports. Never count regional, resolution, format, component or revision variants as extra families, RAR listings, non-HD recolours, mod dependencies or simulated wrong-target imports.
- Work on `Claude` only. No release, IPA or build number allocated. Native core/adapter and app code unchanged from `4850653`; both bundled manifests identical. Every original 377 installable pack object and verification record is unchanged; all 1,072 baseline IDs retained. Report: `docs/hd-textures-target-400-2026-10-20.md`; exact evidence: `docs/evidence/hd-target-400-2026-10-20.json`.
- Gains by console: PSP +7, 3DS +5, Wii +2, GC +1, PS2 +42. Five new one-tap profiles use three pinned creator repository ZIPs. File-host originals stay manual, with creator credits and no rehosting/repackaging. Explicit scopes: Daxter unfinished English HUD; Kirby Wii cancelled WIP; Monster Hunter Forest & Hills partial. The two iZePlayz SMG2 variants are one family; three Ace Combat trilogy game profiles are one family. All existing extraction and memory/prefetch guards are retained.
- **263 raw CI observations / 248 candidate IDs / 30 real host artifact ZIP digests / 15 superseded records** reconciled exactly. Frozen original candidate set: 209/210 IDs observed; final Xenosaga II MEGA transfer unfinished in cancelled batch 3, not retried via another runner/host. Runs `39406754238` and `39416642896` preserve 104 and 33 completed observations before cancellation; resumed batches 1/2 preserve 34 each. Actual wrong/corrected region observations remain separate historical records with registered supersession maps. Corrected-USA Tenchu Wrath (`39431381794`) passes on identical bytes; other corrected runs cover Devil Kings, Akirus DBZ, Basara JP, Silent Hill 3 USA and WWE SVR **2007** USA. No known failed archive is retried to work around protection/quota; target/extraction changes are the only native rechecks.
- `verify_packs.py` retains actual ARMSX2 excluded subtrees. `build_catalogue.py` rejects an otherwise successful ARMSX2 plan whose explicit serial evidence identifies another target; correct the source and reverify, or remove its verification URL. Tests: production two-game exclusion regression and three real trilogy profiles; `test/texture_catalogue_publication_test.py` (real wrong/corrected observations plus NCAA control); existing verifier checks (16). Standard anonymous single-file Yandex API support in CI has seven boundary tests and a real Prince of Persia success (provider SHA-256 agrees); God of War times out and stays unavailable. The app’s existing verified-file reader accepts the same ZIP/7z, size and SHA fields; no host whitelist blocks the import.
- Withheld successes: exact PAL edition unresolved for Maximo RotK, THPS3 Headfonehead and Scooby-Doo; Drakengard creator NTSC vs flat PAL filename conflict; Dynasty Warriors archive identifies a different game; Fatal Shadows Last Round PC ZIP still needs its corrected-USA-target check, while its verified Redux profile remains available in the same family. Robo’s Paint Job is explicitly non-HD (creator), HCTP 2x requires nero619’s game modification and exclusive alternatives, Silent Scope ZIP method 14 is unsupported. Do not promote any of these from `status: ok` alone, mix alternatives, silently rename another serial, or relax native bounds.
- Research: 475 GBAtemp pages returned 403; public spreadsheet parsed and 20 folder/file probes plus additional original-author sources reviewed. Rehosted collections, paid files, obsolete-hash CCKrizalid releases and challenged/quota-protected hosts remain excluded. Daxter’s public original download works: a viewer’s generic sign-in navigation was not an access wall. Two original LOTR ModDB alternatives are RAR, not interchangeable with unavailable GameFront ZIPs. Wii menu channel banners are not separate in-game families; F-Zero Squadaloo has primary reports of severe gameplay failures and stays outside availability.
- CoD Roads to Victory: no downloadable HD pack validated; web recompilation is a separate runtime, and the 82nd Airborne addon targets unupscaled MoH Heroes 2 skins. Fire Emblem GC/Wii: no new complete French/PAL archive validated; AppleBoi PoR RAR needs external extraction, Panda_Venom original protected, Sebastrion PAL original permission/file unverified, Thorn alias unresolved, legacy UI hashes unverified, EagleEyeValor RD text requires Riivolution/Graphics Mods. TenGu314’s indexed French RD announcement credits a Bl4ckH4nd base, but the original video account is closed and no file/permission is verified. Awakening P1 and Fates Character Artwork are previous-phase verified parts; Echoes original download returns 403. Switch: four future references only, **all flags false, zero runtime packs**, no engine activation or phone rendering claim.

## HD catalogue final renewed exploration — 20 October 2026

- A subsequent explicit maintainer request authorizes this additional catalogue campaign on `Claude`; the earlier frozen 352-family snapshot remains the historical Build 496 delivery. The new index is `2026-10-20.8a38a79c72f0`: **355 distinct installable families (+3)**, **164 one-tap + 191 verified manual-import families**. Still 45 short of 400, 46 short of exceeding it. No release or IPA is produced by this catalogue task; concurrent Build 497 PSP work is preserved.
- Three verified original ZIP additions: Project Mirai DX HD buttons (2 PNG sheets; exact `0004000000148C00`, UI only), Kharij Tekken 6 (`ULUS10466`, partial; 933 missing INI targets and 20 case mismatches), DinoPandaa30 Alpha Sapphire v0.0.3 (`000400000011C500`, 336 PNGs + pack.json, partial). Creator-announced French text for Alpha Sapphire is not a device-language test. Original URLs, pinned versions, native folder plans and exact SHA-256/size only; no rehosting or archive edits.
- Raw successful observations: run `39449348701` (Mirai/Tekken) and `39450675080` (Alpha Sapphire). Run `39449572012` selected zero packs and is not verification. The workflow now exposes `parts=releases` for the existing release verifier; generator, counter, archive-verifier and runtime implementation are unchanged. All 1,083 old runtime objects and 663 old raw observations are unchanged; bundled/published manifests are identical. Do not rerun unchanged checks.
- Six genuinely new project references: one verified now, four pending (Turok Evolution RAR, Wii Dawn of the Dragon, WaveLength Spider-Man 2, original Webbed Up live download 403), one future Switch MHGU project. Mirai and Tekken are two re-reviewed older exclusions, not new discoveries. Search-result rows, forks, region/controller/component variants and candidates are not families.
- Correct the earlier Type-0 decoder/URL claim: the exact delivered PPSSPP binary supports KTX2/UASTC/Zstandard; raw `.basis` is distinct and unsupported. Type-0 stays outside availability pending its 11.2 GB payload and Skybladecloud v2 patched-game mapping. No new core was built or run for this static evidence.
- Fire Emblem: no new verified family or French/PAL installation. Switch: five future references total, zero runtime entries, runtime/engine/automation flags false and no verified payload claimed. Report: `docs/hd-textures-final-review-2026-10-20.md`; evidence: `docs/evidence/hd-final-review-2026-10-20.json`; research: `tools/textures/research/hd-final-review-2026-10-20.json`. No iPhone rendering/performance test is claimed.

## Interface Liquid Glass 548 — 25 octobre 2026

- Refonte Liquid Glass de l'interface sur `Claude` (commits `4973e6c` style, `598d35d` interface, `bf40834`/`8346491`/`8e1f3ad`/`5a9f150` recette) : système de design centralisé (`LiquidGlassTheme`, `GlassSurface`, contrôles en verre), écran Réglages › Thèmes › Interface utilisateur (style, barre d'onglets, surfaces, animations, aperçu, 12 langues), espacement des réglages, migration des dialogues/menus/encarts/pages, pages natives Textures HD et Triches. `lib/main.dart`, moteurs, imports, sauvegardes, catalogues et `game_launch_dialog.dart` inchangés. Rapport : `docs/liquid-glass-ui.md`.
- Validation : `flutter analyze` sans erreur ni avertissement (107 informations préexistantes) ; 367 tests sur 35 fichiers, en série (`--concurrency=1` : deux suites partagent le fichier SQLite). Deux constats préexistants consignés : `test/retroarch_baseline_scope_test.py` est rouge sur la base (dix empreintes périmées) et remplacé par une garde directe sur l'hôte 542 ; le cas « rapid focus changes » de `neo_glass_bubble_test.dart` attend une clé absente depuis `ab7997a` et est exclu par son nom. Le test clavier d'`airplay_navigation_test.dart` attendait 75 ms sous le throttle de 128 ms de `GamepadNavigation` : passé à 150 ms.
- Livraison : la recette `liquid-glass-ui-delivery.yml` remet, dans l'arbre de travail du runner seulement, tout chemin que l'interface ne possède pas (propriété = sources du reçu local `docs/evidence/liquid-glass-ui-local.json` + fichiers de recette) à l'arbre de la livraison 546 validée `6c6c6241` (hôte 542, correctif MeloNX 544, Core RPCS3 546 `343649293c` run `40230183096`), car les sessions RPCS3 et MeloNX poussent en continu ; historique Git intact.
- IPA privée **0.0.8 (548)** depuis `5a9f1502973f3b9c37ddbc5f32abb5457b86ee80`, run `40238111186` (`checks`, `cold` réussis) : artefact chiffré `12616880071` pour `build-utils/delivery-548-recipient.pem` (archive SHA-256 `b2f639dc…befdd`), IPA `RewindBox-Build548-5a9f150…-cold.ipa` **186 486 048 octets**, SHA-256 **`b1266a1a0ca352399cf657615a804bcb33455eeb8fd1ab42ea1829aec151be96`**, égale à `SHA256SUMS`, déchiffrée, re-vérifiée et remise. Runs antérieurs : `40233811199` (test clavier), `40235992468` (IPA scellée, vérificateur cherchant des clés interpolées ; SHA-256 `291b2e50…91d3b`, non distribuée). Reçu : `docs/evidence/liquid-glass-ui548-delivery.json`. Aucune validation iPhone. **Ne pas réutiliser le numéro 548.** Prochain numéro RPCS3 : 549+.
