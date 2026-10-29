# MeloNX: SSBU startup — 29 October 2026

## Scope and observations

The recent SSBU v13.0.4 session in the supplied log takes **19.399 seconds from
selection to the first confirmed Metal presentation**. Loading 2,743 cached
shader programs occupies **11.411 seconds**, or 58.8% of that interval.
First presentation is the observable endpoint; the log does not identify when
the main menu or gameplay becomes ready.

The first 5,827 lines of the upload are an exact prefix from the previous log.
Only the new segment is used for this recent-session measurement. Neither
segment identifies the application build or engine commit, so it cannot be
attributed to engine 81. The older SSBU session takes 29.055 seconds, but its
different MoltenVK identity and cache-rebuild history prevent a controlled A/B
comparison. The Hogwarts sessions are not used as SSBU measurements.

| Recent startup window | Elapsed |
| --- | ---: |
| Selection and runtime preparation | 0.193 s |
| Runtime ready to core preflight | 2.066 s |
| Core preflight through firmware readiness | 0.175 s |
| Firmware ready through JIT handshake | 1.006 s |
| JIT complete through renderer setup | 0.759 s |
| Renderer setup and content load to shader-cache start | 0.411 s |
| Shader-cache loading | **11.411 s** |
| Cache completion to first Metal presentation | 3.379 s |

The cache-loading interval reports nominal thermal state and substantial
process memory headroom. Footprint grows from 1,237 to 2,383 MiB while reported
headroom remains 4,272–5,418 MiB. This particular wait is not evidence of
critical memory pressure. The 1,084 primitive-restart warning lines in that
interval are not a count of unique pipelines or successful recompilations.
The log does not isolate the cost of those messages.

Exact timestamps, segmentation, counters, source references and limitations:
[log correlation](evidence/melonx-startup-20261029/log-correlation.md) and
[sanitized log summary](evidence/melonx-startup-20261029/log-summary.json).

## Cached pipeline warm-up without changing synchronous rendering

The available source leaves an unnecessary dependency on the launch path when
the gameplay async-shader setting is false, as it is in both SSBU sessions.
The shader-cache loader validates cached programs using `CheckProgramLink`.
Previously, the Vulkan factory selected its legacy compilation path in this
configuration. That task included the initial graphics or compute pipeline,
so optional pipeline warm-up remained part of cache readiness. Guest CPU
execution waits for that readiness signal before starting.

The new guarded adapter selects the existing background compilation scheduler
for cached programs independently of the gameplay async-shader setting. Shader
modules must still finish and validate before a cached program is ready. The
initial pipeline is warmed opportunistically; it no longer determines cached
program link readiness. Existing worker pipeline caches, demand promotion and
speculative-work cancellation remain in use.

Draw skipping is explicitly allowed only when both `EnableAsyncCompile` and
`AllowAsyncCompileSkip` are true. With gameplay async shaders disabled, a draw
or compute dispatch still waits for its required executable pipeline. Live
programs with async compilation disabled retain their synchronous path.

The existing scheduler bounds the number of worker threads, not the length
of its pending queue. This change does not add workers, change persistent cache
formats or claim that every one of the 11.411 seconds can be removed. Module
validation and cache I/O still take time, and a pipeline first demanded during
gameplay may still require a blocking wait.

## Preserve fatal errors and thread shutdown

Detaching optional warm-up must not turn device loss, host/device allocation
failure or an unexpected exception into successful rendering. The Vulkan
renderer retains the first such background failure for that renderer instance
and checks it at loading, frame and pipeline boundaries. A failure is therefore
reported even if the cached program which encountered it is never drawn.
Recoverable warm-up errors retain the existing demand-compilation fallback.

Cleanup must also wait for other active demand tasks after the initial warm-up
task fails. Both collection wait/disposal paths now drain the remaining tasks
in `finally` before releasing the resources those tasks can use.

The complete GAL test exposed a silent catch in `CommandHelper.RunCommand`:
an exception could leave a default program result or partially consumed
reference slots while subsequent commands continued. That catch is removed.
The threaded renderer retains the original exception and wakes command, frame,
buffer, synchronization, resource and interruption waiters. It abandons the
partially consumed queue and returns the failure to the session owner.
The owner still stops the guest before joining and releasing the renderer.

The disk-cache loader now completes its translation queue and joins every
successfully started worker in `finally`, including an early native error or
a partially successful thread-start loop. Its existing recoverable cache
errors, translation policy, rebuild and validation behavior are preserved.

Review also followed startup failure through the guest's GPU-ready barrier.
That barrier previously signalled only after successful cache initialization.
An error could therefore strand guest threads before CPU execution and prevent
guest termination. The separate startup-failure adapter makes this initialization
outcome terminal and permits kernel thread exit without executing guest code.
Its cancellation and active-cache lifetime are covered by the final targeted
startup test.

## One fresh firmware scan per launch

Launch preflight called `ContentManager.LoadEntries` immediately before
`GetCurrentFirmwareVersion`, which itself starts with `LoadEntries`. The
explicit first call is removed. The authoritative version reader still scans
the current files, so importing, replacing or removing firmware remains visible
on the next launch. No firmware version is cached by this change.

