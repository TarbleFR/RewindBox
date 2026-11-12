# Switch 2: stop cleanly, then start another game in the same RewindBox session

The maintainer asked for this project on 12 Nov 2026, after asking why the other emulators can switch games without
restarting RewindBox and the Switch 2 engine cannot. It is not part of the IPA built next: the maintainer chose to ship
the preparation progress first. It cannot be validated on a device before a first Switch 2 game boots (task E2).

Today, after one Switch 2 game in a process, `launchGame` refuses a second one with `engineRestartRequired`
(`packages/s2arm_engine_bridge/ios/Classes/S2ArmEngineBridgePlugin.m`). The player must close RewindBox and open it again.

Switch 1 to Switch 2, and back, stays a restart. The two engines each carry a NativeAOT .NET runtime, and two of them
cannot share a process. This project does not change that.

## Inventory (12 Nov 2026)

What remains after a game ends in guest mode. Read in the engine at pin `6b6a5715` with RewindBox patches 0001-0009,
and in the bridge. Read only: nothing was run on a device. Metal and audio internals, and the static caches of the .NET
services, are not read yet. The main lines below were checked a second time in the source.

- **The engine already restarts a session in-process, for the same game.** On Apple, `restart_session`
  (`runtime/src/session.c:440`) is reached through `s2a_host_restart` (`session.c:671`). It quiesces the game, shuts
  the managed session (`S2A_ShutdownSession`), resets the window, loader and gate state, and boots again. S2Arm uses it
  from its settings menu.
- **Our guest stop does not use it.** `s2a_rb_guest_stop` ends with the process shutdown, `s2a_host_shutdown`
  (`runtime/src/rb_guest.c:127`, patch 0006). The process exit is sticky (`session.c:145-151`, `SESSION_EXITING`), and
  so is the gate's terminal park (`gate.c:143-147`). The managed side never goes back to `Empty` after `ProcessExit`.
  - The game threads are parked, not joined, so their stacks and mappings stay.
  - The stopping thread parks forever (`rb_guest.c:118`, `pause()`): one GCD worker is lost per game.
- **One-shot latches:**
  - `configure` runs once (`rb_guest.c:45`) and `g_ended` is never cleared (`rb_guest.c:23,82`).
  - The launch context is decided once (`launchctx.c:199-203` `pthread_once`, `launchctx.c:242`, `launchctx.c:267`).
  - The view controller is made once and started once (`ios/app.m:166,917,968`).
  - The bridge's `engineLoaded` flag never resets.
- **Per-game environment and files:**
  - `S2A_*` values of game 1 stay in the environment, and the services read some of them (`S2A_GAME_DATA`).
  - The image pack fd and the file-backed window are per game. The `host.log` fd is opened once.
- **Executable pages (the hard limit for a different game).** iOS cannot rewrite or unmap the kept R|X pages
  (`vawin.c:310-313`). New ones come only from the JIT helper (command 1 of `S2ArmCodePages`). The bridge detaches the
  helper 2 s after boot, and after that command 1 cannot run (`S2ArmEngineBridgePlugin.m:345-346`). The spare pool is
  sized for game 1's later NROs. The same game can reuse its identical pages (`code_same`, `loader.c:690`); a different
  game needs new ones.

## Plan

1. **Same game, after Quit: no restart.**
   - The guest stop takes the restart's retirement path, without the process shutdown: quiesce, managed
     `S2A_ShutdownSession`, then the window, loader and gate session resets.
   - The bridge allows a new `launchGame` for the same title id once the engine reports the session retired.
   - Host tests on macOS first: stop, then start again, with the restart path's own checks. Then iPhone.
2. **Re-armable latches and a per-game reset.**
   - Covers `configure`, the launch context, the view controller and start, `g_ended`, and `engineLoaded`.
   - The `S2A_*` environment and the per-game fds are reset each time.
   - No GCD worker parked forever.
3. **Another Switch 2 game.**
   - New executable pages for its boot code: re-attach the JIT helper for each launch, or keep it attached for the
     whole run. Whether iOS 26+ allows either is to be proven on a device.
   - The window must be placed or resized for the new `main.npdm`.

The first two steps are engine patches (`build-utils/s2arm/engine/patches/`, marked `RewindBox`, listed in the legal
notices) plus bridge changes. The engine needs a new build and a new `engine` pin from main.

## Step 1 design: park on Quit, resume the same game (12 Nov 2026)

Engine patch `0010` (session.c, rb_guest.c, rb_guest.h). It builds only on S2Arm's own in-process restart, the one its
iOS settings page uses ("restart now", `ios/app.m:91,429`).

- **Park.**
  - `s2a_host_park(callback, context)` is `s2a_host_restart` with a flag, and `restart_session` honours it. It runs the
    whole retirement: quiesce, `S2A_ShutdownSession`, graphics destroy, every per-session reset, window, memory,
    loader, os. Then the generation CAS `RUNNING -> RESTARTING(old + 1)`.
  - It stops before `g_rebuild()`: no guest, and `restart_done_notify` is not called, so the first-frame barrier
    stays shut.
  - The control worker's callback reports "parked".
  - `s2a_rb_guest_stop` asks for a park when `s2a_session_rebuild_supported()` holds and the host gave a
    `session_parked` callback (new member of `s2a_rb_guest_config`; the size grows, so older hosts keep the old path).
    If the park is refused or fails, it falls back to today's process shutdown, so no regression.
