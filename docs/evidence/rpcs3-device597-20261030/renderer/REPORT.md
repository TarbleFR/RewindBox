# Renderer source corrections after RewindBox 597

## Scope and integration

This isolated source lot starts from the delivered 597 canonical sources at app commit `293f7feba68eddb0dc7f4a5ec3940b209cc5de35`, on XITRIX RPCS3 commit `22f1152783cef1f7e04af7b1c895173e28fd5b03`. It contains two renderer corrections and the subsequently requested bounded causal observations. No Core build, CI dispatch, IPA, push or release was performed by this renderer task.

The authored delta is `renderer-delta.patch`. It changes these four upstream paths:

| Path | Actual change |
| --- | --- |
| `rpcs3/Emu/RSX/VK/VKVertexBuffers.cpp` | Use the actual uploaded vertex range as the cache key and fingerprint address; observe differences from the old key on iOS. |
| `rpcs3/Emu/RSX/VK/VKDraw.cpp` | Refresh shader state when host sampler metadata changes, including the cyclic-depth fast update; record only the corrected transitions on iOS. |
| `rpcs3/Emu/RSX/VK/vkutils/sampler_shader_state.hpp` | Small snapshot of metadata consumed by shader selection and texture uniforms. |
| `rpcs3/ios/IOSRendererCausality.h` | Fixed-capacity, nonblocking diagnostic producer and window/session drain API. |

`VKVertexBuffers.cpp` was previously an untouched upstream file, absent from the 319 canonical postimages. Its exact pinned preimage is frozen in `fixtures/VKVertexBuffers.before.cpp`, Git blob `d9e9cee9e2d8b4b5f126f9f0b183baf7323c1c61`. `fixtures/VKDraw.before.cpp` freezes the existing 597 postimage. `fixtures/TextureUtils.h` supplies the exact pinned descriptor definition for native tests.

`renderer-manifest.json` records complete source, fixture, test-script and evidence hashes. Applying the delta to a fresh fixture-based directory with `git apply --check` and `git apply --whitespace=error` succeeded. All four resulting files match the candidate byte for byte.

Preservation audit: 318 of the original 319 postimages are byte-identical to the starting materialization; only `VKDraw.cpp` changes. The original materialization already contains 24 CRLF files whose canonical manifest hashes use LF text. Both the base and candidate retain those bytes; the audit distinguishes this preexisting line-ending representation from source edits. All 319 base files match the original canonical hashes after CRLF normalization. No global normalization was performed.

## 1. Vertex cache keys now describe the bytes actually uploaded

The persistent upload path previously calculated its cache address from `vertex_base * stride`. The actual copy path uses `interleaved_range_info::get_required_range(vertex_base, vertex_count)`. These are different for constant attributes, divided attribute frequency and modulo frequency.

Consequently, two draws could share the old address and byte count while copying different source ranges. A cache hit then reused the wrong uploaded bytes. The first-eight-byte fingerprint also sampled the wrong guest address in these cases. Conversely, different draw IDs that used one identical underlying range could create redundant uploads.

The correction obtains the already computed block range and keys the cache with `range.first * stride`, exactly as the persistent copy loop does. It adds no full-buffer hash, no guest-memory copy and no per-vertex loop. The existing first-eight-byte weak validation remains unchanged. This does not resolve all possible same-range guest writes or concurrent writer coherence problems.

The native reproduction extracts the production range calculator, cached getter, complete weak vertex cache, complete persistent-cache allocation/lookup block, and actual persistent copy loop. The oracle is a fresh uncached execution of that copy loop. VM address translation, DMA and the destination heap are host adapters.

| Native result | Before | Candidate |
| --- | ---: | ---: |
| Cases | 1,656 | 1,656 |
| Wrong-range byte reuse | 300 | 0 |
| Ordinary array byte mismatches | 0 | 0 |
| Uploads for eight equivalent-range sequences | 32 | 8 |

