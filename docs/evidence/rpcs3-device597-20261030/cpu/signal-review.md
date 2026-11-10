# Device597 CPU correctness and causal signal diagnostic — final source lot

This lot fixes a reproducible missed notification in the full SPU MFC queue and
adds bounded evidence for the unresolved GOW3 semaphore wait. It retains the
existing597 fixes. The new tracing distinguishes a requested label release, an
executed CPU label store, a deferred GPU release and a completed SPU DMA range.
It never writes a substitute guest signal, advances the FIFO on timeout or
removes a guest ordering barrier.

## What is established

Delivered597 GOW3 session4 still waits on address `0x60300510`, expecting `0x1A24`
and observing `0x1A23` after 2,001,715µs. The prior 595 observation is the same
address with adjacent values `0x6F0E/0x6F0D`. Those logs establish the missing
value, not its producing thread or the cause. The new source cannot be claimed
to fix that scene until the same scene runs with it.

The restored GOW3 windows 14/15/16 have 13.66/12.99/9.56 measured FPS, zero shader
or SPU compilation and about 3.339/3.395/3.048 SPU CPU cores. Measured poll/sleep
and VM-wait times do not justify a blind scheduling or spin-policy rewrite.
These are user-device observations of 597, not measurements of this candidate.
The authoritative parsed input is `device597-analysis/observed-build597.json`.

## Real correctness change: late SNR while WRCH waits on a full queue

The delivered 597 full-queue path drains deferred work, tests pending interrupts
and then waits indefinitely on CPU state plus the native thread notification
latch. A later SNR sets event count, but `set_events()` notifies the waiting SPU
only if `ch_events.waiting` was registered. The full-queue WRCH did not register
it. Its platform-wait callback measures elapsed wait time and does not poll
`ch_events` as an alternative. A stalled DMA list that needs interrupt-handler
ACK can therefore remain asleep until an unrelated wake.

The changed `process_mfc_cmd()` registers `ch_events.waiting` atomically before
checking the IRQ when the queue remains full and interrupts are enabled. It
clears registration on wake, stop and before the non-unwinding `g_escape()`.
If `do_mfc()` freed a slot, no registration was made. The handler still resumes
the current unaccepted WRCH, preserving the prior 597 retry contract. No event
count is consumed by registration and no timeout is introduced.

Production-extracted native tests reproduce four lost-wake schedules in 597.
The candidate passes six early/late IRQ deliveries, 18 masked/disabled cases,
two stop cleanups, two handler-ACK retries accepted exactly once and 128 real
producer/consumer thread cases. The OS wait backend is an explicit condition
variable adapter; this proves the notification protocol, not Apple ulock or
hardware atomic ordering. Disabled instrumentation preserves the fix.

## Signal and producer evidence

`rpcs3/ios/IOSSignalTrace.h` provides fixed storage for 64 events, 32 producer
snapshots with 16 MFC commands each and one retained stall context. All plain
payloads are copied under nonblocking `atomic_flag` try-locks. A contended slot
is skipped and counted; there is no allocation, spinlock loop or new wait in
emulation. A native allocation trap and concurrent ThreadSanitizer run pass.
The four fixed containers occupy 38,928 bytes on the tested host, with a 40 KiB
compile-time upper bound; small process counters and sequence atomics are
additional. A returned global snapshot is a collection of coherent individual
records, not a simultaneous snapshot of every emulated thread.

The last watched non-flip label address is retained between acquires. This lets
a later acquire be correlated with writes that occurred after the preceding
acquire and before the new one. The first watch time and every address change
remain visible. Event sequence IDs and producer serials are process-unique and
support deduplication. All timestamps supplied by production hooks are host
`get_system_time()` microseconds.

At the existing semaphore stall boundary, the helper latches a bounded copy of
the recent history and published producer rows. Resolving the acquire does not
consume it. Ordinary healthy acquires cannot rotate it out of the event ring.
The reporter can take it later subject to its 30-second detail quota. A new stall
may replace an older pending incident, and that replacement is counted. Tests
verify retention after resolution and 200 healthy acquires, busy-slot behavior,
replacement and concurrent latch/consume.

### Exact source coverage

