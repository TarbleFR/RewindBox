# Renderer continuation regression checks

These runners extract production code from an explicitly supplied RPCS3 tree.
They do not require a workspace-specific location, network access, an iPhone or a
Vulkan driver. Their fixtures contain only unchanged upstream declarations and
the existing Vulkan error handler. `fixtures/provenance.json` records the pinned
XITRIX/rpcs3 commit, Git blob SHA-1, original SHA-256 and fixture SHA-256. The
fixtures differ from retrieved upstream bytes only in line endings and final
newlines; their exact contents as used by the recorded harnesses are retained.

## Generate and verify without recompilation

`--generate-only` writes the extracted C++ harness and a `.generated.json` file,
then exits before invoking a compiler or executable. Compare `harness_sha256`
and production fragment hashes against the recorded JSON. A generated manifest
is not a new test execution.

```sh
python3 test_pipeline_reload.py --core /path/to/candidate-core --label candidate --output-dir /path/to/output --generate-only
python3 test_gpu_wait_retirement.py --core /path/to/candidate-core --label wait-candidate --output-dir /path/to/output --generate-only
```

For a partial candidate tree, supply unchanged caller code separately:

```sh
python3 test_pipeline_reload.py --core /path/to/candidate-core --draw-core /path/to/full-core --label candidate --output-dir /path/to/output --generate-only
python3 test_gpu_wait_retirement.py --core /path/to/candidate-core --caller-core /path/to/full-core --label wait-candidate --output-dir /path/to/output --generate-only
```

`--flags-header`, `--shared-source` and `--shared-header` can override the bundled
fixtures when checking a newer upstream base. Existing recorded results then
apply only if the relevant source and harness hashes still match.

`evidence/portability-check.json` records successful generation-only comparisons
after adapting these runners. No native compilation or execution was performed
for the portability adaptation.

## Reproduce native checks when source changes warrant it

Omit `--generate-only`. Supply `--expect-failures` for the unmodified baseline and
`--sanitize` to enable AddressSanitizer and UndefinedBehaviorSanitizer. A C++20
compiler named `g++` is required. The existing runs used `-O2 -Wall -Wextra
-Werror -DRPCS3_IOS`; sanitizer runs add `-fsanitize=address,undefined
-fno-omit-frame-pointer`. Leak detection is disabled for these harnesses.

## Recorded executions

| Evidence | Execution | Verified result |
| --- | --- | --- |
| `baseline.json` | Native, without sanitizers | 112 stale pipeline mismatches / 4,608 cases; 13,333 mismatches / 20,000 draw sequence; late texture invalidation failed |
| `candidate.json` | Native, without sanitizers | Zero mismatches in the same cases and draw sequence; late texture invalidation passed |
| `candidate-asan.json` | Native, ASan + UBSan | Same candidate results; no sanitizer error |
| `wait-baseline.json` | Native, without sanitizers | All 36 failure scenarios violated retirement invariants; all 12 success checks passed |
| `wait-candidate-asan.json` | Native, ASan + UBSan | All 36 failure scenarios and 12 success checks passed; no false completion, fence reset, heap restoration, command-buffer reset or frame cleanup on failure |
| `dma-wait-comparison.json` | One comparative native execution, ASan + UBSan | Each version covers 32 fence failure cases, 32 event failure cases and 20 success cases; candidate has no pending-buffer reset, pending-fence destruction or readback after a failed wait |

There is no separately executed, unsanitized wait-candidate result. Its recorded
file was named `wait-candidate.json` when executed; the portable evidence copy is
named `wait-candidate-asan.json` to make the sanitizer distinction explicit. Its
recorded command retains the actual original invocation.

### Shader pipeline scope

The harness extracts the complete `VKGSRender::load_program()` function, the
complete `begin()` function and the host texture-format invalidation branch
from `load_texture_env()`. Shader compilation, lookup and uploads use deterministic
stubs. A real reachable order is exercised: `begin()` retains the old native
pipeline because only fixed-function state is dirty; `load_texture_env()` then
discovers a new host texture format and dirties the fragment program. Equal
fixed-function properties must not bypass the shader refresh. Both old and new
implementations retain zero additional warm-cache lookups in the tested clean
cases.

### GPU retirement scope

