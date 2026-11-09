# MeloNX lot 7: persistent Metal binary archives in MoltenVK (record)

9 November 2026, Claude Code session 012mUASkkFGHaPcEUx9dsp8q. Board entry: `docs/AI_TASK_BOARD.md`, "MeloNX lot 7".

**Status: prototype kept isolated, NOT integrated, not enabled.** MeloNX's MoltenVK, its pin, every Core and every IPA
are unchanged. No IPA (maintainer). Nothing was built or run for iOS. Three kinds of figures, never mixed: iPhone
(MoltenVK's own statistics in journals already received), macOS runner with its real Metal device ("Apple Paravirtual
device", macOS 26.7.2 25G332, Xcode 26.6), and nothing from the simulator. No iPhone figure exists for the prototype:
nothing here is an FPS or stutter gain.

## 1. Embedded MoltenVK

Khronos v1.4.2 `db66022459ffb663aa2b50f6b018bc2e124f5edf`, built by `melonx-moltenvk-rebuild.yml` from
`build-utils/melonx/moltenvk-rebuild.json` with no patch; pinned binary `41cb207d…` (run 41653781749, iOS arm64,
minimum 15.0). RPCS3 links another MoltenVK build: untouched.

## 2. The five stages, and the one an archive serves

1. Guest program to SPIR-V (Ryujinx translation): not concerned.
2. SPIR-V to MSL (SPIRV-Cross in MoltenVK): not concerned.
3. MTLLibrary creation from MSL (`newLibraryWithSource`, MVKShaderModule.mm:582): NOT covered by MTLBinaryArchive. An
   archive is searched with the functions of an already created library.
4. Pipeline state creation (`newRenderPipelineStateWithDescriptor` MVKPipeline.mm:3101,
   `newComputePipelineStateWithDescriptor` :3135; every pipeline goes through MVKRenderPipelineCompiler or
   MVKComputePipelineCompiler): the only stage an archive serves.
5. Persistent cache load (MVKPipelineCache::readData compiles each library again, stage 3): not covered.

## 3. iPhone evidence already in hand

[device-moltenvk-statistics.json](device-moltenvk-statistics.json): MoltenVK's own statistics lines in the private
journals (Hogwarts Legacy, IPA 624-684), aggregates per session; the journals are not in the repository.

- In play, the ten sessions with at least 20 s of native shader work: library creation from MSL 81.1-83.5 %, pipeline
  state creation 16.5-18.9 % (IPA 684 pid 26658: 359 libraries 33.9 s, 878 pipelines 7.9 s; IPA 672 pid 18409: 1407
  libraries 314.6 s, 1313 pipelines 71.3 s).
- New libraries in play equal new SPIR-V conversions (359/353, 1407/1398): first encounters, which no cache filled on
  this device can serve.
- At launch, 26 of the 35 reports show a warm system Metal cache: at most 2.1 s of libraries and 1.0 s of pipelines
  (IPA 684: 6995 libraries in 1.0 s, 1792 pipelines in 0.8 s), IPA updates included (first sessions of 674, 676, 684).
- The 9 other launch reports (IPA 640, 658, 672: fresh or growing caches, or a cold system cache) compile libraries
  for 13.5-65.8 s and pipelines for 2.4-12.6 s (14.7-18.3 %): the ceiling of an archive at such a launch.
- IPA 693 (board): a 536 s start read as every library of the 780 MiB pipeline cache compiled again at load (stage 3).

## 4. Stand-alone Metal probe (macOS runner)

`test/melonx_metal_binary_archive/metal_probe.mm` and `run_probe.py`; synthetic shaders: 19 libraries, 48 render and 6
compute pipelines; every session a new process; Metal's own cache (`com.apple.metal` directories) found by comparison
and removed for the "system cache removed" sessions. Three runs: 42693416166, 42695873585, 42699272657.
[metal-probe.json](metal-probe.json).

| Measure | Result |
| --- | --- |
| Libraries from MSL (19) | cold 1057-1746 ms (18 samples); warm 3-4 ms; with the archive kept and Metal's cache removed 1147-2544 ms (what remains) |
| Render pipelines (48) | compiled cold 292-480 ms; warm 5-10 ms; from the archive 31-49 ms with Metal's cache removed, 4-10 ms warm; 48/48 under MTLPipelineOptionFailOnBinaryArchiveMiss in each of the 12 reuse sessions |
| Compute pipelines (6) | 1.8-3.2 s in every case on this device, also when served by the archive: no gain |
| Variant left out | strict: miss in 0.06-0.30 ms ("failed to find compiled pipeline functions in binary archive"); then compiled by the normal call |
| Collection order | adding after creation does not recompile (8-20 ms for 48); adding first is slower (728-924 ms, then 38-52 ms) |
| File | 1.76 MB for 54 pipelines, saved in 5-19 ms, loaded in under 1 ms, no footprint change at load |
| Damaged copies | cut, empty or text files are refused at load; a file with overwritten bytes loads, and Metal alone does not always notice (one sample still served 48/48 after 2 KiB were overwritten; no wrong draw among the 24 pipelines the probe draws): hence the prototype's own checksum |
| Threads | lookups from four threads during additions and saves: no error (smoke test) |

## 5. Prototype on MoltenVK's real path

[Patch](../../../build-utils/melonx/metal-archive/moltenvk-v1.4.2-binary-archives.patch) (sha256
`69e7e86110f6455ce11c6279614f2a4d5c0949631289a7e694e125e39c9b3391`; MVKPipeline.h/.mm and MVKDevice.h/.mm, 710 lines
added), [notice and settings](../../../build-utils/melonx/metal-archive/README.md). Off unless
RBX_MVK_BINARY_ARCHIVE_DIR is set; the library then behaves as upstream.

- **Lookup**: inside MVKRenderPipelineCompiler and MVKComputePipelineCompiler, on the very descriptor MoltenVK compiles
  (functions, specialization, formats, vertex layout, options), in the compiler's own block (same device lock and
  compile timeout): `binaryArchives` + MTLPipelineOptionFailOnBinaryArchiveMiss. A miss runs the unchanged
  compilation. The strict option never leaves the lookup: a miss fails a creation only with the test setting.
