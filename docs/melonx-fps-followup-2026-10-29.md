# MeloNX: rendering CPU and allocation follow-up — 29 October 2026

## Scope and status

Five additional engine optimizations follow the Hogwarts memory candidate
`a33eee84` (successful engine 80). They change six production C# files through
guarded preparation adapters. The complete managed library builds with the
final adapters, and all five targeted production-code checks pass. Apple engine
81, source `9dd570ee`, also passes on its first attempt: native iOS/simulator
compilation, exported ABI verification and two ARM64 iOS simulator sessions.

The work was prepared against `58809ae6`. Publication preserves the concurrent
RPCS3 follow-up through `7d1ca65c`; those changes and the delivered IPA 593 are
not altered. This is an engine candidate, not a newly delivered application.
Upstream remains `13700519f3abc4e6d7ed8a065b118b2cc59bcd67`, with SDK 10.0.100
and the existing LibHac pin. No rendering-quality setting, new telemetry,
forced GC, guest synchronization shortcut or persistent cache format changes.

The supplied Hogwarts log motivates work on renderer CPU time and managed
allocation as well as memory lifetime: the previously documented slow phase
has a 2.6 FPS median, high renderer activity and substantial background GC.
The new workloads below are controlled host cases, not a capture of that
game's pipeline or texture population. They establish reduced work on the
changed paths; they do not establish an iPhone FPS or whole-process RAM gain.
See the [original log analysis and memory candidate](melonx-hogwarts-memory-2026-10-29.md).

## 1. Pipeline cache: amortized growth and order-sensitive hashes

`HashTableSlim` previously kept 16 buckets and grew a bucket by one element
for every insertion. A large cache repeatedly copied growing arrays. Buckets
now grow geometrically; the table doubles its bucket count when its average
occupancy reaches eight. Rehashing uses stored hashes, allocates each target
bucket once, and publishes the new table only after construction succeeds.
Insertion calculates a key's hash once. Removal clears the vacated tail slot
so an unused entry cannot keep a pipeline alive.

`PipelineUid.GetHashCode` previously XORed the fields and array entries, making
the result insensitive to their order. The fixture's 512 valid permutations
of vertex layout offsets consequently had the same hash. The replacement
weights the existing fields separately and folds the entries in order.
Equality remains authoritative and unchanged. Inactive array tails are ignored
as before. These hashes serve in-memory lookup, not a disk cache key.

| Controlled workload | Before | After |
| --- | ---: | ---: |
| Allocations while inserting 4,096 small keys | 8,519,680 B | 259,448 B |
| Largest bucket in that fixture | 256 entries | 8 entries |
| Hash calls during fixture insertion and lookup | 12,288 | 8,192 |
| Allocations inserting 512 real 1,280-byte pipeline keys | 170,213,376 B | 2,685,288 B |
| Distinct hashes for the 512 layout permutations | 1 | 512 |
| Equality comparisons for 512 successful lookups | 131,328 | 512 |
| Warm 8,192-lookup collision workload, median | 23.2873 ms | 0.5347 ms |

The test also covers 1/4/16/64/512-entry distributed caches, 6,000 mixed
operations, duplicate keys, negative hashes, null values, enumeration, reuse,
and release of removed references. All three variants (control, growing table
only, full candidate) pass 11,355 checks each. A byte-oriented hashing candidate
was rejected because it penalized small/distributed caches; the final arithmetic
hash avoids that observed regression. Timing is descriptive, not a pass gate.

Evidence: [pipeline-lookup-checks.json](evidence/melonx-fps-20261029/pipeline-lookup-checks.json).
The harness compiles the complete production classes with the actual
Silk.NET.Vulkan 2.22.0 structures and struct-array helpers.

## 2. Bindless cache: distinguish keys already distinguished by equality

The two key hashes in `TextureBindingsArrayCache` now incorporate the fields
already compared by their `Equals` methods: pool identity, image/sampler kind,
target, array length, and, for buffer keys, handle index and buffer bounds.
Previously many distinct handles in the same buffer were guaranteed to collide.
No entry ownership, eviction, binding decision or equality rule changes.

For both pool and buffer fixtures, caches of 32/128/512 entries require an
average of 16.5/64.5/256.5 equality comparisons per hit before the change and
one afterward. The 15,531 functional checks preserve all 20,083 binding calls
and the same disposal/eviction outcomes.

