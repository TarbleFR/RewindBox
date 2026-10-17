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

## Targeted retained-owner defect identified

`LibretroCheatMenu.m` declared both page pointers on one line:
`__weak LibretroMenuPage *_visiblePage, *_rootPage;`. ARC applies the written
ownership qualifier to the first pointer; the second is implicitly strong.
Both LLVM Clang and the actual Apple iPhone compiler prove `_visiblePage` weak
and `_rootPage` strong in the unchanged 469 declaration. The root page's
sections contain action blocks that retain the menu, closing a strong cycle.

The corrected source, `6b1aaba9dd8b6e7cdb50de5730fbd6f51dd0a9eb`, changes only
that declaration into two separate explicitly weak declarations. The catalogue,
cheat matching, activation, preferences and visible menu actions are unchanged.
The existing session owns the menu while it is in use; navigation owns its page.

The new native measurements establish the retained objects directly: after each
of 20 normal session closures, session/controller/renderer/presenter/audio/core/
input objects are gone, while live cheat menus and catalogues increase from 1
to 20. The final heap also contains exactly 20 root pages, 160 rows and 60
sections. About 1.27 million allocation nodes account for 89 MiB, dominated by
catalogue strings and dictionaries. Adding autorelease pools did not remove it.

This declaration defect explains the measured retained ownership and growth.
Its relationship to the reported iPhone terminations is still unconfirmed.
The targeted final regression passed: all 20 ownership records show zero
retained tracked application objects. The 99 NES cheat/menu checks and four
independent-process persistence checks also pass. Actual artifact 12117547161
(run 39077361583, source 2ca52ba2) was downloaded and its verdict, Apple
ownership proof and SHA-256 independently checked. Archive SHA-256:
`1a94c66490bb3779a9646cabca934da047cd84f219bcae230d84688a180e1fef`.
The first and twentieth post-close footprints are 43.94 and 50.26 MiB; malloc
bytes in use are 4.87 and 5.57 MiB. The old instrumented baseline ended at
131.10 MiB footprint / 89.06 MiB malloc bytes, with 20 retained menus/catalogues.
These are Simulator measurements, not iPhone memory-budget estimates.
No unaffected passing suite is scheduled again.

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


The exact six-code 10-Yard Fight resource was also checked against upstream
Git blob `6983758d4944dd21648f9bd07037d2b831d4a76f`, at catalogue revision
`12c21cf79f1e20eff6ac68b80875816c717d0a7a`. Its Game Genie code and five
short address/value programs are disabled in the upstream file. The catalogue
also explicitly publishes downloaded entries as disabled. This does not reveal
the maintainer's previously saved selections. Resource parsing runs on the
catalogue's serial queue and publishes on main; applying selected codes is
queued to the emulation thread. The existing core boundary refuses unloaded
content, non-ASCII/NUL-containing or oversized programs. No new cheat behaviour
is introduced and the successful `parsed=6` line is not evidence of a fault.

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
termination on the originating thread. The owning journal removes only its own
handlers when the session ends; another emulator cannot inherit a Libretro
session's fault identity. A pre-existing or subsequently registered reporter is
preserved. The next process keeps an actual fault in
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

## Validation design and evidence

- Negative 469 renderer/view lifetime reproduction; candidate terminal-state
  and weak deallocation assertions.
- 100 Nestopia sessions: 82 original-skin, 10 native-control, 8 Ignited;
  two original test programs and ZIP packaging; 10 s / 30 s final sessions.
- Five live sequences, each with four skin switches, requested and observed
  portrait/landscape rotations, 32 MiB touched memory and a clearly synthetic
  memory-warning notification/cache eviction.
- Ten independent process restarts with original NESThumbstick, retaining the
  installed application and disk cache. Each must record its process/session
  identity, first submitted/completed video frame, original landscape edgeToEdge
  activation, normal close and session deallocation. The previous 37-session
  single-process result did not cover this startup boundary.
- Native signal child processes, journal concurrent writes/rotation,
  existing native frontend/input/pressure checks, iPhone compile/link,
  installed-skin preservation, catalogue, cheats and other-core suites.
- 12 additional sessions with AddressSanitizer instrumenting bridge/probe CPU
  memory operations (the prebuilt core and GPU are not instrumented); concurrent
  journal writers also run under ThreadSanitizer on macOS. These are additional
  diagnostic tests, never presented as a physical-device run.
- No commercial 10-Yard Fight ROM or physical iPhone is available. No 30-launch
  physical run or long-duration thermal result is claimed.

### Verified results

The common runtime and full test source are frozen at
`2e877872a919c119fb3d10f47699218cc1a34e96`. The sole subsequent product change
is the explicitly weak `_rootPage` declaration in
`6b1aaba9dd8b6e7cdb50de5730fbd6f51dd0a9eb`. Later changes add only CI recipes and external diagnostics, including
process sampling and temporary memory-isolation variants; product/test bytes
remain identical. The delivery gate closes all runtime, data,
dependencies and test sources against each witness, and pins each changed
recipe separately. Only the exact new Menu bytes use their independent targeted
witness; the previous passes cover the unchanged inputs. A changed commit label
is not substituted for byte identity.

