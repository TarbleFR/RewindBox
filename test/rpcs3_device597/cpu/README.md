# Device597 CPU and signal causal-diagnostic checks

These checks extract the affected production bodies from a candidate core and
compare them with the exact core delivered in IPA597. They do not build RPCS3,
execute LLVM, emulate a game or measure device FPS. The native tests use explicit
VM/GPU/wait-backend adapters; the bounded signal history itself is the actual
production header with real standard C++ atomics.

## Files to integrate

Place these eight files in `test/rpcs3_device597/cpu/`, together with this README:

- `run_late_snr.py`
- `late_snr.cpp.in`
- `run_signal_tests.py`
- `signal_trace_test.cpp`
- `signal_rsx.cpp.in`
- `signal_dma_suffix.cpp`
- `signal_list_suffix.cpp`
- `audit_codegen.py`

Do not copy a full historical SPUThread.cpp fixture, the one-time
`patch_signal_hooks.py` mutation script, compiled executables or Python caches.
The delivered 597 baseline should be reconstructed in a temporary core tree by
reversing the reviewed device597 `core-delta.patch` from the exact integrated
candidate. Use `git apply --reverse --check` before applying the reversal; verify
the original SPUThread.cpp SHA256 is
`4d138e76afc25d12d8eff04a5794153cbe9a4562c8dcbe5d9eac274ab4c927d3`.
This inverse delta is for the device597 follow-up lot, not the earlier continuation
lot, whose inverse reconstructs an older baseline.

A complete baseline already provides `rpcs3/Emu/Cell/MFC.h` and
`Utilities/Thread.h`. If the test tree is intentionally sparse, supply the
unchanged upstream files via `--support`: `support/MFC.h` and
`support/Utilities/Thread.h`. No other support file is needed. Prefer the full
pinned baseline over duplicate fixtures. The local historical Thread.h support
copy differs from pinned upstream only by an extra final LF; extracted bodies
are unchanged, and source hashes explicitly record the chosen input.

The signal DMA/list checks reuse these two already reviewed adapter preambles
through `--repo`, without modifying them or rerunning their previous suites:

- `test/rpcs3_continuation/cpu/dma_mmio_prefix.cpp`
- `test/rpcs3_continuation/cpu/dma_list_harness_prefix.cpp`

The cache audit also reads
`docs/evidence/rpcs3-continuation-20261030/codegen-identity.json` from `--repo`.
Only the unchanged, authenticated LLVM backend digest is reused from this
receipt; no LLVM source download or code emission is claimed.

## Commands for the Apple source preflight

The existing Apple preflight supplies its authenticated compiler wrapper through
`CXX` and the host SDK through `HOST_MACOS_SDK`. Both native runners parse `CXX`
with `shlex.split`; `--compiler` can explicitly override it. They pass the SDK as
`-isysroot` when set. Linux-only sanitizer linker flags are omitted on Darwin.
There is no need to select a separate compiler or bypass the preflight wrapper.

Set `REPO`, `CORE`, `BASELINE` and `OUT` to absolute paths in that preflight.
These task-specific variables are examples, not persistent environment changes.
Run the affected modes only:

```sh
python3 "$REPO/test/rpcs3_device597/cpu/run_late_snr.py" "$CORE" \
  --baseline "$BASELINE" --report "$OUT/late-snr-plain.json"
python3 "$REPO/test/rpcs3_device597/cpu/run_late_snr.py" "$CORE" \
  --baseline "$BASELINE" --sanitizer address,undefined \
  --report "$OUT/late-snr-asan.json"

for mode in helper rsx dma list; do
  python3 "$REPO/test/rpcs3_device597/cpu/run_signal_tests.py" "$CORE" \
    --baseline "$BASELINE" --repo "$REPO" --mode "$mode" \
    --report "$OUT/signal-$mode-plain.json"
  python3 "$REPO/test/rpcs3_device597/cpu/run_signal_tests.py" "$CORE" \
    --baseline "$BASELINE" --repo "$REPO" --mode "$mode" \
    --sanitizer address,undefined --report "$OUT/signal-$mode-asan.json"
done

python3 "$REPO/test/rpcs3_device597/cpu/audit_codegen.py" "$CORE" \
  --baseline "$BASELINE" --repo "$REPO" --report "$OUT/codegen.json"
```

