# Hogwarts Legacy: device evidence and targeted performance work

The supplied `app(1).log` confirms sustained poor performance in Build 604.
The later delivered Build 605 adds achievement presentation/translation and
retains the same MeloNX Core; it does not ship this performance work.

The exact attachment is 5,078,608 bytes, SHA-256
`39776381e25defdf494c01e4613f745733e4c1c7a7ab06256e7dda2c6d8c8aa2`.
Hogwarts 1.0.5, title `0100f7e00c70e000`, runs in PID 56408 with Core
`ada4058f5738465ac882934bb87224b637bcd0a1`. The selected window is lines
36060–37052; Smash begins at 37053 and must not be combined with Hogwarts.
Earlier journal sessions are not new Build 604 observations.

## Sustained gameplay window

There are 198 performance samples. The following 93 samples at `t=101…193`
exclude the final pause and are independently recomputed from the supplied file.

| Measurement | Observed value |
| --- | ---: |
| Median / mean FPS | 3.6 / 3.5914 |
| Median frame interval | 276.4 ms |
| Median process CPU | 210% |
| Median `GPU.MainThread` CPU | 70% |
| Median `.NET_BGC` CPU | 50% |
| Median render thread CPU | 26% |
| Median FIFO processing occupancy | 100% |
| Resident footprint | 3,674–3,762 MiB |
| Process memory headroom | 2,893–2,981 MiB |
| Thermal state | nominal, 93/93 samples |

CPU 100% represents one CPU core. `GPU.MainThread` is a CPU thread and FIFO
occupancy measures host dispatch activity; neither measures physical GPU
utilization. No memory exhaustion, thermal throttling or new fatal termination
is demonstrated in this Hogwarts session. Different scenes and caches prevent
an honest A/B FPS claim against earlier sessions.

## Confirmed source costs

1. The log reports a 63.77 MiB worker checkpoint and 37 further repetitions.
   The cache maintenance code bypasses normal checkpoint spacing when its
   estimated size approaches budget, even while its measured size still fits.
   Restore disk-checkpoint pacing while retaining urgent size probes, recycling,
   dirty generations and forced final persistence. These snapshots can add
   startup work; their duration is not measured and they do not explain the
   late low FPS alone.
2. `CounterCache.FlushPendingReports` individually removes every completed
   item from a list. Remove a matching snapshot prefix once; retain exact
   individual removal when concurrent/reentrant work has changed that prefix.
   This reduces CPU complexity without claiming lower GC allocations.
3. Buffer synchronization sorts a virtual-dependency collection even when it
   contains only one item. Capture the sole reference before its callback;
   retain the original sorted multi-dependency path and ownership. Measure
   both branch frequencies before assigning this cost to Hogwarts.

The previous work session tested these mechanisms but ended before a push.
Reconstructed code must pass fresh final-source fixtures before compilation;
old scratch receipts are not proof for the current candidate. The observed
304-byte single-dependency saving and checkpoint 193→2 result are host fixture
measurements, not measured device FPS gains. Negative multi-dependency timings
must remain visible in the current implementation's evidence.

## Diagnostics needed to choose the next lever

Measure allocation bytes, GC collections/pause time, completed dispatch/render
scopes, waits, pipeline creation, cache exports and the relevant buffer/report
batch frequencies. Mark overlapping CPU wall-time scopes and incomplete active
scopes explicitly; do not sum them as a frame time. Keep records bounded and
separate their process, generation, title, application build and Core identity.

Put new journals under `Diagnostics/<console or system>/`; retain old logs and
engine-owned compatibility paths in place. Avoid duplicating large Core records
through the general event ring and Flutter. No cache purge, GC-policy change,
resolution reduction or skipped GPU synchronization is justified by this log.

Sanitized numeric samples and recomputed aggregates:
[device-window.json](evidence/hogwarts604-performance/device-window.json).
The raw private journal is not committed.

## Reconstructed 606 candidate, 31 October

The integrated candidate starts from delivered 605 and preserves its achievement
translation and Dolphin hook. Four fresh Linux .NET 10.0.100 receipts bind the
actual prepared sources and collector under [hogwarts606-local](evidence/hogwarts606-local/):
pipeline checkpoint 646 assertions per variant, CounterCache 10,171 per variant,
Buffer 4,939 per variant, and diagnostics 103 runtime assertions plus 22 source
checks. They do not replace the pending Apple builds and runtime sessions.

The instrumented final candidate preserves 193 cache pressure probes while
reducing exports from 193 to 2, including final persistence. Its single virtual
dependency path avoids 304 bytes per call; other dependency counts have unchanged
allocation. CounterCache keeps allocation and semantic traces identical.

Negative host timings are retained: empty Counter batches measured 89→199 ns;
GPU Buffer synchronization with 2 dependencies was +11.9% and with 8 was +20.1%.
The one-dependency GPU/readback cases measured 519→100 and 736→205 ns. These
isolated, noisy timings include the new instrumentation and establish neither
universal acceleration nor physical-device FPS. The next categorized journal
must identify actual branch frequencies and remaining costs.

### First Apple execution

Source `ae78b4be6aa3fbc2db3537fd0a17c9aad75b2284`, Core run
`41239330287`, job `124649711327`: the four affected fixtures, both NativeAOT
compilations, ABI/source checks and actual simulator smoke passed. The smoke
contains two final diagnostic events: generation 1/sequence 59 and generation
2/sequence 95. The run nevertheless **failed** in the final Python validator:
it incorrectly required every managed-memory field to be scalar, including
the valid three-element `collections` array. The failed run and its original
bytes remain distinct from the separate corrected final validation.

Host run `41239330429`, job `124649711439`: Flutter, Dart analysis, Foundation
(54 Swift and 34 Objective-C checks), parity and performance checks passed.
UIKit failed its exact sample/final persistence assertion after fixed delays;
the captured report did not contain the observed rows, so a scheduling race
is not yet proven as the cause. The follow-up fixture waits for actual writes
with a deadline, keeps the exact sequence/count assertions, and records the
observed journal on failure. The following achievement integration command
had not run when this first native step stopped.