| Hook | What its event establishes |
| --- | --- |
| `nv406e.cpp::semaphore_acquire` | Actual address, expected value and values already observed by the existing atomic acquire read; one begin/stall/resolve/abort boundary, never one event per poll |
| `nv406e.cpp::semaphore_release` | The guest requested a release; this is not a completed store |
| `nv47_sync.hpp::write_gcm_label` | `rsx_cpu_commit` only after the actual CPU atomic store; delegated GPU release is `rsx_gpu_deferred`; failed store/no-op has no CPU-commit record |
| `SPUThread.cpp::do_dma_transfer` | A successful ordinary non-GET DMA transfer overlapped the watched label; commit only after actual copy/store completion, including accurate and relaxed paths |
| `SPUThread.cpp::do_list_transfer` | The real inline PUT copy completed over the watched label; generic fallback is covered by the ordinary DMA hook |
| `SPUThread.cpp::ios_publish_mfc_snapshot` | The SPU owner published its own queue, pending command, IRQ/event state and SNR counts at a full-queue wait/wake/IRQ/stop/ready boundary |

No additional guest-memory read was added after a DMA copy. A diagnostic load
there could outlive the range lock. DMA records therefore have
`value_valid=false`, value 0 as an unused field and
`value_is_written_argument=false`. Their range completion and a later acquire's
observed value are separate observations. A CPU RSX commit carries its actually
stored argument and sets `value_is_written_argument=true`. Requested/deferred
arguments remain explicitly different from actual commit.

Producer capture runs only on the owner thread. Reporters never read another
SPU's live non-atomic `mfc_queue`, PC, IRQ fields or FreezeDump. Each row includes
`pc`, `return_pc` (`srr0`), queue size/barrier/fence/stall/tag masks, event
bits/mask/count/waiting, interrupt enable, SNR counts, the unaccepted command and
up to 16 queue entries. `published_us` and `serial` identify freshness.
`last_progress_us` means an observed decrease in queue size, not arbitrary guest
computation progress. Only full-queue MFC waits are covered; this is not a census
of every SPU wait.

PPU direct writes, PUTLLC/PUTLLUC and other reservation stores, and actual
completion of GPU-deferred label writes are outside this coverage. Only one
recent label is watched; first-watch boundaries and address changes leave gaps.
A partially failed transfer is not reported as a whole-transfer commit. Other
direct JIT store paths are not generally intercepted. The current ordinary
SPULLVM PUT/SNDSIG route uses the C++ functions, and list routes also call C++,
so those current routes are covered by these hooks. Absence of a write record
must never be reported as proof that no write occurred.

### Reporter contract

- `signal_trace::reset(session, true)` at the existing iOS profiling session
  reset; supply a new monotonically increasing nonzero ID for each start or
  restore. Parent integration owns `Performance.cpp` and this call.
- `summary()` returns `session`, `enabled`, current `watch` and `totals`. Use the
  existing 5-second reporter for a light summary.
- `snapshot()` is non-destructive and returns up to 64 events and 32 producer rows.
  It is intended for bounded diagnostics, not ordinary full dumps every window.
- `take_stall_snapshot(snapshot_result&)` consumes the one retained incident
  only when the reporter's detail quota allows. Keep its incident acquire ID
  and time separate from the current watch. Dump queue entries only for blocked
  producer rows, together with publication time and serial.
- `enabled` is atomic. New event/producer publications retain the session
  captured before the operation. A completion from an old session is discarded;
  stale row memory is filtered without needing an unsafe concurrent reset.

Counters are deliberately process totals, not per-session counters reset while
old producers can finish: `events_published`, `events_dropped`,
`history_overwritten`, `stale_session_dropped`, `producer_published`,
`producer_dropped`, `producer_replaced`, `read_busy`, `watch_changes`,
`stalls_total`, `stall_latched`, `stall_overwritten`, `stall_dropped`. Reporter
window deltas are possible. Snapshot gaps, ring overwrite, producer-ID modulo 32
collisions and lost retained incidents must remain explicit. Old publication
age must not be described as a live blocked state without qualification.

### Cost review

The normal non-full MFC command short-circuits before loading diagnostic enable:
no diagnostic clock read, queue copy, file write or atomic publication. Full
queue transitions alone take an owner snapshot and host timestamp. A snapshot
copies at most 16 entries once per transition; it does not poll another thread.

DMA hooks first test enabled state and range overlap. Only a matching watched
word obtains the watch token, and only successful completion takes a timestamp
and appends its event. No extra guest read occurs. RSX non-flip acquire/release
boundaries do take timestamps while diagnostic mode is enabled; this is a real
cost, not a zero-overhead claim. There is no newly added per-poll clock, record
or formatted message. The retained detailed copy is made only on the existing
stall boundary. Text formatting and file retention belong to the parent
reporter/app lot, outside these source hooks. No host timing or iPhone FPS gain
is claimed for this instrumentation.

