# Build 499 — selective ARMSX3 / RPCS3 improvements

Status: candidate, Core and IPA build pending. No physical-device validation or measured FPS gain.

The baseline is Claude `ef8b4b9db09ac142e801ee43e65221261d49cae4`, including delivered Build 498, its verified PSP memory contract, 418 directly installable HD families and native RAR/public-host support. Only the RPCS3 Core is rebuilt.

## Evidence and scope

The supplied ARMSX3 IPA is `ARMSX3-22348-bbe9ce84.ipa`, 38,406,391 bytes, SHA-256 `0db92aea054b716863eeea486d2102656f20e9a58f8872742ae405deeb43385d`. Info.plist identifies `com.armsx3.Harness`, marketing version 0.1/build 1, minimum iOS 17.4, Xcode 27.1 SDK 27.1; the embedded engine string is `22348-bbe9ce84`. It is an unencrypted arm64 executable, UUID cfd7cfb2-d427-3691-9ad4-573c4a8caab4. The main executable has 50,158 symbol-table entries. LLVM 22.1.8 is embedded. These are static observations, not performance measurements. Public ARMSX3 master was pinned at `2e1a02c3aecaa6841e161cfeda4b6c57cd5cacbd`; the supplied hash does not resolve publicly.

NeoStation materializes the unchanged XITRIX/rpcs3 upstream `22f1152783cef1f7e04af7b1c895173e28fd5b03` plus a single canonical delta with 226 postimages. This cycle changes exactly three core postimages: SPULLVMRecompiler.cpp, SPUThread.cpp and Emu/CMakeLists.txt. The other 223 are unchanged.

## Selected changes

1. Correct the u64 SHUFB insertion pattern. The old pattern matched a malformed shuffle and missed the valid single-lane insert; scalar differential testing finds one wrong entry among the 30 patterns. Use upstream RPCS3 d7f4c3507be3aaef631067aca9f0d0c8c89e9eea, also public ARMSX3 e99467b5bafddcb467e77ccd670e815a02c9218e. Preserve every other lowering and the generic fallback.
2. Enumerate a conditional direct branch's taken target first, followed by its fallthrough, retaining one target if both coincide. Use upstream RPCS3 9c8e4349b7296c5e14d7fde9cc4d88a8b69f2fca, ARMSX3 ddd902e766799f57f68be386fe10891f289d5b3d. Test with the actual decoder, forward/backward/self branches and local-store wraparound.
3. Independent compile-path diagnostic reduction: ordinary block-build messages use trace (the logger filters it before formatting at its default notice level). A decrementer read no longer forces a complete disassembly in normal use. Explicit SPU debug and failed debug-file-write diagnostics remain. Aggregate JITPROF/SPUPROF remain unchanged. This removes avoidable compilation work; it is not a proven steady-state FPS gain.
4. Extend the configure-time SPU object identity to cover SPUThread.cpp and SPUOpcodes.h, which affect branch discovery. Existing identity/relocation validation, size limits, eviction and stored symbol resolution remain. The SPU cache rebuilds once; PPU codegen inputs and PPU object naming remain unchanged.

## Preserved and rejected

The ARM64 TBL byteswap, byte arithmetic fast paths, x86-only guards, NEON reservation copies, wake-on-range-lock-clear, bounded persistent SPU objects, InstCombine calling-convention correction and cache-pressure fallback already exist. No duplicate import. NeoSwap allocation/eviction/storage services, coherently aliased guest memory, GPU retirement, JIT arenas and entitlements remain unchanged. No ARM host address is serialized by these changes.

The newer ARMSX3 FIFO fetch fix targets a puller whose public GET reflects fetched commands. Our older FIFO publishes consumed positions, so the patch's prerequisite is absent; do not transplant a newer FIFO state machine. Android scheduling/Turnip linear images and driver patches are platform-specific. Private graphics-pipe conversion strings in the iOS IPA lack matching public implementation and measured benefit here. Do not copy third-party binaries or enable unmeasured driver paths. Memory-cap increases and global SPU compile pauses are not adopted.

## Validation

Local production-snippet test: 30 masks x 1,024 independent random inputs, zero wrong masks in the candidate vs one in the exact old translator. 96 conditional-branch cases: zero wrong target orders vs 80 old mismatches (16 coincident-target cases already correct). 4,096 non-debug decrementer compilations: zero full dumps vs 4,096 with the old diagnostic block; explicit debug and debug-file-write failure still dump. These are host component results, not gameplay or iPhone throughput. The original pre-499 source hashes are recovered by reversing only the exact proposed edits before compiling the negative controls.

The canonical patch was regenerated in bytes and reapplied on a pristine upstream clone, reproducing all 226 postimages. The existing Build 487 helper/metrics/boot/retention tests pass locally under ASan/UBSan; on this restricted Linux host LeakSanitizer cannot inspect /proc, so leak scanning was disabled only for that local rerun. The default macOS Core gate retains its sanitizer settings. No failure is presented as device proof.

Core preflight, full iPhoneOS compilation, produced-binary checks, IPA composition and artifact verification are pending. Exact identities and measured build results will be appended after completion.

## Credits and testing on device

RPCS3 contributors, elad335, the SHUFB upstream author as recorded by the linked commit, ARMSX3/jpolo1224 and XITRIX. Imported changes retain GPL-2.0 source/licence attribution; no supplied binary component is redistributed.

For God of War III compare the same edition/update, firmware, settings and thermal state. Discard the first SPU-cache rebuild session. Use internal CONFIG_LAYERS, SPUWARMUP, JITPROF, SPUPROF, COREPROF, guest-frame/emu-state samples and NeoSwap counters to separate compilation from gameplay and native UI frames. Compute average/1% low from guest frames and frame times, compilation stalls and storage/page-fault latency. No Jetsam/IPS request. A 30-FPS objective is not declared reached without those device measurements.