- **Collection**: after a compilation, a copy of the descriptor on one utility serial queue; the creating thread never
  waits. Lot 5's replays and warm-ups go through the same two functions, so they are served and collected like draws'
  pipelines, with their existing order and priority. No managed change, no draw or dispatch removed, no shader changed.
- **Files**: identity directory (pipelineCacheUUID = MoltenVK revision, OS version, GPU family, argument buffers; OS
  build; GPU name; no IPA number); one segment per session named by session token, size and SHA-256 prefix; temporary
  file then one rename; earlier segments never rewritten. Damaged = removed; refused by Metal = kept once, removed at
  the second refusal.
- **Bounds**: 8 segments, 192 MiB, 4096 additions and 64 MiB per session, 256 pending collections, no collection under
  384 MiB of available memory (iOS).
- **Saves**: at 64 additions, when the application reads its pipeline cache data (MeloNX's pipeline cache checkpoints
  and close) and at device destruction (one synchronous drain: the addition or save in progress finishes, pending
  additions are dropped, one last save).
- **Isolation**: the Vulkan pipeline cache, the guest shader cache and the .variants journal are never read or written
  by it; an archive failure leaves them as they are.
- **Independent review** (rb-core-review, source only, on the first version `9ad7b2c6…`): a compiler object leaked on
  every hit and strict miss; the lookup ran outside upstream's compile timeout; two devices of one identity could share
  a file; bounds could be overshot; archives were destroyed before the queues. All fixed in `69e7e861…`, then run
  again.

## 6. Execution through Vulkan (macOS runner)