The harness extracts the complete `command_buffer_chunk` type,
`command_buffer::reset()`, `frame_context_cleanup()`, `wait_all()` and the pinned
upstream `die_with_error()` function. Driver results, handles, resource side
effects and locks are deterministic shims. Error injection covers `VK_TIMEOUT`,
device loss, host OOM and device OOM, including both mandatory reuse callers,
repeat waits and each wait-all slot. Successful blocking waits, already-finished
work, fence polling and a deterministic lock-upgrade interleaving are checked.
The shader test and the wait test do not execute Vulkan or an emulated game.

The wait fix preserves the existing timeout and invokes the existing Vulkan
exception path before publishing completion. It prevents unsafe reuse after a
failed wait; it does not repair the GPU producer responsible for a stall.

## Primary source comparisons

- Shader guard corroboration in RPCS3's newer state architecture:
  https://github.com/RPCS3/rpcs3/commit/b4d4e2bd7d8d0bdc37cfdf1b5e7d06867704abec
- Error handling before command retirement in RPCS3's newer recovery architecture:
  https://github.com/RPCS3/rpcs3/commit/3e4df51852ae1e4ec9ea2c8529e205d080ccf67b
- Pinned error handler used by this fork:
  https://github.com/XITRIX/rpcs3/blob/22f1152783cef1f7e04af7b1c895173e28fd5b03/rpcs3/Emu/RSX/VK/vkutils/shared.cpp
- Vulkan pending-command-buffer reset requirement:
  https://docs.vulkan.org/refpages/latest/refpages/source/vkResetCommandBuffer.html
- Vulkan fence-wait timeout semantics:
  https://docs.vulkan.org/refpages/latest/refpages/source/vkWaitForFences.html

No FPS gain, iOS memory reduction or game-specific visual correction is measured
by these host regression harnesses.

## DMA fence ownership and event wait continuation

`test_dma_wait_ownership.py` compares baseline and candidate code in a single
sanitized executable. Its core trees and output location are explicit arguments:

```sh
python3 test_dma_wait_ownership.py --baseline /path/to/baseline-core --candidate /path/to/candidate-core --support-core /path/to/full-core --output-dir /path/to/output --generate-only
```

Omitting `--generate-only` compiles and executes the comparison once with ASan
and UBSan. The runner extracts both complete DMA functions, the production
command-buffer constructor setup, destructor, submit, end, begin and reset
methods, the command-buffer chunk, the fence constructor/destructor, the outer
`flush_all()` method and the existing error handler. Driver waits, submission,
the asynchronous scheduler, actual GPU work and guest-memory conversion are
controlled shims. The `flush_all()` transfer delegate is also a shim; the outer
production lock and exception unwinding execute unchanged.

The fence correction uses the fence already owned by the command buffer.
`submit()` installs that fence in the submission and marks the buffer pending.
After a successful timed wait, the production `begin()` method observes the
signaled fence, resets it and the command buffer, then begins recording. The
explicit earlier reset and local fence are removed. On failure, the exception
leaves the owned fence alive until normal renderer teardown. A simple exception
guard around the former local fence was rejected because stack unwinding would
destroy a fence that could still be referenced by a pending submission.

The actual call graph confines this branch to the primary RSX command buffers;
the secondary CPU fault buffers use the unchanged auxiliary branch. Production
setup creates the owned fence before any buffer is begun. The primary polling
and retirement callers execute on the RSX thread, and the fence-wait helper does
not call back into renderer service code. The code adds no EID, retirement or
heap snapshot publication. Renderer teardown already waits for the device before
destroying the command-buffer chains; this test does not emulate device recovery.

The comparison observed 24 pending-buffer resets and 24 pending-fence
destructions in the baseline failure matrix, with neither occurring in the
candidate. The eight baseline event-timeout cases proceeded to readback; all
eight are stopped by the candidate. Other event-driver errors already entered
the error handler in the old wait helper and continue to do so. Device loss is
treated as releasing pending Vulkan work for lifetime checking, so it is not
counted as a pending-fence destruction in this matrix.

All 20 success checks per version passed. They cover primary readback with and
without an open query, absent/idle/host-mode/GPU-mode asynchronous scheduling,
the unchanged auxiliary submission path, and event readback combinations for
tiling, swizzling and framebuffer storage. Query flags and sentinel EID/snapshot
state remain correct. The candidate performs one fence-state recheck after a
successful timed wait; it never enters a new pending-fence wait in the tested
success path. The eight primary success cases create and destroy eight temporary
fences in the baseline, versus zero temporary fences in the candidate. This is
an operation-count result, not a measured FPS or frame-time gain.
