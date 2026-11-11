# MeloNX lot 14 — device protocol (IPA with Core 735)

Core 735 = Core 733 + `adapt_remap_sweep_range`: a guest Map or Unmap no longer makes the engine re-queue, restore and
re-send every partially mapped texture of the session, only those the event can concern. The bridge decodes the engine's
diagnostics report only when it changed. Nothing here was run on an iPhone. The protocol of
[Core 733](../melonx-733-gates/device-protocol.md) applies unchanged (two sessions, the same route, 20 minutes, a pause
after five; the first 120 s carry the heap sampler); this page lists what lot 14 adds.

## What decides it (engine `[MeloNX:core-performance]` samples, every 5.1 s)
`python3 tools/melonx/frame_budget.py MeloNX-performance.log --pid <pid> --window 130- ...` for the frames; for the samples:
- `counts.arrDeltaElems` and `counts.arrDeltaChanged` per sample (IPA 725: 12 758 to 40 390 visited, 12 028 to 37 175
  changed; one sample 1 616 503 visited);
- `gpuWork.arrayDelta` calls / ms / KiB (IPA 725: 137 to 572 calls, 286 to 681 ms, 1 262 to 20 018 KiB per sample);
- `gpuWork.compute` ms per dispatch (IPA 725: 130 to 150 µs including the nested deltas);
- `phases.gpuDispatch` ms per sample (IPA 725: 3.0 to 3.8 s in the slow stretches).
Expected if the sweep was the cause: `arrDeltaChanged` and `arrayDelta` ms divided several times, in steady scenes
first. Would refute it: the same figures; the deltas then come from the guest rewriting its pools, and the next lot
takes the per-element cost (the exact-length arrays, the three walks over the array's textures) instead.

## Frames, heat, memory
As in the Core 733 protocol: frame times from t=130, `en=` and `sw=` (watts, wake rates), `th=` over the 20 minutes,
`[MeloNX:heap]` lines, `zones=`. Less GPU-thread work per frame shows as fewer millijoules per frame at the same rate.

## The host side
`cpu=`: the thread of the host's diagnostics queue (an unnamed `threadNNN` at priority 20 in IPA 725, 5.1 s of CPU by
t=120, 4 % of a core) should be at a fraction of that. Host measure: the journal test's `READERCPU` line (stall-watch
run on macOS).