In the complete-cache warm benchmark, 512-entry hits fall from about 812 ns
to 115 ns. The extra hash fields cost about 19 ns in the one-entry fixture
(91 to 110 ns), a measured tradeoff for avoiding long collision chains.
Both variants allocate zero bytes per hit. The driver accepts the exact
pristine input used by CI and applies the existing bindless-allocation adapter
to both variants before comparing the new hash behavior.

Evidence: [binding-lookup-checks.json](evidence/melonx-fps-20261029/binding-lookup-checks.json).
The real cache, key and memory-range classes execute; GPU resources are doubles.

## 3. Buffer descriptors: preserve clean state for identical assignments

The three uniform/storage buffer setters already compared buffer identity,
offset, write access and range before changing per-binding state, but still
marked the entire descriptor category dirty unconditionally. `SignalDirty`
now runs at that existing change point. An empty assignment preserves its
previous explicit invalidation behavior.

This does not skip buffer acquisition, `SignalWrite`, mirror handling or
barriers. Already dirty state remains dirty. Program switches, rebinding,
copying descriptor state, command-buffer changes and buffer swaps retain
their invalidations. Review confirmed that a buffer swap still signals the
command-buffer change.

After initial binding, 250,000 repetitions of an identical uniform or storage
assignment previously caused 250,000 descriptor updates and 500,000 binds in
the fixture. Both counts become zero. The 500,000 buffer lookups remain. The
direct storage case gives the same update/bind reduction; the push-uniform
case removes 250,000 redundant extra binds. Forty-four functional checks cover
real changes, reentrant rebinding, nulls, mirrors, ranges, write access, program
and command-buffer switches, and empty assignments.

Evidence: [descriptor-update-checks.json](evidence/melonx-fps-20261029/descriptor-update-checks.json).
Production methods and the normal descriptor update loop execute verbatim.
Vulkan calls and resource managers are doubled, so operation counts are the
main evidence; the nanosecond measurements do not measure driver execution.

## 4. Memory tracking: reuse the containing region without skipping signals

Under the existing tracking lock, `MemoryTracking` remembers one live host
region and one live guest region. Only a nonempty request fully inside the
remembered region uses the shortcut. Creating/splitting or removing regions
invalidates the remembered topology before it changes. Mapping operations
still act on the same live objects and still execute their protection work.

A single-region miss carries its region directly rather than renting an array.
Multi-region requests retain a private snapshot because callbacks can release
the lock or change the region graph. That array is now returned and cleared
in `finally`, including exceptional callbacks. All original signaling, dirty
tracking, exemptions and precise-event handling remain active.

In 1,000 localized events alternating host/guest tracking, range-list searches
fall from 1,000 to two, and array-pool rentals from 1,000 to zero. Requests
moving between single regions also avoid the rental. A throwing multi-region
callback now returns its rented array. The fixture exercises 2,400 topology
changes and produces an identical 26,820-event semantic trace in both variants.
The candidate passes 726 functional checks.

An uninstrumented benchmark with 4,096 tracked regions measures roughly
128 to 26 ns per same-region event. Changing-region and multi-region results
are retained in the receipt, but their smaller differences are not treated as
a reliable speedup. The optimization adds two remembered references, not a
growing cache.

Evidence: [memory-tracking-checks.json](evidence/melonx-fps-20261029/memory-tracking-checks.json).
Twenty production tracking/range classes execute; native memory protection is
doubled. Timing runs are separate from pool-boundary instrumentation.

## 5. Texture data overlap: linear traversal for valid contiguous mappings

`Texture.DataOverlaps` previously restarted a nested LINQ scan for every data
region. Padded array allocations can overlap physically while their data does
not, forcing all N×M pairs to be examined. For contiguous, bounded, ordered
mappings, a two-cursor traversal visits at most N+M−1 pairs.

The original first pair is tested before layout validation, preserving a fast
first match even for a later-invalid layout. If it does not overlap, a lazy
one-byte state validates immutable region ordering, nonnegative sizes and
bounds with wide arithmetic. Initialization resets that state. Mapping bounds
are checked on every call, including after remapping.

Fragmented mappings, holes, short mappings, wrapping addresses and invalid
layouts keep the original path. This includes the reviewed five-layer 1 GiB
integer-overflow case: its positive total size conceals negative/wrapped
offsets, and the original slice exception is preserved. The existing GOB 3D
exception and single-subresource branch remain unchanged. Moving the LINQ
fallback into a helper also removes its closure allocation from early returns.