The targeted test executes the production preflight, directory scan, version
reader and parser with the pinned LibHac local filesystem. It substitutes NCA
decryption and surrounding emulator services, without using personal firmware
or key material. Both variants pass 62 checks across 15 scenarios and produce
the same semantic trace; a fresh launch performs two scans before the change
and one afterward. Invalid or missing data preserves the same errors.
The existing native preflight/key-schema/journal gate also passes 14 checks.

This removes a duplicate operation within the roughly 0.175-second preflight
window. It is a smaller improvement than the shader-cache dependency; there
is no measured device-time saving for this edit yet.

## Validation and delivery

The targeted shader test passes with 5,933 control assertions and 3,426 candidate
assertions. Its 48 combinations cover cached/live programs, graphics/compute,
initial pipeline state, async/skip permissions and binary/retranslated sources.
Thirteen candidate fatal cases include failures arriving during a graphics
wait. Dedicated cases cover demand promotion, recoverable errors, invalid
modules, speculative cancellation, fresh renderer state and both cleanup paths
with another active demand task after the initial task faults.

In the controlled 2,743-program fixture, the candidate validates all modules
and leaves the cache-loader barrier while the speculative pipeline worker is
deliberately held. The control waits for all 2,743 initial pipelines. The
candidate's zero pipeline completions before barrier exit is an imposed test
condition proving independence; it is not a prediction that real launches
perform zero pipeline work. Actual draws remain synchronous in that setting.

The harness compiles the real factories, constructors, readiness/demand/disposal
methods, complete background scheduler and complete pipeline hash table. Native
Vulkan calls, pipeline-state packing, descriptor layout construction and GLSL
compilation are doubles. These boundaries are explicit in the source-bound
[shader receipt](evidence/melonx-startup-20261029/cached-shader-startup-checks.json).
The separate [firmware receipt](evidence/melonx-startup-20261029/launch-firmware-checks.json)
records its real filesystem/version parsing and its substituted NCA boundary.

The [threaded renderer test](evidence/melonx-startup-20261029/threaded-renderer-failures-checks.json)
compiles 200 real engine files, including all 188 GAL files, and the actual
embedded window lifetime. The control passes 20 checks and demonstrates the
silently swallowed failures; the candidate passes 149 checks. Cases include
program creation/linking, `PreFrame`, thirteen external waiters, a full
9,999-command queue, producer/interruption exceptions, paused GPU shutdown and
guest-stop failure quarantine. Its backend is inert; no GPU timing is measured.

The [loader lifetime test](evidence/melonx-startup-20261029/shader-loader-lifetime-checks.json)
executes the complete production loader and ten supporting source files with
real threads and queues. Both variants pass 214 checks; a separate partial-start
candidate passes 36 more. In three early-error scenarios, the control returns
with eight translators still active; the candidate returns with none. The
original exception and stack survive. Success, four recoverable cache cases,
cancellation and failures occurring after the drain preserve their outcomes.
Only the partial-start executable substitutes the thread-start boundary to
inject a failed start; its successful starts and joins still use real threads.
Storage, translation, renderer and cache containers are controlled boundaries.

The [GPU startup test](evidence/melonx-startup-20261029/gpu-startup-failure-checks.json)
passes 54 control and 127 candidate assertions. The control reproduces three
stranded startup waits. The candidate covers ten cases, including four
cancellation cases, with six guest threads per case. It executes the complete
`ArmProcessContext`, real kernel thread entry/exit/termination methods, the
process termination loop and the embedded session owner. It holds an active
initializer after cancellation and proves that guest exit, unregister and
disposal do not occur before that initializer unwinds. Failed or cancelled
startup never enters the CPU; late waiters, terminal-state stability and
flush/drain are covered. CPU execution, scheduling services, shader loading,
the renderer and the frame body are explicit controlled boundaries.

The final complete managed library build passes with zero errors and 21
existing warnings in 31.96 seconds. Fresh preparation changes exactly fifteen
of 4,095 source/project files relative to engine 81; the other 4,080 remain
identical. After the first integration build, only the five additional
failure-path source files were copied into the existing compilation workspace.
All five targeted host gates pass with their final input hashes and integrated
postimages verified. Independent review accepts the final readiness, exception
transport and worker-lifetime changes. The Apple build follows publication of
this exact source candidate.

- [Fifteen-file source delta](evidence/melonx-startup-20261029/source-delta.json)
- [74 preparation input hashes](evidence/melonx-startup-20261029/embedded-inputs.json)
- [Managed integration and targeted-check receipt](evidence/melonx-startup-20261029/integration.json)

The candidate extends the verified engine 81 source and preserves concurrent
RPCS3 work. Upstream remains `13700519f3abc4e6d7ed8a065b118b2cc59bcd67`, SDK
10.0.100 and the existing LibHac pin. The already delivered private IPA 593 is
the application baseline. This work prepares an engine for the next authorized
IPA; it does not replace the contents of an installed application.

No new SSBU launch time, menu readiness, physical-device FPS or whole-process
memory gain is claimed. Controlled tests establish which work blocks readiness
and whether required rendering/error/cleanup behavior is preserved. The actual
selection-to-first-presentation improvement still needs a run of the resulting
engine on the device with comparable cache state.
