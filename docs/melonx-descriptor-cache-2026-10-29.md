# MeloNX: descriptor updates, cached data and buffer lookup

This source continuation starts at local `Claude` commit `55fdfeb`, retaining
the ten changes in the [previous continuation](melonx-steady-state-2026-10-29.md).
Five new guarded adapters remove repeated descriptor work, reuse private data,
and reduce buffer/allocator bookkeeping. No game
quality, synchronization policy, memory entitlement or runtime telemetry changes.

The results below are controlled host executions of production code with
explicit resource/native boundaries. They do not establish iPhone FPS, process
RSS, or that a particular operation dominates Hogwarts Legacy or Persona 4.

## Identical scalar descriptors retain their clean state

Four `DescriptorSetUpdater` setters now compare the complete resulting binding
record before marking its category dirty. They still resolve every view/sampler
and perform all usage, preparation and barrier operations. Mutable texture
buffers and latent buffer references retain conservative invalidation. Command,
program, copy, rebind and explicit forced-dirty paths remain active.

The production records, setters, invalidations, normal dispatch and template
writer pass 145,135 assertions per variant with equal semantic/resource digests.
For each of four 100,000-assignment probes, redundant updates and binds change
from 100,000 to zero, while the same 100,000 applicable getter/usage/barrier
effects remain. Both variants allocate zero in these probes. Tests include
view/buffer transitions, mutable backing, direct images, nested calls, exceptions
and changes made by resource getters.

## The exceptional descriptor fallback uses bounded stack storage

The non-template overload of `UpdateAndBind` created six forms of unit arrays
inside its binding loops. Two one-element stack spans now provide that temporary
storage, once per invocation outside all loops. The complete authenticated
`DescriptorSetCollection` consumer fixes the span and calls Vulkan synchronously;
no pointer survives that call. Existing zero-handle filtering is preserved.

The real fallback/consumer/dispatch fixture passes 10,457 assertions per variant,
with equal semantic/resource traces, including a nested call from the native
double, short/missing arrays, null handles and partial native failures. Six probes
of 20,000 invocations with eight bindings each reduce allocations from 7.68 MB
(image info arrays) or 5.12 MB (buffer-view arrays) to zero, with identical native
updates. This benefit is limited to the fallback after template failure; it is
not claimed as an ordinary-frame or device-wide acceleration.

## Constant-buffer snapshots reuse their existing exact-length arrays

`CacheEntryFromBuffer.UpdateData` previously allocated fresh texture/sampler
`int[]` snapshots on each rebuild. It now copies into its existing private array
when the exact length is unchanged. Combined/separate transitions and overlapping
input spans retain distinct ownership when required, including the sampler span
ignored in combined mode. Real allocation failures preserve the established
partial state at the remaining allocation sites.

The complete cache fixture passes 1,292 scenarios and 5,894 assertions per variant
with identical digest, bindings and setter calls. Two input-drift controls are
rejected before mutation. For 200 warm rebuilds:

| Snapshot length | Combined control | Separate control | Candidate, either mode |
| --- | ---: | ---: | ---: |
| 16 words | 17,600 B | 35,200 B | 0 B |
| 1,024 words | 824,000 B | 1,648,000 B | 0 B |
| 32,768 words | 26,219,200 B | 52,438,400 B | 0 B |

The final row is a synthetic 128 KiB workload, not a captured game buffer.
The same words are still read, compared and copied. This removes allocation of
replacement snapshots; it does not reduce byte-copy volume or add a retained pool.

## Simple containing-buffer lookups avoid collecting every overlap

`BufferCache.GetBuffer(MultiRange)` previously allocated ten output slots,
collected all interval hits, deduplicated them and then selected the first
containing buffer. A stack-owned predicate now visits the same tree/subrange
order and can stop at that result. Existing physical synchronization, write
notification and sparse decisions still execute.

Consecutive duplicate visits are ignored and at most eight pure `Contains`
tests are attempted. If that budget is exhausted, the original collect/dedup
path runs unchanged. This prevents an unbounded regression on highly aliased
misses. The generic traversal documents physical visits without deduplication;
only the reviewed identity-equality `MultiRangeBuffer` caller uses it.

The real tree/range/list classes and exact binding method pass 4,815 scenarios
and 23,112 assertions per variant, with equal digest. Four source-drift controls
are rejected. Simple hits/misses change from 104 allocated bytes to zero. Later
hits and fragmented misses retain the old allocations and add bounded work;
those rows are slower in the host probes. Their timings are single-pass samples
with resource Range/Equals instrumentation, not unbiased device measurements.

## Allocator splits and merges move fewer list elements

Successful ordinary splits replace their surviving interval in place and insert
at most one extra interval. Freeing next to one or two existing intervals also
replaces the merged interval in place, removing only the redundant next interval
when both neighbors merge. First-fit choice, alignment, lock and native-memory
policy are unchanged. Unusual allocation configurations keep the historical path.

The complete allocator and independent wide-integer model cover 64,000 random
operations, 1,620 exhaustive cases, 441 zero/wrap/duplicate/overlap histories,
8,000 concurrent operations and native payload/bounds checks. Four executions
have the same functional digest. Warm allocation remains zero in both versions.
For a cycle with a suffix of N entries, prefix-and-tail churn moves 6N→2N list
elements; one-remainder churn moves 4N→0; full fits retain their original count.
These are deterministic movement counts. Some small/full cases are slower in
the recorded single-loop host timing; no universal CPU or FPS gain is claimed.

## Integration and next measurement

The exact receipts, source composition and complete managed Release library
build are under `evidence/melonx-descriptor-cache-20261029/`. Preparation now
authenticates 102 inputs. The new sources compose with all earlier changes;
unchanged suites are reused within their recorded scope rather than replayed.
Source, build inputs and compiled outputs are linked by hashes.
The final incremental integration build succeeds in 26.31 seconds with zero
errors and 21 pre-existing warnings in unchanged sources. Its complete source/
resource input set matches a fresh preparation. A prior experimental integration
included the subsequently rejected purge; its success is not delivery proof for
that rejected variant, and only the final accepted source composition is used.

The single-dependency `Auto` experiment was rejected: its 32-byte saving did not
justify measured regressions on other hot paths. Its rejection summary is kept
to prevent treating it as an untried optimization; no product code from it is
integrated.

The proposed purge of evicted pools' buffer-backed entries was also rejected.
Compute activity can evict a pool still retained by the graphics binding manager;
the older cached entry can mask that stale manager reference. Purging it alone
can force a lookup into a disposed pool. A future cleanup first needs correct
pool reacquisition and a complete compute-to-graphics transition proof. The
experimental purge and its favorable isolated weak-reference tests are not
integrated; existing pool lifetime behavior remains unchanged.

No Apple NativeAOT core, IPA, release or device gameplay is produced here. The
next priority is an authorized Apple build with changed-path checks, followed by
same-scene iPhone frame-time, GC, memory and visual/audio comparisons. Remaining
cache/search changes need their actual game frequency established before
increasing cache budgets or changing further lifetime rules.
