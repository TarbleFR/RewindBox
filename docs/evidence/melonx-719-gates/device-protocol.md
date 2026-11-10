# MeloNX lot 9 — device protocol (IPA after 718)

Inputs to check first: the IPA's manifest names the MeloNX Core of this lot (Core 719 candidate, contract and binary
recorded in `run.json`), the patched MoltenVK (`MeloNX-MoltenVK-rebuild-9936f295…`, binary sha256 `6d3a8d03…`, marker
"RewindBox drawable ownership"), and the bridge commit with `MLXSkinInteraction` and the journal field `mgd=`.
Settings unchanged between runs; caches and saves kept (no deletion of the player's caches); thermal state noted.

## 1. Presentation crash (Super Mario 3D World + Bowser's Fury, 1x, async shaders on, vsync Unbounded)
- Same scene as PID 45805 (IPA 718: SIGSEGV about 41 s after resuming, `presentCAMetalDrawable`).
- Three sessions of at least 5 minutes each: continuous foreground; one loss/return of activity (Control Centre)
  after 30 s; one with screen capture on. Count crashes and the session length each time.
- Then the same three with vsync Switch (a bounded rate shortens the race but does not replace the fix).
- One session without a crash does not prove the fix; report the count of sessions, their length and conditions.
- Journals: `MeloNX-crash.log` (any signal), stderr `[mvk-warn]`/"can only be presented once" lines.

## 2. Skin touches after the in-game menu (any Switch game, Switch Pocket skin, controller off)
1. Buttons and both sticks answer (perf journal `in=` shows `tL`/`tR`, `b`).
2. Menu from the skin's own Menu control → Resume → touch A at once: pressed in game at the first contact.
3. Repeat 5 times; then open the menu while holding the left stick: after Resume the stick is centred, no ghost
   button, Menu not stuck.
4. Each menu entry that resumes (Resume, RAM graph, Stick buttons, Screen format) once.
5. Controller on with "hide touch controls": skin hidden; controller off: the skin answers again.
No rotation, skin change or relaunch should be needed.

## 3. Long stutters
- SSBU (asyncShaders off, the player's setting) and Hogwarts (1x, async on): the same routes as IPA 718, caches kept;
  a first pass and a warm repeat.
- From `MeloNX-performance.log`: presentation intervals p50/p95/p99 and counts over 50/100/500 ms
  (`tools/melonx/frame_report.py`); `mgd=` per second (ms the engine call waited: a GC suspension in progress) next to
  `.NET_BGC` CPU on the same line.
- From `MeloNX-core.log`: `gcEvent` lines (pauses, `fellBackFromBackground`, fragmentation from the gen2/loh columns),
  `gcKeepAlive elevated` lines and the summary's `fragmented skips` / `requests run blocking`.
  Expected with the guard: no keep-alive request when gen2 + LOH fragmentation is above 0.48; a blocking gen2 the
  runtime still runs is its own schedule (journaled as such), not the keep-alive's.
- Hogwarts' 3666.692 ms background final pause (index 211, ratio 0.31): decide between a suspension waiting for a
  thread (`mgd=` of seconds with `.NET_BGC` CPU near 0) and marking work (`.NET_BGC` CPU high).
- Pipeline caches: `pipelineCache checkpoint/checkpointSkipped/written` lines, `cacheSizeProbe` and `cacheSave` in the
  performance samples, render-thread compilations and `Pipeline variants` (ready before first draw, planned not built).
Phases overlap: never add them as one budget; worker totals are not one freeze.
