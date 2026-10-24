# Build527 — controlled iPhone follow-up

Reference: the already delivered Build526, source `d1354170efa22d18ab6cca898998a340239a90c2`. Verified candidate: Build527, Core `75ffd142645392f75608aa7c9797195289b498de`, assembly `df9f76eba2b2fba741edebf0d042548bff7d5d89`, IPA SHA-256 `884a44dea6e627fc9cd774d296dc2abf1ef683ca01572651d5c0e3425bd9756e`. Installation requires personal Apple re-signing. Existing supplied device files are Build525 and cannot replace this comparison.

Use the same iPhone16ProMax, same GoWIII edition/update, exact same checkpoint/route, resolution, CPU/SPU options, frame limit, sound and controller state. Keep charging state, screen brightness, available storage and other foreground/background apps comparable. Start each run at the same reported thermal state; a hot candidate and cool reference are not a controlled comparison. Leave original game saves, savestates, keys and caches intact. No system crash logs are required.

## First-start preparation (timed separately)

Record the app build/Core source and effective JITCPU configuration from internal diagnostics. Note whether the Core's own cache identity triggers compilation. Time launch to first guest presentation and loading to the selected checkpoint. Do not include native loading UI frames in game FPS.

A true cold comparison requires matching empty **isolated** cache copies for each Core; preserve the original caches. If this is unavailable from the current app, mark `cold_comparison_available=false` and report each first-start observation separately rather than deleting user caches or calling a warm run cold. First compilation can exceed five minutes and is outside the active test below.

## Active follow-up — eight minutes per build, after first guest presentation

Record the wall-clock start/end of each phase in a short note or screen recording so the exported internal log windows can be assigned reliably. Intervals straddling transitions are excluded from scene statistics. Discard the first complete five-second report after each scene transition or resume as well: its first guest interval can have begun before the labelled phase. Begin the phase annotation only after this guard interval; do not classify a paused gap as gameplay stutter.

| Time | Phase and action |
|---|---|
|0:00–0:30|Game menu, same camera/menu; no input changes.|
|0:30–1:00|Same cinematic segment, if replayable; otherwise label this interval `unclassified` and skip its comparison.|
|1:00–4:00|Same demanding gameplay route, same attacks/camera/checkpoint. Collect a complete three-minute window.|
|4:00–4:15|Pause then resume using the same controls; confirm audio/input returns.|
|4:15–4:45|Close game; remain in library so memory cleanup is sampled.|
|4:45–5:00|Launch again without restarting the app. Time the second launch/loading separately. If loading takes longer, extend the test; do not shorten gameplay to preserve a nominal eight-minute duration.|
|5:00–8:00|Repeat the same three-minute gameplay route with warm caches, then close and export internal app/RPCS3 logs.|

Run526 and527 in alternating order on a second pass if possible. Report native UI, first loading, menu, cinematic and gameplay separately. A three-minute warm interval is a useful screening test, not prolonged-session validation. Prolonged validation needs an additional matched20–30minute gameplay session per build, with logs before/after pause, close and second launch.

## Report fields and interpretation

The existing526 COREPROF mixes UI/presentation windows and does not provide FRAMEPROF527 guest-only quantiles or JITPUB527 timings. Compare only fields whose definitions and phase coverage genuinely match. The new527 guest median/P95/P99 and JIT publication measurements establish a new baseline; do not subtract them from old526 COREPROF values or claim a matched historical JIT time. An exact future526/527 quantile comparison would require equivalent instrumentation in526; this cycle delivers only527, not a second speculative IPA.

For each matched phase: guest-presented frame count, interval duration, FPS, guest-interval median/P95/P99, frames>50/100ms (and histogram-based thresholds), maximum frame time, JIT publication count/time/max/ranges newly flushed versus historical ranges skipped, SPU cache load count/time/max, pipeline queue/compile time, compile-admission waits and ranges/RSX fence waits. Keep each counter's scope explicit; CPU times across parallel threads are not additive wall time. A P95/P99 aggregated from bucketed or sampled data must be marked approximate; unavailable526 fields remain unavailable.

Memory: peak and stabilized process footprint, resident, virtual and compressed (when provided); JIT/data high-water, VMA allocated/block/unused, requested textures/recyclable bytes, compiler buffers and NeoSwap live/prepared/shared backing. Do not sum overlapping process/shared/donor counters. Note memory after close and after relaunch; a larger configured NeoSwap target is not physical-memory savings.

To decide whether incremental JIT helps gameplay, correlate new publication events with slow frames and compare matched warm gameplay windows. A lower synthetic finalize cost alone does not establish fewer in-game pauses. For waits, identify the blocked component, producer and exact resource before changing synchronization. Keep GPU time unavailable if reported as−1.

Export only existing application journals (`app.log`, `RPCS3-diagnostic.log`, `RPCS3-diagnostic.1.log` when present, `RPCS3-milestones.log`, NeoSwap operations if available). Export the cold-start observation before starting the warm run. The diagnostic writer retains one previous2MiB generation, so export checkpoints during a20–30-minute session as well; pass all generations to the analyzer, which deduplicates mirrors. No IPS/Jetsam/watchdog report is requested. Preserve failures and classify incomplete runs; do not average them into successful gameplay.

## Log analysis

Use `python3 tools/rpcs3/analyze_cell527_logs.py app.log RPCS3-diagnostic.log --phases phases.json --output comparison527.json`. The phase JSON contains epoch seconds: `[{"name":"gameplay_warm","start":1792872000,"end":1792872180,"build":"527","pid":12345,"session":1}]`; replace all example values from the actual run. Session/window joins remove mirrored records and transport ordering. Merged quantiles are histogram upper bounds. The analyzer refuses conflicting mirrors, labels unknown phases explicitly, and never fabricates a526 measurement. Shared/process/VMA categories are not summed. Session sampled memory peaks are not phase-specific peaks.
