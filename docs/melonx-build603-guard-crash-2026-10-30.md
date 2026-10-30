# Hogwarts crash after Build603

The new device journal confirms that private Build603 still crashes. Its final
session identifies application0.0.8(603), Core1630bd0230c9 and original Core
SHA256 prefix423f2af029a5. The uploaded journal SHA256 is
`3ccb2d37698542fd8ff0f718a69ac0a1830cc027a6052f3741ace6de16473b09`.
The raw journal and personal content are not published in this repository.

Hogwarts Legacy1.0.5 starts at19:09:29.658UTC on30October. The1024MiB JIT
arena/probe succeeds, the GPU initializes by19:09:35.661 and Metal confirms
the first presentation at19:09:42.099. Presentation stops after approximately
37seconds of engine runtime while audio counters continue. At19:10:37.198,
the final record is an unhandled `InvalidMemoryRegionException` from
`NativePageTable.VirtualMemoryEvent` with relativeOffset0x40000003,
tableBytes0x40000000, size1 and writeTrue.

This offset belongs to the shared guard page used for unmapped guest pages.
It does not establish a page-table indexing overflow. The native signal bridge
always supplies size1, so that field is not the instruction's access width.
The log does not contain the faulting guest instruction or address. Sampled
memory remains around3034MiB with3621MiB process headroom; it does not prove
an OOM/Jetsam explanation. The experimental Unreal RomFS profile is enabled,
but the journal does not establish it as the cause. No user cache, mod,
firmware, save, pairing or setting is deleted or silently changed.

## Reproduced source defect

Build603 fixes literal memory lowering, including actual S/D/Q31 loads, but
the separate register-use analysis still treats vector register31 as integer
ZR. Its read/write masks omit V31 and the compiler consequently omits required
context loads/stores. The TBX instruction table also omits its incoming
destination read, losing bytes that the instruction must preserve for indices
outside its lookup table. Vector register lists also drop the low registers when
crossing V31 instead of wrapping modulo32. These defects can discard guest
values across translated blocks and host calls.

The final local vector fixture passes1664 opcode cases and125326 checks,
reproducing190 baseline mask failures and zero after correction. Its224
integer-register controls remain unchanged. The guard-context fixture passes
557 checks with explicit memory/context adapters. Both reports are retained
under `docs/evidence/melonx-guard604-local/`; neither executes ARM64 on a
physical iPhone.

The correction distinguishes real vector operands from integer operands in
mixed conversion/move and memory instructions. Integer zero-register and stack
pointer semantics remain intact. Tests use the pinned instruction decoder,
original/corrected register-mask functions, Block/DataFlow and the retained
compiler's real context-transfer methods and ARM64 assembler. They independently
decode emitted transfers and reproduce loss of a128-bit V31 value across two
translation units. This is executable compiler evidence, not physical game
execution or proof that this exact Hogwarts exception came from V31.

The fatal guard additionally records the existing thread's last guest dispatch,
when available, with no per-instruction or per-dispatch instrumentation. It
explicitly identifies this as neither the fault PC nor the access width. The
guard remains fatal; no invalid page is mapped, skipped or returned as zero.

## Unfinished lots completed in this candidate

P0-A had two remaining visibility holes. The 3D engine's syncpoint path did
not drain pending occlusion reports before publishing completion. The threaded
conditional-render command returned success without observing the backend's
answer, so Vulkan's CPU comparison fallback could be skipped. Front-end
reservation also remained held when the backend declined the operation.
The candidate drains the same gated report queue at both syncpoint paths and
returns the actual backend answer through the existing synchronous command
mechanism. The backend owns its reservation. Native Vulkan conditional-render
commands are not newly implemented; the existing CPU comparison is respected.

The targeted local harness runs 75 scenarios and 528 checks for each variant.
It reproduces 12 premature syncpoint publications, six false host-render
answers and four leaked reservations in the baseline, with zero in the
candidate. It compiles actual production report, conditional, command and
failure-propagation methods; native query readiness and command transport are
explicit doubles. Its 18 baseline source inputs and three candidate postimages
were independently authenticated. This is not a physical GPU or performance
measurement.

P0-B's bounded query batching, P1's explicit-allocation-failure JIT fallback,
and lot 5's depth-readback/thin-mip corrections are already implemented in the
retained baseline. They are not replaced or replayed as new work. The Unreal
experiment's reversible installation and consent already exist. The remaining
UI work supplies all 12 application languages and separates localized error
explanations from expandable technical details. Fresh targeted Flutter tests
are required before delivery. Whether the Switch game consumes the installed
CVar settings, and whether black textures recover, still require device evidence.