`run_mvk.py` builds MoltenVK `db660224` for macOS with the patch (library `a47777f3…`, 10 981 168 B, carrying the
prototype's strings) and runs `mvk_archive_test.cpp` through Vulkan: 62 graphics and 6 compute pipelines from synthetic
SPIR-V (two color formats, blending, a vertex buffer layout, specialization constants; one color attachment, no depth,
one sample), 33 MSL libraries, 38 draws and 6 dispatches hashed; isolated directories; every session a new process.

- Run 42699272657 (commit `bb49a541`, reviewed patch): 32 sessions, every expectation met.
  [moltenvk-run-2-reviewed.json](moltenvk-run-2-reviewed.json).
- Run 42695873585 (commit `dd35ce19`, patch before review): 28 sessions, every expectation met.
  [moltenvk-run-1-before-review.json](moltenvk-run-1-before-review.json). A slower runner: compare within a run only.

| Session | MSL libraries (33) | Graphics creation, 62 calls (their libraries included) | Compute (6) |
| --- | --- | --- | --- |
| Reference, cold, no archive (2 per run) | 1.60-1.98 s; run 1: 2.96-3.15 s | 1.35-1.39 s; run 1: 2.03-2.18 s | 2.25-2.46 s |
| Reference, system cache warm | 7 ms | 0.20 s; run 1: 0.21 s | 1.95 s |
| Collection, cold (68 collected) | 2.02 s | 1.58 s; run 1: 2.08 s | 2.53 s |
| Reuse, system cache warm (68/68 from the archive) | 6 ms | 0.18 s; run 1: 0.20 s (the 62 hits: 12 ms) | 1.89 s |
| Reuse, system cache removed (3 per run, 68/68 from the archive) | 1.66-1.77 s; run 1: 2.32-2.56 s | 0.95-1.01 s; run 1: 1.34-1.51 s (the 62 hits: 34-40 ms) | 2.06-2.29 s |

- **Gain, where there is one**: system cache removed, 62 graphics creations cost 0.34-0.44 s less than the cold
  reference (run 1: 0.53-0.83 s). Libraries remain. Compute pipelines gain nothing (1.6-1.9 s for the six hits, as when
  compiled). With a warm system cache: no gain.
- **Stage 4 alone, seen by accident**: a session without archive that followed sessions served by the archive compiled
  the 62 graphics pipelines in 0.52 s (run 1: 0.61 s) with warm libraries, against 0.20 s when Metal's cache had them.
  Pipelines served by an archive do not seem to enter Metal's own cache: a lost segment costs their compilation again.
- **Reuse proven**: 68/68 pipelines from the archive in a new process, strict (a miss would fail) and not strict. Same
  draw and compute hashes in the 26 sessions of the main shader set (run 1: 22), compiled or served by the archive.
  The thread rounds use other sets whose creating sessions do not draw: their next-launch result has no reference.
- **Miss and fallback**: strict, the variant left out is refused (VK_ERROR_INITIALIZATION_FAILED; lookup 0.08 ms, run
  1: 0.21 ms) and the 68 others served. Normal operation: it is compiled as before (21 ms, run 1: 96 ms), collected
  (0.1 ms, run 1: 0.4 ms) and saved as a second segment (64.8 KB), the first byte-identical; then strict with two
  segments serves 69. A lookup miss adds at most 0.21 ms to a creation (ten sessions with misses).
- **Collection cost**: 68 additions 10-23 ms single-threaded, up to 43 ms with four creating threads (longest single
  addition 12.5 ms), all on the utility queue; saves 1.3-18.9 ms each, 1.90 MB; segment check and load at most 6.6 ms
  per launch; device destruction 8-20 ms in collecting sessions (2-4 ms in the references).
- **Failure cases**: save failure (read-only directory) counted, the published segment untouched and still serving 68;
  4 KiB overwritten: removed by the checksum, everything compiled as before, new segment saved (with the check off,
  Metal still served 67 of 68, run 1: 63, same result); cut file removed; a file Metal refuses kept, then removed at
  the second launch; other identities never loaded, the older pruned; oldest segment pruned at the bound; 10-addition
  bound held (58 not queued); memory floor: 68 collections held, lookups still served.
- **Concurrency**: three rounds per run of creation from four threads with pipeline cache reads (22-34), saves every 4
  additions (21-22 saves) and the device destroyed at once: no failure, 68 collected, 68 served at the next launch.
- **Memory**: 20.0-20.8 MiB peak footprint in sessions that do not collect, archives loaded or not; 25.9-28.8 MiB in
  sessions that collect the 68 pipelines (+6 to +8 MiB for a 1.9 MB file); reopening the session's archive from its
  file after each save made no measurable difference (26.5 against 27.2 MiB).

## 7. Decision

Not integrated, not enabled.

- The gain exists only for stage 4, and only when Metal's own cache is cold.
- Stage 3, which is 81.1-83.5 % of the iPhone's native shader time in play and the reading of the IPA 693 cold start,
  is untouched.
- The in-play work is first encounters: in no cache.
- With a warm system cache (26 of 35 launch reports, IPA updates included) there is nothing left to save.
- Compute pipelines gained nothing on the runner.
- An OS update invalidates the archive with the system cache; a change of MSL or compile options changes the
  functions, so the archive misses too.
- No iPhone measure of the prototype exists.

## 8. Limits of the prototype

- Memory: the session's own archive is held in memory until saved (bounded by 4096 additions or 64 MiB per session),
  plus mapped segments (192 MiB of files, 8 segments by default).
- The checksum pass reads every segment once per launch on a utility thread.
- Hits are never collected again: a pipeline whose segment ages out is compiled once more.
- A kill loses at most the additions since the last save.
- Not judged without a device: hits for the descriptor kinds the test set lacks (depth or stencil attachments, several
  color attachments, multisampling, tessellation, multiview); whether an addition recompiles after Metal evicted the
  binary; the cost of saves and of the checksum pass on iOS storage; any gain on the iPhone.

## 9. Sources and identities

[run.json](run.json). Branch `work/melonx-lot7-metal-archive`: probe `73bed99f`, `39af6cc2`; prototype `dd35ce19`;
review fixes `f32bc99f`; final sources `bb49a541` (the commit of run 42699272657); notice `aa28e2cc`; evidence
`e43c9970`. The same files are on `Claude` by cherry-pick, with identical git objects: tree of
`test/melonx_metal_binary_archive` `284034c3`, patch blob `589b044b`, workflow blob `13290072`.
`.github/workflows/melonx-metal-archive.yml` starts only for pushes that touch its own files; it is not a Core gate and
builds no IPA. No Core contract, no pin and no dependency of the application changed.

## 10. Protocol for Hogwarts on the iPhone (not requested)

Needs the integration owner for the MoltenVK pin and an IPA.

1. Build the patched MoltenVK for iOS with the existing workflow (`patch` and `patchSha256` in
   `moltenvk-rebuild.json`), pin it.
2. Set RBX_MVK_BINARY_ARCHIVE_DIR per title before the Vulkan device is created.
3. Same route three times: launch 1 (collection), launch 2 (reuse), launch 3 after deleting the app's com.apple.metal
   cache directory.
4. Read the "RewindBox Metal binary archives" line (hits, misses, collected, saves), MoltenVK's "Compile MSL into a
   MTLLibrary" and "Compile MTLFunctions into a pipeline" totals, peak footprint and the render-thread pipeline waits.

Expected from the journals: a visible effect only in launch 3, bounded by the pipeline share.

## 11. Lever the evidence points to instead (another lot, not started)

Stage 3: library creation deferred to first use when the pipeline cache loads (the 693 stall and part of the 7 s
load), and fewer distinct MSL variants per shader.