These are ten native executions plus one compiler-free cache audit. The helper
also has a successful local Linux ThreadSanitizer receipt. Reproduce that
additional concurrency check only where the host/toolchain supports it:

```sh
python3 "$REPO/test/rpcs3_device597/cpu/run_signal_tests.py" "$CORE" \
  --baseline "$BASELINE" --repo "$REPO" --mode helper --sanitizer thread \
  --report "$OUT/signal-helper-tsan.json"
```

The current receipts use GCC 13.3 on x86_64 Linux. The Apple commands are prepared
for a later authorized preflight and have not been executed on an Apple host by
this source task. `aarch64Executed` in a future late-SNR receipt refers to the
native harness host architecture, not execution of the full emulator or LLVM.

## Assertions and expected JSON

Every native run must have `passed: true`, no sanitizer diagnostic and
`traceHeaderSHA256` equal to the candidate's raw IOSSignalTrace.h digest. For the
frozen five-file source lot that digest is
`4a667c7b40839349aa7be20508873312f6a5f4e0d304bee6e71b552920b5d8f6`.
The generated program and source hashes are recorded; the runners regenerate
and compare inputs after execution to reject an edit racing a test.

| Mode | Required result checks |
| --- | --- |
| late-SNR | `baselineLostWakeSchedules=4`, `candidateInterruptDeliveries=6`, `maskedOrDisabledCases=18`, `stopAfterRegistration=2`, `handlerAckRetriesAcceptedOnce=2`, `concurrentProducerConsumerCases=128`; owner snapshot, disabled-instrumentation late IRQ and old-session drop booleans true; `guestTimeoutAdded=false` |
| helper | capacities 64/32, 40,000 concurrent write attempts, positive coherent snapshot and concurrent retained-stall read counts, allocation trap true, disabled/session/overflow checks true, retained stall survives resolution and 200 healthy acquires, `storageBytes=38928` on the recorded host |
| RSX | 80 unresolved polls produce 3 trace records, no invented signal, CPU commit follows executed store, GPU-deferred/no-op/failed stores produce no CPU commit, prior release retained, disabled mode records none |
| DMA | 320 before/after cases, 44 recorded commits, failed-copy and old-session completion drop checks true, GET/unwatched paths unrecorded, `noAdditionalGuestRead=true`, `dmaValueExplicitlyUnknown=true` |
| list | 88 before/after cases, 10 recorded commits, 8 zero-element no-commit cases, GET/unwatched paths unrecorded |
| codegen | exactly 5 old aliases preserved plus 1 exact new SPUThread alias; correct path maps, wrong path/future SHA do not; `candidateWithExactAlias==baselineIdentities`; PPU `a987639e9f838d1c`, SPU `477a3fa442d27917` |

Concurrency counts vary with scheduling; do not freeze the exact positive count
of snapshots or drops. Fixed storage size can vary by ABI; production also
asserts its four bounded containers occupy no more than 40 KiB. Source SHA must be
`254336c40c34189064bea97d4ab25021929b763f8c9f60ff72b433196cb61440`, compatibility
file SHA must be
`7891895841c71c6cd361f8b227284b6447ec1ce7ac0e455c69b18a050128d8fa` for this frozen
lot. An altered source requires fresh review; do not extend the alias broadly.

## Limits

The late-SNR test extracts the real MFC drain, notification latch, channel,
event delivery, IRQ dispatch and wait-list construction. Its OS wait backend is
a condition variable, and its atomic update adapter uses mutexes. It verifies
notification registration/interleavings, not Apple ulock behavior or ARM atomic
ordering. The real owner-published diagnostic helper is executed.

RSX/DMA/list checks execute the complete affected production functions with
bounded simulated memory, real test copies and explicit host adapters. They do
not execute Vulkan, guest PPU stores, reservation primitives or actual SPU code.
ThreadSanitizer covers the production diagnostic header, including concurrent
latch/consume, not the complete emulator.

The cache audit reproduces the actual ordered CMake hash recipe and checks host
helper scope and external binding. It does not execute CMake or LLVM and does
not compare newly emitted objects. None of these results establish an iPhone
FPS gain or identify the producer of GOW3's missing semaphore value.