| Evidence | Run / job | Actual result |
| --- | --- | --- |
| Dart, analysis, localization | 39071406958 / 117509624834 | 578 + 245 + 4 tests; 12 locales / 917 keys; two existing analyzer infos, no analyzer error |
| Native frontend, shaders, iPhone compilation and codec | 39071406958 / 117509624886 | 19 frontend files, 6,025 touch checks; 74 sources compile and link for iPhone; current codec and original 453 negative control pass |
| Skin sessions, iPhone + iPad Simulator | 39071406958 / 117509624693 | 27 scenarios / 2,840 checks; all pass |
| Repeat skin sessions and pressure pixels | 39071419764 / 117509663129 and 117509662998 | 27 / 2,840 repeated checks pass; 1,133 pressure pixel checks pass |
| Catalogue transports and original artwork composition | 39071418361 / 117509658452 | 109 Dart tests; 39 associations / 78 native checks pass |
| AddressSanitizer + journal ThreadSanitizer | 39071406998 / 117509622756 | 12 sessions, 38 lifetime/switch/rotation checks pass; no captured non-cancelled decode or GPU error; four cancelled decode breadcrumbs |
| Installed-skin upgrade, fallback and persistence | 39072237930 / 117512063394 | 53 + 10 checks pass; original 463 resource rejection reproduced; recipe-only witness ed45df2e |
| General sessions / error handling | 39071406964 / 117510105544 | All 13 scenarios pass |
| Other software cores, lot 2 | 39071406964 / 117510105857 | 8 scenarios pass: FreeChaF, FreeIntv, O2EM and PC-FX, twice each |
| Official HTTPS shader menus and GPU output | 39071406964 / 117510105765 | All 6 software, Vulkan and DeSmuME scenarios pass |
| Original NESThumbstick 100 + ten process starts | 39071406998 / 117509622555 | 100 normal + 10 independent process starts pass; actual downloaded normal/baseline/sanitizer verdicts verified |
| Targeted menu ownership and preserved cheat functions | 39077361583 / 117527185352 | PASS: iPhone source/ARC proof, 20 ownership sessions with zero retained tracked owners, 99 cheat/menu checks and 4 second-process checks |
| Other software cores, lot 1 | 39071406964 / 117510105939 | 29 scenarios pass |

The initial installed-skin attempt (39071406951) timed out without its first
application progress event. The unchanged product and test sources passed in
the diagnostic retry above, despite another silence exceeding 120 seconds.
No process stack sample was produced by that retry; the cause of the initial
silence is therefore not established. This must not be reported as a diagnosed
application crash or a diagnosed simulator fault.

The initial cheat run (39071416870) completed all five first-process scenarios:
128 Ignited checks, 99 NES cheat checks, 10 preview checks, 4 DS and 4 SNES cheat
checks. The second process timed out without a new progress event. The whole
run failed; its functional checks are not substituted for the pending complete
process-persistence test.

The first broad run could not compile its two historical controls because
the modern probe requires a controller forward declaration. After adding only
that declaration to the temporary old headers, scoped run 39075544105 succeeds:
117521825151 (before-fix) and 117521825436 (before-reservation). No legacy
implementation body was changed; its five unrelated jobs were intentionally skipped. The synthetic shader suite completes its six sessions but fails
its first `simple.slangp` menu download with `MENU_DOWNLOAD_MISSING` after the
harness's existing 400 ms navigation wait. All other cases must not be used to
claim this suite passed. This is separate from the six successful real HTTPS
shader cases, and is not a reproduced Nestopia termination.

The original full Dart/source-contract execution is 38962439914 / 117180593798,
source fc1ef43a. Its checks job passed before unrelated jobs were cancelled;
Build 469 reused that exact cached result. The original `dart-validation.json`
in delivered 469 records this exact tested SHA. All current Dart files, fixtures,
assets and dependencies remain identical. The engine 2e877872 provides the fresh
analysis/localization checks for the added native diagnostics. The delivery
reuses these results and runs only its two changed guard tests.

NeoSwap native validation is also reused from delivered 469: its successful
identity closes all 107 native inputs byte for byte and the exact Xcode/iPhone
SDK. The 34 precompiled libretro cores and other unchanged native runtimes are
reused. The affected bridge/application must still be compiled, packaged and
signed to create a testable IPA.

The targeted runtime check and final private IPA delivery have passed.
Final file identity and the Windows copy are recorded below.

## Retained diagnostic evidence before the targeted fix

The completed 100-session process grows from 18.48 MiB at the first session
creation to 493.84 MiB at the hundredth (skin-active maximum 504.95 MiB).
Growth continues through native-control sessions. The full result document is
only 1.61 MB, so the report storage alone cannot explain this observation.
No uncancelled decode or Metal completion error was captured. The later owner/heap and ARC evidence above identifies the retained Menu/root
page cycle. This is not a diagnosed iPhone termination mechanism or a stability
approval.