- **Resume.**
  - `s2a_rb_guest_resume()` is refused unless the engine is parked. It runs `s2a_host_rebuild()` on the retirement
    worker, as `restart_session` does: graphics settings, pad and gfx resets, `load_session_modules`,
    `S2A_InitSession`, guest start.
  - Then `restart_guest_publish_running` and `restart_done_notify`.
  - The host presents the engine's view controller again (`app.m` keeps the same one); `s2a_rb_guest_start` is not
    called a second time.
- **No new executable pages.**
  - In guest mode `s2a_window_session_reset` keeps the code pages (`vawin.c:303-325`, prepared by patch 0004).
  - The loader reuses a block in place when its content is byte-identical (`code_same`, `loader.c:690-698`), and
    `s2a_imgpack_map` (the only caller of `prepare_code`) is not reached for it.
  - So the same game resumes without the JIT helper, which detached 2 s after the first boot.
- **Bridge.**
  - The status map gains `parkedGameId`.
  - `launchGame` for that title id resumes: no configure, no JIT transaction, no pool. It then presents the view
    controller.
  - A different title id is still refused (`engineRestartRequired`) until step 3.
- **Dart.** `launch()` no longer refuses an `engineLoaded` engine whose `parkedGameId` is the game's id.
- **Proof.**
  - Static checks of the patch: the park skips only `g_rebuild` and the barrier; the resume calls the same rebuild,
    publish and notify as `restart_session`; the fallback is the process shutdown.
  - The engine CI build.
  - On a device, once a first game boots: Quit, launch the same game again, and see the first frame. Then the save,
    and the memory after three cycles.

## Risks

- The restart path is S2Arm's own, but it has only been used for the same game, from its settings menu.
- The parked game threads and their mappings have to be released, or the memory grows with each game.
- Every step is unobserved until a first Switch 2 game boots on the iPhone.

## Step 1 implemented (12 Nov 2026, reviewed, engine build next)

- Engine patch `build-utils/s2arm/engine/patches/0010-guest-park-and-resume-the-same-game.patch`:
  - `s2a_host_park` and `s2a_host_resume` in session.c (above);
  - `s2a_rb_guest_stop` parks when the host gave `session_parked` and falls back to the shutdown;
  - `s2a_rb_guest_parked`, `s2a_rb_guest_view_controller` and `s2a_rb_guest_resume`.
  - The config accepts the size of a host built before the patch.
  - The series 0001-0010 applies on the pin. session.c and rb_guest.c compile here without warnings (`-Wall -Wextra`) on
    the non-Apple path, and on the Apple path through stub headers. app.m and the real Apple build are the engine
    build's.
- Exports: the three new entry points are in `build-utils/s2arm/engine/export_list.py` (the framework exports only that
  list), and `s2arm-engine.yml` checks them. Without this, `dlsym` would not have found them.
- Bridge:
  - `resumeParkedGame` presents the parked view controller, then calls `s2a_rb_guest_resume` in the presentation's
    completion. No dlopen, configure or JIT is involved. The settings apply again first.
  - `status` gives `parkedGameId`, and `session_parked` sends `sessionEnded` with `parked: true`.
- Dart: `launch()` lets only the parked title id through.
- Tests:
  - `test/s2arm_park_resume_test.py` (41 checks). A missing anchor is a FAIL line; each review fix below fails its own
    check when it is removed;
  - the bridge test (163 checks): the guest ABI is compared with the struct the whole series produces;
  - `test/s2arm_engine_exports_test.py` and `test/s2arm_session_menu_test.py` (each launch path checked on its own);
  - the Dart service test: the parked game resumes, another game and an end are refused.
- Then: the engine build, an engine pin, and the device check once a first game boots.

### Independent review of patch 0010 (12 Nov 2026)

A separate read of the park, resume and stop paths against S2Arm's restart found these defects. All are fixed in the
patch and the bridge except the last one, which only a device can settle.

1. **A failed resume left what the rebuild started running.** It now fails the session, then stops and joins the guests
   and services, as a failed restart does (`stop_failed`, `s2a_gate_stop_begin`).
2. **A park that timed out fell back to a shutdown while the retirement worker still owned the services and the GPU.**
   That would dispose them twice. When the retirement is still busy, the session now ends for the host without a
   shutdown. That process cannot run another Switch 2 game.
3. **The park flag was set before the restart request was accepted.** A Quit during S2Arm's own restart could have
   turned that restart into a park. The flag is now stored by the accepted request only, after its CAS, under the
   request lock.
4. **Quit, SIGTERM and app termination did not know about the park.**
   - Quit during a park, a resume or a restart is ignored, so a shutdown never runs on top of one.
   - SIGTERM while parked exits at once, as after an end.
   - App termination while parked runs no shutdown: the save was written by the park.
5. **A second tap during a launch or a resume answered "restart required".** The bridge now answers "busy" first.
6. **The stop reason leaked after a park, and could be a literal.** `park_result` frees it after a park and after a
   timed-out park, and keeps it for the fallback shutdown, which logs it later. A park now needs the heap copy.
7. **Device check: the same game whose code blocks differ.** A block reuses its page only when it is byte-identical
   (`code_same`). Otherwise the loader takes pages from the spare pool, sized for the first boot's later NROs. The JIT
   helper detached after that boot, so an empty pool cannot be refilled: the resume then fails and the session ends.
   Only a device run shows whether this happens.

