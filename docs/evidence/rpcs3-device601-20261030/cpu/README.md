# MFC full queue: decrementer collection and persistent wake

The retained change modifies two host bodies in `SPUThread.cpp`:

1. `process_mfc_cmd()` collects an expired `SPU_EVENT_TM` on its owner before
   testing the pre-acceptance IRQ. WRCH deliberately suppresses ordinary
   `cpu_work()` interrupt collection while its command is unaccepted.
2. The deadline callback in `spu_dec_intr_timer` uses `spu->notify()`, retaining
   the thread notification latch as well as notifying the CPU-state waiter.
   A callback arriving between the IRQ test and wait registration must remain
   observable even when the state snapshot already includes its pending flags.

The timer still publishes pending work only. It never sets the guest event
from another thread; the owner validates its current decrementer value.
The current WRCH PC, queue ordering, list acknowledgement and barriers remain
unchanged. No semaphore value is forced and no guest timeout is introduced.

The source-extracted regression passes both normally and under ASan/UBSan:

| Case | Verified result |
| --- | --- |
| Deadline before entry, before state snapshot, before actual wait | Three baseline blocks; three candidate IRQ deliveries |
| Interrupted BARRIER/EIEIO/SYNC, all 32 tags | 96 commands accepted exactly once after list acknowledgement and actual IRET |
| Existing late SNR | Four schedules preserved |
| Masked, disabled, frozen, stale-token and stop cases | Eight cases retain the expected behavior |
| Concurrent deadline producer and owner | 64 IRQ deliveries with the current PC and unaccepted command preserved |
| Remove owner collection | Regression test rejects the mutation |
| Remove persistent notification | Regression test rejects the mutation |

Files `mfc-decrementer-plain.json`, `mfc-decrementer-asan.json` and the two
mutation reports bind the runner, adapters, generated program and native source
inputs. The test extracts the real MFC drain, `cpu_work`, event collection,
decrementer read/arm/cancel, IRQ entry, timer publication, notification latch,
wait construction, unstall helper and IRET. Clock/timer queue, reservation
predicate, CPU-state dispatcher and kernel wait are explicit adapters. Real
guest DMA, LLVM translation, iOS kernel scheduling and gameplay are not tested.
LeakSanitizer and ThreadSanitizer are not claimed.

The original lost-wake reproduction predates the production edit. The final
comparative runner reconstructs the earlier source from the provided baseline
and checks that the remainder of `SPUThread.cpp` and every other extracted
method are unchanged. Both independent omission mutations reproduce a failure,
so neither half of the correction is justified solely by a test that mirrors
the intended final result.

## GOW3 evidence and remaining scope

The historical build 597 wait is on RSX label `0x60300510`, expected `0x1A24`
and observed `0x1A23`. Its producer is not identified by the retained traces.
The build 601 GOW3 attempt never reaches guest execution: its twenty preparation
windows have zero acquire watches and no MFC producer snapshots. Therefore no
log proves that this decrementer defect caused that game's introduction freeze.
The correction must not be described as a verified GOW3 freeze resolution or
an FPS improvement.

A separate read-only probe demonstrates the analogous missing collection when
the full queue depends on an LR interrupt. That probe adapts the reservation
predicate and does not validate real reservation memory. No LR correction is
retained here: collecting once would not wake a thread for a later reservation
loss. A correct next step needs owner collection plus a registered reservation
notification and the existing data/generation validation, including writes
without normal reservation notification. Indefinite polling or forcing a label
is not a substitute.

## Upstream comparison

The primary source checked is RPCS3/rpcs3 commit
`9508444d31338e89a4f4cee1d0cee1800c96d2c1` (30 October 2026):
https://github.com/RPCS3/rpcs3/blob/9508444d31338e89a4f4cee1d0cee1800c96d2c1/rpcs3/Emu/Cell/SPUThread.cpp

Its full-queue prefix is retained in `upstream-fullqueue-prefix.txt`. It still
uses `do_mfc()` followed by an indefinite state wait and has no
`spu_dec_intr_timer` implementation. The retained correction is a verified host
protocol correction in this fork, not an upstream patch transplant. The
previous pre-acceptance-PC, SNR, empty-list, MMIO and restoration fixes remain
in place.
