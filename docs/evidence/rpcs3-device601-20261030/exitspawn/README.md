# BO2 internal process switch: source fix and host verification

The supplied BO2 sessions reach another renderer initialization after the
`t6mp_ps3f.self` transition. They do not establish a missing SELF or a native
driver deadlock. The current ordering opens/decrypts the executable, computes
the main module hash, assigns its path, calls `ConfigurePPUCache`, and only
then initializes the renderer and imports its executable-scoped Vulkan cache.
The `ENOENT` for an earlier `/dev_hdd0/game/t6mp_ps3f.self` probe is therefore
not treated as the cause of the later preparation interval.

One source defect is reproduced: `lv2_exitspawn` previously called `BootGame`
from UIKit's final cleanup callback. Native shader-cache preparation could
therefore block UIKit for its entire duration. The changed path uses the
existing owned worker and Core API mutex. VFS/FXO capture and the original
asynchronous stop stay on UIKit; loading the next SELF runs on the worker
after renderer cleanup. The queue has one active task and at most one pending
process-transition phase. Legacy savestate `post()` remains exclusive.

Both phases check the cancellation generation, exact native emulation
identifier and title before applying captured arguments. The UIKit capture
checks again after dispatch. A wrapper stop clears continuous mode even in
the stopped gap before a delayed cleanup callback posts its continuation.
An active native cache import is not interrupted: an explicit stop waits for
the API mutex, and no second native boot overlaps it. Surface and pad updates
keep their existing independent synchronization. No new host ABI or profiling
counters are introduced.

A bounded private completion hook preserves a SELF request behind an active
savestate. It neither overwrites that save's callback nor waits on the worker
that must restore it. A failed preparation resumes the original process
transition. A successful restore permits its exact one replacement process,
then stops it before switching SELF. If saving/restoration already failed
after killing the original PPU and resetting its FXO, the request reports an
error and remains stopped with continuous/force flags cleared; it does not
read absent FXO objects. The original process is already gone in that case,
so a new game launch is required. The public status snapshot is unchanged.

## Executed checks

`test/rpcs3_exitspawn_worker601_test.py SOURCE --baseline BASE --report OUT`
accepts `--sanitize`, `--compiler`, `CXX` and `HOST_MACOS_SDK`. Its baseline is
the cumulative `b9346b5` source, including the short vertex-upload correction.
The script extracts the complete old/new `lv2_exitspawn`, the owned executor
and new transition wrappers. The real savestate operation header is included.
Core, VFS, FXO and UIKit are explicit doubles; a controlled latch represents
blocking driver work. It is not a GPU simulator or a Metal benchmark.

Both ordinary execution and ASan/UBSan pass **22 scenarios**. They cover the
old UIKit boot versus the worker boot, UIKit progress while driver work is
held, API-stop exclusion, stale callbacks before argument mutation, native
restart identity changes between dispatch and capture, preservation of a later
stopped incarnation despite an old saved outcome, the stopped gap,
recursive SELF transitions, bounded pending work, legacy queue exclusivity,
save failure before Kill, successful automatic restore, save failure after
Kill without any FXO access, completion-before-registration, cancellation,
worker shutdown, state/display rejection and exceptions. The non-iOS
`lv2_exitspawn` body is identical after preprocessing. The API stop/boot/
shutdown cancellation ordering is checked from the real source; the harness
does not execute the full installed-game or public shutdown implementation.

Results and exact input hashes: `boot-plain.json`, `boot-asan-ubsan.json`.
`stale-incarnation-before.json` records the reproduced flag mutation before
the exact incarnation guard was tightened. Separate `status-plain.json` and `status-asan-ubsan.json` exercise the actual
completion hook, including registration races and reentrant callbacks.

No Core/IPA compilation, CI dispatch, push, release or iPhone execution is
performed. This fixes the demonstrated UIKit blocking path; it does not prove
shorter Metal preparation, successful BO2 multiplayer gameplay or extra FPS.
