# MeloNX visual-artifact follow-up — 25 October 2026

The maintainer reports persistent visual defects with the recommended shader
settings. The symptom was clarified as visual defects, rather than only stalls.
The supplied eleven-second recording shows the settings for Persona 5 Royal:
resolution 0.75x, shader cache on, asynchronous shaders off, VSync on, bilinear
filtering, host memory tracking on and texture recompression off. It does not
show gameplay or the defective pixels. Do not classify this as user error, or
claim to have reproduced the visual defect from this recording.

## Separate the sessions

`app (1)(3).log` contains 8,479 lines and many historical processes. The latest
process is PID 83904, starting at line 8285. Persona 5 Royal is selected at
12:43:57 UTC. The recent Apple audio correction is demonstrably present:
48 kHz stereo, a 20 ms scheduling lead and owned AVAudioSession playback are
recorded. The first Metal frame is confirmed at 12:44:11; closing begins at
12:46:33 and completes with successful native return at 12:46:36. No new
ErrorDeviceLost or shader compilation failure is recorded in this process.
This does not prove that its rendered image is correct or its audio sounds good.

The previous Zelda report, `app (1)(2).log`, is a different failure: PIDs 2326
and 2353 report syncpoint delays, ErrorDeviceLost, failed teardown and quarantine.
Do not transfer those failures to this Persona session.

## Cache warning is not a visual diagnosis

The latest Persona session warns that the main Vulkan pipeline cache is
**estimated** at 128.09 MiB against a 128 MiB budget (line 8391). In the pinned
upstream `PipelineCacheManager`, `NotifyMainPipelineCreated` computes this
estimate; it does not measure the final blob or prove that persistence failed.
`Maintain` later queries the actual size. If it really exceeds the budget,
the previous snapshot is preserved. Its final result is logged at Info/Notice,
which the embedded warning/error relay does not forward to the app journal.

This warning does not establish failed shader compilation, GPU memory
exhaustion or the cause of missing textures. Increasing the memory budget,
deleting caches or changing the user's preferences is not justified by it.

## Confirmed diagnostic defect and scoped correction

The actual graphics-options message begins with `resolution=...`. The existing
native secret scrubber intentionally redacts complete key-assignment lines.
It therefore masks this entire safe diagnostic as `[redacted key entry]`,
including the latest process at line 8380. That prevents comparing the options
shown in the UI with the post-override options used by the native engine.

The source correction adds `Applied graphics: ` to that fixed-format numeric,
Boolean and enum diagnostic. It preserves the secret scrubber unchanged. No
renderer, compilation policy, memory budget, preferences or cache data changes.

`test/melonx_effective_graphics_journal_test.py` runs the production parser,
option application, extracted production formatting statement and actual
native journal on .NET 10 with the pinned upstream enums. Its 22 assertions
reproduce the old masking, preserve both the reported and opposite explicit
settings in the ring and file, exercise a comma-decimal host culture, and keep
synthetic personal key material redacted. Exact input hashes are recorded in
`docs/evidence/melonx-effective-graphics-journal.json`.

This particular change is diagnostics-only. The subsequently clarified short
recording shows the Persona 5 Royal main menu with black regions. The other
recording shows Persona 4 Golden; it is not a same-scene comparison. The original
journal still does not prove the cause of those pixels. A separate reproduced
pipeline-lifetime defect and its private candidate are documented in
`docs/melonx-pipeline540.md`. Physical GPU validation remains outstanding.
No IPS/Jetsam reports are required.