This is a deterministic reduction of work in the constructed cases. It is not a measurement of game frames, iPhone upload counts or FPS.

## 2. Host sampler changes invalidate all affected shader inputs

The existing refresh path dirtied a shader only when the host descriptor's format class changed. The same format class can accompany different scale/bias, clip bounds, texture dimension, sample count or remaining software format conversion. `get_current_fragment_program()` consumes these values, but returns early while its dirty flags remain clear. `calculate_sample_clip_parameters()` is one real producer of changed coordinates without a guest sampler register update.

The correction snapshots just the relevant metadata before a host refresh. It invalidates the program when that metadata changes, including validity transitions. Active clip bounds are compared only when clipping is enabled; inactive bounds are not initialized by the descriptor and are deliberately not read. Image-handle replacement alone remains clean. Color-texture cyclicity and texel remapping without format features do not trigger extra invalidations.

There is also a fast framebuffer refresh that updates `is_cyclic_reference` without replacing the descriptor. A change in cyclic depth handling now invalidates the fragment state even when no texture upload is required. The unchanged sampler fast path performs no diagnostic record, snapshot or additional metadata scan. Its existing correctness check compares only the cyclic flag around the descriptor-expiry call.

The native reproduction extracts the complete old and new `load_texture_env()` methods, the real descriptor type, the clipping producer and the production uniform-copy statement. It supplies deterministic texture-upload and driver adapters, then compares cached shader-visible state with freshly resolved state. The final shader/pipeline and Vulkan resources are modeled; no GLSL, Metal or GPU execution is claimed.

| Native result | Before | Candidate |
| --- | ---: | ---: |
| Cases | 2,537 | 2,537 |
| Stale shader-visible states | 306 | 0 |
| Unchanged-state invalidations in tested cases | 0 | 0 |
| Uploads during 2,000 unchanged fast-path calls | 0 | 0 |

The tests cover coordinates, active clamps, dimension, MSAA, class, conversion, validity, depth cyclicity, ignored fields, guest-dirty state, hardware SNORM view changes and the cyclic fast update.

## 3. Bounded observations for the next iPhone run

The user subsequently authorized targeted instrumentation. `rpcs3::ios::renderer_causality::profile` exposes `reset(session)` and `take()` for the parent task's performance reporter. The renderer task does not modify `Performance.cpp`, `RSXThread.cpp` or app log routing.

Three event kinds are retained: `vertex_range`, `sampler_refresh`, and `sampler_cyclic_fast`. Eight slots per reporting window are divided into budgets of two, four and two, so frequent vertex events cannot consume all sampler observations. All admitted triggers are counted by kind and reason even after their event budget fills. A failed `try_lock` is counted separately as `contended`; its kind and reasons are unattributed. `dropped` includes both full-budget and contended records. Reason counters can overlap because one event can change several fields.

Events carry their captured session, monotonic microseconds, observed `int_flip_index`, draw count, fragment guest offset, vertex program start, sampler slot/stage and old/new guest resource references. Sampler events retain both compact metadata states. Vertex events retain the old and actual address, source/draw first vertex, draw count, stride, bytes and current cache-hit result.

The program positions are guest addresses/register positions, not content hashes. The frame identifier's scope is `rsx_flip_index`, not a unique guest-present serial. A vertex key divergence shows that the corrected path is exercised; it does not establish visible corruption in that draw. No legacy cache lookup is performed, so observation cannot alter cache state or double the guest-memory probes.

Only retained events read a clock and construct context. Producers never wait on the recorder mutex. Storage and counters are fixed; there are no per-event allocations, guest-memory reads, driver calls or direct log writes. The iOS producer does not run on unchanged sampler fast paths. Retained events and attributed counters clear together at reset; a contended rejection may straddle a reporting/session boundary only in the explicitly unattributed contention count.

