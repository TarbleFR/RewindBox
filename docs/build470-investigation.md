# Build 470 investigation — persistent Nestopia skin terminations

Base: `69f2194acb415a4d68f7898428d42262ab2149da` (private Build 469).
Branch: `Claude`. No public release requested. Physical iPhone unavailable.

The maintainer reports the crash still occurs in 469. The two available
application journals stop at 0.094 s and 0.503 s. They identify Nestopia
2.0.0 / 135dfa6, NESThumbstick 2cb17f0364a285dd, landscape edgeToEdge and
software video; neither identifies a native exception, GPU fault or system
kill. They predate the delivery commit and contain no build stamp. They
must not be presented as newly captured Build 469 crash evidence.

## Source findings and limits

1. `invalidateSession` revoked current work but was not terminal. A subsequent
   `showRepresentation` created another image generation. The game view also
   accepted layout/appearance after `stopInputPolling`, recreating its display
   link. The regression probe exercises the unchanged 469 method bodies, then
   the corrected bodies. This is a concrete lifetime defect; its relationship
   to the reported startup termination remains unconfirmed.
2. `startFromViewController` had no per-object one-shot guard and its deferred
   UIKit presentation completion could start the emulation thread after an
   early stop. A session is now single-use; stopping revokes presentation and
   input/layout work immediately. Validation callbacks refuse a closing session.
3. The old probe's 150-second watchdog captured every session strongly, hiding
   deallocation during repeated launches. The observer now holds it weakly;
   selected scenarios require deallocation before the next launch. This is a
   test-harness correction, not a product crash diagnosis.

## Actual execution and ownership

| Step | Executor / owner | Deferred work and cancellation |
| --- | --- | --- |
| launch, configuration, preferences | main; plugin owns session | single-use guard; closing flag revokes presentation completion |
| choose / parse skin and representation | main; session skin cache | representation keyed by identifier/device/display/orientation |
| validate PNG/PDF paths | serial skin queue; immutable filenames | main completion checks session, cache identity and closing |
| create controller, overlay, CAMetalLayer, presenter | main; session/controller own these | terminal stop drops callbacks and layout source |
| layout, thumbstick coordinates, safe areas | main; controller/layout source | coalesced main callbacks cannot revive stopped view |
| decode images / pressure frames | serial skin queue; image/progress generation | cancellation before/after decode; publication on main with generation and identity checks |
| core load, initial black frame, audio start | emulation NSThread; session owns host/presenter/audio | explicit before/after breadcrumbs; run-loop condition handles stop |
| software frames | synchronous core callback on emulation thread | data copied before callback returns; upload slots wait for their GPU readers |
| Metal submit / complete | encode on emulation thread; completion on Metal queue | command buffer retains resources; slot group + in-flight semaphore released on completion |
| touch and physical-controller polling | UIKit main/display link; input snapshot under lock | terminal stop invalidates display link and releases touches |
| cheats / achievements | existing services, unchanged | added scheduling breadcrumbs only; no activation/format behaviour changed |
| close / relaunch | request on main, core teardown on emulation thread, dismiss on main | revoke UI work first; existing core/context teardown order preserved |

## Video and original skin audit

The upstream original archive contains six PDFs and info.json, including the
separate landscape thumbstick PDF. The landscape representation is translucent.
The source bounds decoded dimensions; each PDF render owns its own document.
The real Nestopia option `nestopia_blargg_ntsc_filter=composite` produces a
filtered frame; 602×224 is not evidence of a bad resolution. Record actual
pitch and pixel format before upload. No core, rendering quality, catalogue,
touch preference or valid skin is disabled in this candidate.

The Metal upload ring already waits for readers of each slot. Command buffers
retain their textures; layout snapshots are locked independently of drawable
acquisition. No new GPU-fault cause or buffer-overrun reproduction is claimed.

## Diagnostics and preservation

Every journal event carries session UUID, native thread ID and main/thread
name. Record OS, physical RAM, object addresses, Metal device, skin generation,
decode start/end/error/cancellation, first software frame dimensions/stride/
format, drawable acquisition and GPU completion/error, audio start and service
scheduling. System notifications record background/foreground, memory warning,
thermal state and measured footprint.
Loaded app/core image UUIDs and load addresses are recorded for matching a
fatal PC against the exact delivered Mach-O images; footprint is sampled at
session creation and successful skin activation.

`native-termination.log` captures fatal signals only when no handler already
owns them. The handler uses fixed stack storage and a preopened descriptor,
without Objective-C, allocation, locks or unwinding. It preserves fatal signal
termination. The next process keeps an actual fault in
`previous-native-termination.log`; normal launches do not overwrite that fault.
It cannot capture SIGKILL/jetsam/watchdog or promise a complete stack trace.
Absence of a fatal line never proves a system kill.

Never ask the maintainer for .ips, Jetsam or watchdog files; they are not a
prerequisite for further diagnosis or delivery. Use application evidence.

## Simulator versus hardware

The simulator runs the actual pinned Nestopia binary retargeted to the
simulator, production UIKit/session/Metal code and original skin. It uses the
host GPU, host memory budget and scheduling, simulator audio and synthetic
touches. It does not reproduce iPhone GPU drivers, memory enforcement,
ProMotion, thermal conditions, signing/provisioning or suspension timing.
Success is not physical-device validation.

## Planned validation (results must be filled from CI)

- Negative 469 renderer/view lifetime reproduction; candidate terminal-state
  and weak deallocation assertions.
- 100 Nestopia sessions: 82 original-skin, 10 native-control, 8 Ignited;
  two original test programs and ZIP packaging; 10 s / 30 s final sessions.
- Five live sequences, each with four skin switches, requested and observed
  portrait/landscape rotations, 32 MiB touched memory and a clearly synthetic
  memory-warning notification/cache eviction.
- Native signal child processes, journal concurrent writes/rotation,
  existing native frontend/input/pressure checks, iPhone compile/link,
  installed-skin preservation, catalogue, cheats and other-core suites.
- 12 additional sessions with AddressSanitizer instrumenting bridge/probe CPU
  memory operations (the prebuilt core and GPU are not instrumented); concurrent
  journal writers also run under ThreadSanitizer on macOS. These are additional
  diagnostic tests, never presented as a physical-device run.
- No commercial 10-Yard Fight ROM or physical iPhone is available. No 30-launch
  physical run or long-duration thermal result is claimed.

Compilation and delivery identity are pending actual successful checks.