## Delivery scope

The application baseline is the last delivered Build 603, source
`808b64e16bb0f5112a2a7b5a07b400c19bb9cfbd`. At this stage the product source
delta contains the Unreal locale catalogue, profile dialogue, its playlist
entry point and the MeloNX plugin presentation call. Other product roots remain
exact. The affected MeloNX
Core is rebuilt from authenticated Core 1630 provenance with seven changed
production paths, 120 preparation inputs and 160 prepared members.

Delivered 603 contains RPCS3 378509e82. Run 41113741373 failed and produced
no Core. The later a4d0c9a5 attempt has completed successfully and its actual
artifact has been verified for the new IPA selection.
No retired application component is restored.

The immediate MeloNX baseline is the actual authenticated 1630bd02 archive.
Its historical receipts remain attributed to their original inputs; changed
source scopes are superseded by fresh targeted evidence. New Apple gates and
fresh NativeAOT simulator sessions validate the changed Core. The next private
IPA remains a candidate for the maintainer's physical Hogwarts test; a
successful build alone does not establish recovery.

## Launch-time investigation

The latest Build 603 selection-to-first-presentation interval is 12.441 seconds:
approximately 4.1 seconds for helper/JIT preparation, 0.65 seconds of host work,
0.628 seconds of GPU initialization and 6.44 seconds until guest presentation.
The GPU phase includes 375 cached shaders loaded in 0.231 seconds. A previous
Build 602 session took 72.276 seconds, dominated by 60.047 seconds of GPU
initialization, but another session of the same build initialized in 0.437
seconds. Therefore the log does not prove that Build 603 removed the intermittent
minute-long delay. Existing per-title shader/pipeline cache improvements are
retained. A further optimization requires a reproduced unnecessary cost and
must not delete user caches or weaken data checks.

Five recent launches spend 0.510–0.513 seconds between UIKit presentation and
`viewDidAppear`, where the engine starts. The candidate presents the game view
without animation, removing that mandatory transition from the launch path.
It still waits for view attachment and preserves the JIT, generation and window
guards. The existing real UIKit presentation/retry/cancellation fixture is
rerun against the current plugin; its historical registration-failure control
is not repeated. The observed half-second cost is a baseline measurement, not
a measured improvement from the new IPA.

## Actual Apple execution and scoped validation recovery

Core source `ada4058f5738465ac882934bb87224b637bcd0a1` compiled both NativeAOT
libraries in run 41118873328/job 124280125758. All three new Apple gates and
compiled-source binding passed. The run remains failed: its simulator fixture
requested stop after 30 seconds, before GPU initialization at about 35 seconds.
The native session drained cleanly, but the required guest SVC was not proven.
A subsequent optional stack-sampling timeout masked the primary test report.
The retained artifact 13007577275 is 87,638,481 bytes, SHA256
`93771c1ff47396f841534463ec6ea49ad3657d8a815e8c39c3d63e138c926395`.

A targeted runtime validation reuses those exact compiled bytes and successful
gate reports. Its fixture allows 90 seconds for the guest SVC, then separately
45 seconds for teardown, within a 300-second overall app bound. Both distinct
sessions, generation checks, guest SVC evidence and donated-backing release
remain mandatory. Primary outcomes are saved before optional diagnostics.
Thirty evidence-writer checks pass; the new actual simulator execution remains
a delivery prerequisite. No Core or unchanged regression gate is rebuilt.

Host source `3c47542cd3a732d60f11a97fe9e6baf42e483539`, run 41119381432/job
124281873638, passed 19 Flutter tests, the analyzer (zero errors or warnings,
six informational diagnostics) and 14 actual UIKit checks. Its run also remains
failed because the receipt parser rejected Flutter dependency output and valid
`test.startedProcess` sideband events. The original six-output archive is
authenticated: artifact 13008895566, 6,148 bytes, SHA256
`618cf64968a41b554ca691499a645590fca03d85972035064ab6246a59b31b30`.
The strict corrected parser recovers the actual successful evidence while
retaining the producer failure; no successful host fixture is replayed.

RPCS3 source `a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a` has now completed
run 41117115264 successfully and its actual Core, diagnostics and preflight
archives are authenticated. It replaces 378 only in the new IPA selection;
the delivered 603 receipt continues to identify its historical 378 payload.