The source-extracted renderer tests additionally assert that an event occurs exactly when the corrected relevant transition occurs, excluding already dirty guest-register changes. They verify frame/draw/program context and zero events on unchanged paths.

The independent production-header test completed 276 checks. A burst of 15,000 triggers retained eight events, called the context callback eight times, and counted 14,992 excess events. The retained distribution was 2/4/2. Allocation tracking found zero allocations in record/drain operations. A real competing thread verified nonblocking rejection and a failed nonblocking drain while the producer held the lock; the subsequent successful drain retained the original event and counted the rejection. Three session/reset scenarios passed.

## Validation and limits

### Subsequent compiler-wrapper portability update

After the six recorded runs were frozen, the three Python runners were changed only to accept `CXX` or `--compiler` through `shlex`, explicitly pass `-UNDEBUG`, use `HOST_MACOS_SDK` on Darwin and restrict `-no-pie` to Linux sanitizer runs. The five generated native programs were reconstructed without compilation and compared byte for byte with the frozen programs; all are identical. `renderer-portability.json` records both runner revisions and those program hashes. The existing six execution reports and `renderer-manifest.json` remain historical evidence for their original invocation envelope. The parent integration will produce new execution reports using the portable runners; no Apple execution is inferred from this portability change.

All three test scripts passed ordinary `g++ -std=c++20 -O2 -g -Wall -Wextra -Werror` execution and separate AddressSanitizer/UndefinedBehaviorSanitizer execution. Renderer extractions compile with `RPCS3_IOS` and include the actual diagnostic producer. Sanitized builds use `-fsanitize=address,undefined -fno-omit-frame-pointer -fno-sanitize-recover=all -no-pie`; leak detection is disabled, so no LeakSanitizer claim is made. Concurrency tests are functional; no ThreadSanitizer result is claimed.

Commands from this directory:

```sh
python3 test_vertex_upload_key.py --source ../device597-core-render --output vertex-plain
python3 test_vertex_upload_key.py --source ../device597-core-render --output vertex-asan --sanitizer
python3 test_sampler_shader_refresh.py --source ../device597-core-render --baseline ../device597-core-base --output sampler-plain
python3 test_sampler_shader_refresh.py --source ../device597-core-render --baseline ../device597-core-base --output sampler-asan --sanitizer
python3 test_renderer_causality.py --source ../device597-core-render --output causality-plain
python3 test_renderer_causality.py --source ../device597-core-render --output causality-asan --sanitizer
```

The six output directories retain generated C++, build/run logs and `result.json`. Successful source tests establish the reproduced CPU-side defects and bounded observation behavior. They do not prove that BO2 weapons/forearms, Assassin's Creed torches, the GOW3 startup wait or any iPhone FPS value is fixed. No new physical-device measurement exists for these changes.

## Continuity and next optimization decisions

The retained 597 AC and GOW3 windows contain zero shader compilation. These changes address stale shader inputs and exact vertex ranges rather than treating those warm stutters as new compilation. Detailed 597 BO2 windows have rotated away, and the supplied movies are historical 595 evidence; neither supports attributing a new visual result to this source lot.

The next authorized device run should determine whether the vertex divergence and sampler metadata transitions occur near the reported visual defects, and correlate them with the parent's slow-frame and wait observations. The limited vertex fingerprint still needs a sound writer/coherence design if same-range mutations are implicated. Replacing it with a blind full-buffer hash remains excluded: it adds size-dependent work per hit without establishing concurrent coherence. Broad batching, skipped barriers, forced label values and broad depth-query retention were not reintroduced. No new telemetry beyond the requested bounded causal observations was added.

The separate review of the parent's `IOSFrameTrace.h` found no blocking issue under its explicit lifecycle contract: one RSX producer and reset after the prior producer stops. Its producer-only time baseline advances on a rejected observation, shared records are mutex protected, wait additions use thread-local state, and fixed-capacity selection/sorting stays bounded. That review does not substitute for the parent's own tests and final integration gate.
