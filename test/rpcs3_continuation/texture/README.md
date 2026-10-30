# RPCS3 texture continuation

The production delta is `texture-delta.patch`, against the authenticated
`rpcs3-full` postimages of RewindBox Claude
`de8169848ecfa9c95946fc957861263a9fd1b879`. It changes three files, without changing
the canonical RewindBox patch itself. `texture-review-report.json` contains the
baseline/candidate/patch hashes, final extracted-program hashes, original proof
locations and limits. Applying the delta to a separate baseline copy reproduces
all three candidate files byte for byte.

## Implemented changes

1. **Release completed pooled images under iOS memory pressure.** The recyclable
   image pool is populated by retirement callbacks, so detached pool entries have
   already completed their GPU use. The old pressure path queued them again under
   the current event instead of freeing their allocations. The new path purges
   active temporary views through the existing deferred release mechanism, then
   unlocks the cache mutex and destroys the detached retired pool outside both
   cache locks. Late driver returns retain their own accounting. Other platforms
   keep the old disposal path. This does not free active/in-flight images.
2. **Normalize 3D/cube depth after assigning and validating it.** The former
   unnormalized-coordinate path divided by the zero-initialized attribute depth
   before assigning the actual depth. The division now follows that assignment.
   The zero-pitch case, 1D/2D coordinates and normalized-coordinate path remain
   unchanged.
3. **Omit clears for fully overwritten small 2D atlases.** A bounded, allocation-free
   sweep over at most eight color-copy rectangles proves full destination
   coverage. Complete strip/tile assemblies can therefore omit the color clear.
   Depth, unsupported geometry, alias, gaps and larger recipes keep their existing
   behavior. The GPU barriers, copy ordering, copy extents, background uploads and
   image layout transitions are preserved. The original single-full-first-copy
   optimization is unchanged.
4. **Use 64-bit atlas coverage areas.** The old percentage calculation overflowed
   signed 32-bit arithmetic, including a 256×256×512 texture. This could accept
   an incomplete GPU reconstruction and skip the existing CPU background-fill
   fallback. Target area, accumulated copy area and bounding-box area products
   now use 64 bits. This retains the existing sum-and-bounds coverage heuristic,
   including its treatment of overlaps.
5. **Reuse the owned command-buffer fence for synchronous DMA submission.** The
   primary submission now uses the fence already owned by the command buffer.
   It avoids constructing and destroying a separate fence at each readback and
   retains ownership if the bounded wait fails. A failed wait takes the existing
   Vulkan error path before the command buffer can be reset. On success,
   `command_buffer::begin()` recycles the completed owned fence and resets the
   buffer, including its existing status check of the already-signaled fence.
   The auxiliary submission path, explicit timeout, queue/semaphore
   ordering, EIDs, heap snapshots and occlusion restoration remain unchanged.
6. **Reject incomplete DMA readback before consuming bytes.** `imp_flush()` now
   checks the existing event-wait result before `flush_dma` and any CPU copy or
   deswizzle. A timeout uses the existing error handler instead of continuing with
   incomplete data. The event is a member-owned object, so it remains alive when
   this error unwinds the call.

`texture-four-fixes.patch` preserves the first four changes separately.
`texture-dma-extension.patch` applies only changes 5 and 6 on top of those four.
`texture-delta.patch` includes all six against the original baseline.

## Verified results

| Scope | Result |
| --- | --- |
| Retired image pressure | 6,429 assertions; 1,000 interleaved driver returns. A modeled 256 MiB retired pool is destroyed immediately while 2 MiB of active temporary images remain deferred. Baseline retained both until completion. Destruction is asserted outside both mutexes. |
| Unnormalized depth | 69,120 configurations; baseline has 15,120 incorrect depth scales, candidate has zero. |
| Atlas clear control flow | 84,000 synthetic recipes, 694,279 assertions; 22,263 fewer recorded color clears, 61,737 unchanged cases, 14 conservative fallback checks, zero helper allocations. Independent pixel painting confirms output coverage and copy ordering. |
| Atlas area arithmetic | 117,756 cases; 11,591 baseline mismatches against a wide independent arithmetic oracle; all 99,928 non-overflow baseline cases remain unchanged. Candidate passes the oracle. UBSan reproduces signed overflow in the baseline 256×256×512 probe. |
| DMA ownership and waits | Per version: 32 fence-error cases, 32 event-error cases, 20 success cases. Recorded unsafe command-buffer resets / pending-fence destructions / incomplete readbacks are 24 / 24 / 8 before and 0 / 0 / 0 after. Eight successful primary readbacks remove eight local fence creates and eight destroys. |

