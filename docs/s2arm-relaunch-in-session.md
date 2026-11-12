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

## Risks

- The restart path is S2Arm's own, but it has only been used for the same game, from its settings menu.
- The parked game threads and their mappings have to be released, or the memory grows with each game.
- Every step is unobserved until a first Switch 2 game boots on the iPhone.