## Cache compatibility is exact and limited to the immediate 597 baseline

The final SPUThread.cpp raw SHA256 is
`254336c40c34189064bea97d4ab25021929b763f8c9f60ff72b433196cb61440`.
`JITCacheCompatibility.cmake` adds exactly that hash at `Cell/SPUThread.cpp`,
mapping to597's effective hash
`b9bc0cfeaeaac3a913e41e7890c7e14b758bd52efebdf56acdea343d9c12a1f4`.
All five existing mappings remain byte-for-byte intact. Wrong path, unknown
future hash and every other input still invalidate normally.

The audit restores the three changed host bodies, removes the diagnostic
include and new owner helper, and recovers the complete delivered 597
SPUThread.cpp exactly. SPUThread.h/layout, translator, native helper signatures,
LLVM emitters and helper bindings are unchanged. The inspected LLVM call helper
declares an external function, updates its native mapping and emits a call;
cached objects bind the current host function body rather than embedding these
changed C++ bodies.

The real ordered CMake recipe has 21 PPU and 33 SPU inputs. Reproducing it gives:

| Source/mapping | PPU identity | SPU identity |
| --- | --- | --- |
| Delivered597 | `a987639e9f838d1c` | `477a3fa442d27917` |
| Candidate without the new exact alias | `a987639e9f838d1c` | `6987b1df811a7338` |
| Candidate with reviewed exact alias | `a987639e9f838d1c` | `477a3fa442d27917` |
| Future mutated SPUThread.cpp | unchanged | `7f6dd90c44603c6f` |

This is source-scope and recipe evidence. CMake/LLVM were not executed; no newly
emitted object comparison or Apple binary validation is claimed. The one
unmaterialized unchanged LLVM backend digest comes from the authenticated597
receipt; all other source inputs are read. Toolchain/backend pins and existing
runtime settings keys remain required.

## Verified tests and reproducible deliverables

Eleven final native runs pass: late-SNR, helper, RSX, DMA and list in plain and
ASan/UBSan modes, plus helper ThreadSanitizer. The helper test exercises 40,000
concurrent write attempts and concurrent retained-stall consumers. RSX verifies
80 unresolved polls generate only 3 trace events and no invented signal. DMA
compares 320 cases and 44 successful records; list compares 88 cases and 10 records,
including 8 zero-element no-commit cases. All use the frozen final header and
production bodies. The cache audit passes separately.

The complete portable command set, exact expected JSON checks, adapter scopes
and required eight test sources are in `test/README.md`. The scripts accept
explicit candidate/baseline/repo/report paths, respect the preflight compiler
wrapper and SDK, and avoid Linux linker flags on Darwin. Current native receipts
are GCC 13.3/x86_64 Linux. Apple source preflight, core compilation, iPhone replay
and FPS measurement remain unperformed for this lot.

`signal-source-record.json` records before/after/raw/LF digests of all five core
files and the exact delta. `cpu-device597-signal.patch` has SHA256
`5ba3420689a0b3078c7b9ac4eb88827e9d4544678f7d0ffcdd61302544dc58b3`; it passes
application check against exact597 and reproduces all five candidate postimages.
CRLFs in both RSX files are preserved. `codegen-review-final.json` records the
exact source and compatibility hashes plus the recipe cases. Individual native
receipts are `late-snr-signal-{plain,asan}.json` and
`signal-{helper,rsx,dma,list}-{plain,asan}.json`, plus
`signal-helper-tsan.json`. The final proof index authenticates their contents.

## Next evidence and optimization decisions

After an authorized build, replay GOW3's fresh intro and retain the latched
`SIGNALCAUSE` incident even if it resolves before a reporting window. Its first
useful outcome is to distinguish an actually committed overlapping write, a
requested/deferred-only release, a published MFC queue waiting for ACK/IRQ, or a
coverage gap. An MFC row must be evaluated with its age and matching session.
A candidate producer still needs a command/address linkage; unrelated blocked
SPUs must not be labeled the cause.

If the missing signal's source lies outside captured C++ DMA/RSX paths, extend
the specific uncovered writer only after the trace identifies that gap. PPU or
reservation-store instrumentation cannot be inferred from missing records.
The heavy warm GOW3/AC compute work remains a separate performance question;
this synchronization repair and diagnostic lot supplies no new FPS proof.
No app build, IPA, CI dispatch, push or release was performed by this agent.