Candidate scopes passed AddressSanitizer and UndefinedBehaviorSanitizer.
LeakSanitizer is disabled. The area sanitizer matrix excludes the baseline
except for the deliberately failing, captured baseline-overflow probe. A zero
`baseline_mismatches` field in that sanitized report is not a baseline pass.

The final depth extraction is byte-identical to its earlier tested extraction;
its proofs are reused after an unrelated area-arithmetic edit in the same header.
The final pressure and atlas scopes were tested after independent review added
the out-of-cache-lock destruction and explicit alias fallback. The manifest
authenticates each reuse by comparing the final generated program hash with the
original proof's program hash. Source generation does not run tests or compile.
The DMA changes were validated separately by the renderer reviewer using the
complete extracted cleanup and flush methods, command-buffer lifecycle methods,
fence constructor/destructor, chunk state, flush locking and existing Vulkan
error handler. Its original report and generated program were copied unchanged
to `results/dma-independent`; their source-file hashes match the final candidate.
The four texture scopes were only regenerated and hash-checked after this DMA
extension, without rerunning their test matrices.

These are source-extracted host checks with recorded Vulkan boundary calls.
The image sizes in the pressure adapter are lifetime counters, not real GPU
allocations or a device RSS measurement. The atlas adapter verifies destination
footprints and control flow, not native Vulkan/Metal execution or interpolation.
There is no full Core build, iPhone measurement, FPS claim, frame-time claim or
confirmed fix for the three reported games.

## Portable runners

Copy these seven files together into the desired test directory:

- `verify_texture_lifetimes.py`, `pressure_adapter.cpp`, `depth_adapter.cpp`
- `verify_atlas_coverage.py`, `atlas_adapter.cpp`
- `verify_atlas_area.py`, `atlas_area_adapter.cpp`

Every runner accepts `--source`, `--baseline`, `--compiler`, `--report-dir`,
`--sanitize`, and `--generate-only`. The lifetime runner's baseline path is
optional provenance; run it with `--source` pointing at the baseline plus
`--expect-baseline` to reproduce baseline observations. `--only pressure` and
`--only depth` avoid unrelated compilations. `--name` remains an optional label
when using the default report destination.

Examples, using explicit absolute source roots and output directories:

```sh
python3 verify_texture_lifetimes.py --source /path/to/core --baseline /path/to/baseline --report-dir /tmp/texture-generated --generate-only
python3 verify_atlas_coverage.py --source /path/to/core --baseline /path/to/baseline --report-dir /tmp/atlas-generated --generate-only
python3 verify_atlas_area.py --source /path/to/core --baseline /path/to/baseline --report-dir /tmp/area-generated --generate-only
```

Omit `--generate-only` to compile and execute the requested scope. Add
`--sanitize` for ASan/UBSan; `--compiler clang++` selects a compatible alternate
compiler. The test code requires a C++20 host compiler. The area oracle also uses
the GCC/Clang `unsigned __int128` extension. No Vulkan SDK or physical GPU is
required by these extracted host tests.

The independent DMA runner is
`../renderer-review/portable/test_dma_wait_ownership.py`, with its neighboring
`fixtures` directory. The manifest records its absolute source path and the
original report path for integration alongside the other renderer checks.

## Source review and deferred work

Retirement ownership was reviewed through `cached_image_reference_t`,
`release_temporary_subresource`, the resource manager, the existing frame-end
pool trim and the renderer's pressure entry point. A separate reviewer confirmed
that atlas copy and scaled/typeless copy paths preserve the destination
rectangles used by the coverage proof. Neither review is a device run.

Temporary-subresource identities omit some layout/recipe fields, and CPU writes
may need stronger invalidation of cached composite images. Neither investigation
produced a complete, safely reproducible production failure for this cycle; no
speculative concurrent-cache change was retained. Layer-count omission in the
recyclable-image key did not produce a demonstrated alias among the present
call sites. These are investigation candidates, not claimed fixes.