| Controlled 256-region case | Before | After |
| --- | ---: | ---: |
| Disjoint data with padding, warm median | 1.655 ms | 7.281 µs |
| Same case, first comparison | 1.632 ms | 13.563 µs |
| Warm allocated bytes per comparison | 18,984 B | 304 B |
| First comparison allocated bytes | 18,984 B | 608 B |
| Immediate first-pair match, first comparison | 175 ns | 95 ns |
| Single-subresource allocation | 48 B | 0 B |

The first-pair match uses 304 bytes and never scans the rest of the layout.
No region arrays are retained by this optimization. All 12,170 checks per
variant have the same result digest, including randomized mappings, padding,
aliases, boundaries, 2D/3D layouts, remapping, exceptions and initialization.

Evidence: [texture-overlap-checks.json](evidence/melonx-fps-20261029/texture-overlap-checks.json).
The actual initialization/overlap methods and real size/range utilities execute;
the harness does not create real GPU resources.

## Integration and verification

All five adapters are wired into `prepare_embedded.py`, the embedded input
hash receipt, and five dedicated engine CI steps. Test input hashes match the
final files. A fresh preparation from the pinned source changes exactly six
of the 4,095 compared source/project files relative to engine 80. The final
integrated texture methods also match the tested production-member hashes.

The full managed Release build passes. After the final texture edge-case
adjustment, only that changed production file was copied into the same build
workspace and the incremental library build passed again: 0 errors, 21 existing
platform/analyzer warnings, 28.60 seconds. This Linux managed build is not an
Apple NativeAOT or physical-device test.

- [Exact six-file source delta](evidence/melonx-fps-20261029/source-delta.json)
- [Final preparation input hashes](evidence/melonx-fps-20261029/embedded-inputs.json)
- [Managed build and integration receipt](evidence/melonx-fps-20261029/integration.json)

Independent review covered the pipeline hash/equality contract, table growth,
descriptor invalidation and buffer swaps, tracking topology and callback
ownership, and texture ordering/fallback semantics. The short-mapping and
overflow-layout defects found during review were fixed before publication.

The next useful gameplay validation is the same Hogwarts menu/cutscene on the
same device and settings, recording the exact new engine identity and comparable
warm-cache frame times. No numerical FPS target or whole-app RAM reduction is
claimed from these host tests. The existing IPA 593 still contains its delivered
engine until a separately requested app build packages this candidate.

## Successful Apple engine 81

Source commit: `9dd570ee71c5df9edb5a593c90e1757e17f57d93`.
Source tree: `6da9529ee77447cdd63fbd51e970c09e99c076a0`.
The 27 committed source/test/documentation blobs match the verified local
files, with concurrent RPCS3 work preserved in the parent tree.

[Run 40827952992](https://github.com/TarbleFR/RewindBox/actions/runs/40827952992)
is successful on attempt 1. All five new production-code gates pass on the
macOS ARM64 runner. The run compiles actual `ios-arm64` and
`iossimulator-arm64` NativeAOT libraries and verifies exported ABI symbols.
The job takes 14 min 47 s; native compilation takes 4 min 31 s and the iOS
application smoke step 4 min 22 s.

The exact simulator library passes two consecutive homebrew sessions on
iOS 26.5, with the original homebrew SVC confirmed, initialization/idempotency,
teardown and stale-session refusal checked. Simulator core SHA-256:
`9181688313618dbe54c05e825bffb21ee6ef88b9868188f5080481e19116d08a`.
These sessions do not render gameplay/video or measure physical iPhone FPS;
the runtime receipt explicitly leaves JIT and physical-device testing false.

Artifact:
[MeloNX-engine-9dd570ee](https://github.com/TarbleFR/RewindBox/actions/runs/40827952992/artifacts/12878071074),
ID `12878071074`, 102,641,031 bytes. SHA-256 from the upload log and artifact
API, which agree:

```text
157d76bd129af0c1e04acc878259c795c4982d188a340101b1b4e2b9f7b4eb52
```

The archive was not separately downloaded and rehashed in this session.
Reuse this exact verified engine artifact when preparing the next IPA instead
of rebuilding unchanged sources. The delivered IPA 593 identity remains intact.
Complete CI results, host measurements from the Apple runner and runtime
proof: [apple-engine.json](evidence/melonx-fps-20261029/apple-engine.json).