Memory A/B run 39075535345 executes 20 complete Nestopia sessions per variant
(ten original NESThumbstick, ten native controls). All three CI jobs fail their
extra instrumentation assertion because the initial wrapper did not intercept
the compiler's direct subprocess call; this was repaired in b5fcc3ce and the
next run proves the instrumented translation unit was compiled exactly once.
The actual variant source patches, normal session journals and external VM/leaks
captures are still present and usable:

| Temporary variant (never a shipping fix) | Final footprint | Heap allocation nodes / bytes | Interpretation |
| --- | --- | --- | --- |
| Unchanged production baseline | 133.4 MiB | 1,273,143 / 91,064 KiB | Growth reproduced |
| Per-work-item pools on both catalogue/preference queues | 133.8 MiB | 1,272,874 / 91,012 KiB | Does not remove growth; do not ship as a claimed fix |
| Omit only the eager cheatsPage preparation call | 46.2 MiB | 37,450 / 5,441 KiB | Isolates growth to the catalogue-preparation path; not permission to remove that feature |

The three external `leaks` captures report zero unreachable leaked bytes.
This does not prove that reachable objects have the correct lifetime. The
owner/heap comparison is required before identifying retained ownership. No
physical termination mechanism is inferred from simulator footprint alone.


The third broad cheat attempt, 39075535269, did not complete either process
within its budget. Its console shows late startup and partial first-process
execution; no complete result was copied. This remains a failed test, not a
product-crash diagnosis. It is superseded for the final changed code by the
focused ownership/99-check/four-check witness above, without repeating the
unaffected overlay, SNES, DS or catalogue suites.


## Modified files

Shipping native files, all under `packages/libretro_internal_bridge/ios/Classes/`:

- `LibretroCheatMenu.m`: split the weak page declarations; no cheat behaviour/data changes.
- `LibretroSkinRenderer.h/.m`: make invalidation terminal and log decode generations.
- `LibretroGameViewController.m`: terminal input/layout teardown.
- `LibretroSession.m`: single-use launch, closing callbacks, correlated stages.
- `LibretroMetalPresenter.h/.m`: correlated first-frame/draw/GPU diagnostics.
- `LibretroSessionJournal.h/.m` and new `LibretroCrashCapture.h`: session/thread/native diagnostics and preservation.

Regression/provenance files include `test/libretro_simulator/probe.m`,
`test/libretro_simulator/skin_lifetime_probe.h`,
`test/libretro_nestopia_skin_stability_probe.py`,
`test/libretro_simulator_probe.py`, `test/libretro_crash_capture_test.c/.py`,
`.github/diagnostics/libretro_memory_probe.py`,
`.github/diagnostics/libretro_simulator_device.py`,
`build-utils/verify_delivery_reuse.py`, `test/delivery_pipeline_test.py`,
and the associated CI recipes. Delivery recipe changes reuse passed Dart,
source contracts, native NeoSwap checks and unchanged precompiled runtimes.
The public 470 recipient contains no private key. `AGENTS.md` persists both
maintainer rules: never request system crash reports and never repeat passing
validations with unchanged inputs.


## Final private Build 470 delivery — 18 October 2026

- Built commit: `a43a570412ed2bf382d2df3acc0a9ce9ca88c27c`, branch `Claude`.
- Actions run `39078262825`: checks, native and Release iPhone build pass; optional warm benchmark skipped.
- Actual IPA: `NeoStation-Build470-a43a5704.ipa`, **218,634,697 bytes**, version **0.0.7 (470)** in the app and all five extensions.
- IPA SHA-256: `c240faf5ec816243fd9b595e7fae1c07118e8e71a5db3f1abb394e9242bceb60`.
- Encrypted artifact `12118192232`: 220,259,229 bytes, archive SHA-256 `77262a977f7d19a67a61bbb2d6aa9569dcf08ca6b929a527c428039ab97ee3b9`.
- Independently decrypted with the authorized 470 recipient; actual ZIP structure/CRC, source stamps, six versions, 34 cores, all 76 sealed Mach-O code/data/ABI fingerprints and shader compiler boundary verified. CI verifies 79 ad hoc signatures; Linux did not execute codesign.
- The actual delivered `libretro_internal_bridge` binary has weak-layout bytes `f0 52`: `_visiblePage` at offset 168 and `_rootPage` at offset 176 are both weak and absent from the strong layout. This checks the compiled correction in the IPA, beyond the source commit or a build label.
- Desktop Commander copied the same verified bytes to `C:\Users\Coren\Downloads\NeoStation-Build470-a43a5704.ipa`; the final Windows SHA-256 matches. The old 469 IPA remains untouched.

SideStore Apple re-signing is required, as with earlier private deliveries. No
public GitHub release was created. No physical iPhone, exact commercial
10-Yard Fight ROM run, 30-device-launch test or long thermal soak was available.
The retained-owner defect and its correction are established; definitive
disappearance of the reported device crash is not claimed.

The maintainer's two permanent rules are retained in `AGENTS.md`: never request
`.ips`, Jetsam or watchdog files, and never repeat passing validations when
their tested inputs are unchanged. The final delivery reused the successful
Dart, source-contract, Swift, NeoSwap, native libretro and skin results; only
the changed delivery guards and the targeted ownership/cheat regression were
executed for the new change.
