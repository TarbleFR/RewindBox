# MeloNX: readback, barrier and binding costs during gameplay

This continuation follows the six verified changes in local `Claude` commit
`8399607`. It implements four further engine changes, preserving those first
changes and the existing upstream pin. The earlier work and its limits remain
in [the GPU execution report](melonx-gpu-runtime-2026-10-29.md).

The new changes target work repeated during rendering rather than adding
diagnostics or changing resolution, guest synchronization, audio or RAM knobs.
The measurements below execute production code with documented host boundaries.
They are not Hogwarts/Persona frame captures, iPhone FPS or resident RAM results.

## Readback: avoid copying clean data and reuse one local callback

`Buffer.FlushImpl` already owns the renderer's `PinnedSpan` through the final
guest-memory write. The old helper nevertheless copied the entire span to a
new array whenever a virtual dependency existed, even when none contributed
bytes. It now borrows that existing lease and creates its mutable snapshot only
at the first actual modified-range callback, before any backend call could
invalidate borrowed data. A clean read returns the original span.

There is no preliminary dirty check: the same sorted dependencies receive the
same range queries in the same order. One callback per invocation replaces a
new capture/delegate per dependency. The complete consumers' hashes guard their
synchronous non-retention contract; no callback state is shared between
invocations, threads or reentrant calls.

The GPU copy also now uses the clamped modified sub-range length. Previously it
used the entire outer readback length from a sub-range offset, potentially
overwriting unrelated physical bytes or overrunning the buffer.

| Controlled host workload, 200 operations | Control allocations | Candidate |
| --- | ---: | ---: |
| Clean 32 KiB readbacks with a dependency | 6,648,000 B | 89,600 B |
| Readbacks without virtual dependencies | 9,600 B | 0 B |
| Clean GPU-only sync, 1 dependency | 80,000 B | 80,000 B |
| Same, 2 dependencies | 100,800 B | 81,600 B |
| Same, 8 dependencies | 235,200 B | 100,800 B |
| Same, 32 dependencies | 772,800 B | 177,600 B |

The final full-class fixture passes 4,905 assertions per variant with identical
functional digest. It tests the overcopy correction, fragmented mappings,
stable ordering/ties, reentrancy, exceptions and explicit/ephemeral leases.
A modification entirely outside the read window remains reserved, incurs no
copy or physical mutation, and is consumed correctly by a later overlapping
read. In the clean candidate, the original borrowed pointer actually reaches
the guest write; it is not just an equal replacement array. Two consumer-drift
controls are rejected before mutation.

## Vulkan: compact consumed barriers once per batch

The barrier matching helper formerly removed every matching run immediately
from its list. With interleaved stage flags, each removal shifted the remaining
suffix again, up to sixteen shifts in one batch. It now compacts survivors
stably and removes the consumed interval once. The same native calls receive
the same barriers, flags and ordering, with the same batch capacity and forced
fence behavior. No barrier or wait is omitted or combined.

The complete production `BarrierBatch` fixture passes 624 scenarios and 776
checks with identical full barrier/resource/native-dispatch traces and zero
warm-flush allocation. Five timing rounds alternate control/candidate order.

| Interleaved-flags workload | Control median | Candidate median |
| --- | ---: | ---: |
| 128 barriers | 4.61 µs | 1.41 µs |
| 1,024 barriers | 180.9 µs | 26.7 µs |
| 4,096 barriers | 3.225 ms | 0.349 ms |

Tradeoffs remain in the raw evidence: one same-flag barrier measures 60.5→61.4 ns
and 1,024 same-flag barriers 18.9→24.9 µs, with substantial timing dispersion.
The initial experiment is preserved too. These are CPU host workloads, not
driver/GPU latency or proof of a universal speedup.

## Threaded texture arrays: reuse exact-length snapshots with a fixed budget

After the scalar optimization, multi-element bindings still allocated an exact
snapshot array on every update. A shared pool now reuses independently owned
arrays of length 2–4,096. It keeps at most eight cleared arrays per closed
reference type. Texture/image bindings share the texture pool; samplers have
their own. The maximum retained reference-slot storage is 512 KiB on ARM64,
plus the small array/cache overhead. In-flight arrays retain the original
ownership and queue-capacity contract; this is not a bound on all in-flight
memory.

Commands still use only two table references. The producer snapshots before
publication, and the consumer resolves backend identities at execution time.
Return/clearing occurs only after synchronous consumption or unwinding. A failed
producer publication never returns an array that might still be queued. Backend
hashes guard the non-retention contract. Covariant arrays use a read-only span
copy, preserving the old legal subtype-array inputs.

For each of textures, samplers and images, warm update allocations change from
40/88/2,072/32,792 bytes to zero for lengths 2/8/256/4,096. Empty/scalar paths and
lengths above 4,096 keep their earlier allocation behavior. Bursts can still
allocate when the pool is exhausted. The complete-class fixture passes 275,801
control and 285,288 candidate assertions with equal digest, including 30,000
concurrent commands checked element by element, covariance, nested consumption,
exceptions, failed publication, weak references and pool bounds. Nine source/
backend drift controls fail closed.

Paired runs in one process alternate the two real production assemblies over
twelve samples. All twelve pooled-case medians improve in that experiment,
from 4.6% to 38.9%. Unchanged scalar/empty cases also vary, so those ratios alone
do not establish an attributable or device-wide speedup. All samples, rejected
copying experiments and the fixed-budget tradeoff are recorded. The certain
result is less snapshot allocation after reuse, at the cost of clearing and two
short lock acquisitions per pooled update.

## Uniform data: handle packets larger than the 512-word cache

The FIFO's existing complete-packet path can submit up to 8,191 words to a
512-word updater. The old span method threw when such a packet exceeded its
cache. Oversized spans now fill bounded open cache ranges. A scalar word handles
every flush/restart or unusual address boundary, then all registers are read
again before any batch copy. A batch cannot itself trigger a flush or translation.

Spans of at most 512 words remain textually unchanged. No FIFO dispatch or
register/shadow shortcut is added. The final fixture covers 924 small cases,
792 large cases compared against the actual `Update(int)` oracle, 48 injected
errors that really occur, three historical zero-sentinel states and 32
reentrant register mutations. All allocation probes give zero. The normal,
uint32/ulong wrap, capacity, translation/write ordering, exceptions and private
cache state agree with the scalar path for the extended cases.

This fixes support for a formerly failing path. Comparing its new batching with
a scalar oracle is not a speedup measurement against a previously functioning
large-span implementation, nor a measured acceleration of fragmented FIFO
continuations.

## Integration and remaining work

Raw receipts, unchanged-source comparisons and the final managed library build
are in `evidence/melonx-steady-state-20261029/`. A fresh preparation composes all
ten changes; the earlier six results are reused only within their original
scope. These four affected fixtures are new executions. No unchanged engine,
audio, CPU or kernel suite is replayed, and no Apple core or release is built.

The next priority is the authorized Apple NativeAOT build and same-scene iPhone
comparison: Hogwarts and Persona frame regularity, background GC, memory peaks,
graphics/audio and long-session stability. Frequency of the remaining large
snapshot/readback paths must determine further cache or algorithm changes.
No FPS gain is inferred from a successful host build or microbenchmark.
