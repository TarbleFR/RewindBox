# MeloNX performance diagnostics: measurement boundaries

The observer attributes the remaining Hogwarts cost without changing guest
waits, query publication, drawing, GC policy or memory budgets. It samples the
existing accepted session every five seconds on the host's diagnostics utility
queue. The UIKit performance overlay remains unchanged. A one-off diagnostics
request on Darwin's main thread skips collection.

## What the fields mean

| Field | Meaning and limits |
| --- | --- |
| `phases[name]` | Completed calls, inclusive CPU wall milliseconds, bytes allocated on the calling thread. A wait contributes wall time. This is not physical GPU time. |
| `active[name]` | In-flight scopes and approximate age since the first scope registered in the overlapping group. That first scope can already have completed; an unpublished start is `null`. |
| `draws`, `dispatches`, `barrierRequests` | Calls at the selected production submission/request points. They do not prove hardware execution or GPU saturation. |
| `spanFallbacks`, `spanFallbackBytes` | Threaded-renderer payloads that took the actual array fallback, and their requested byte sizes. |
| `counterReportBatches`, `counterReportBatchMaxSession` | Calls to report flushing and largest snapshot batch in this session. |
| `counterReportsFlushed` | Successful returns from `report.Flush()`, not a count of guest memory writes or newly published query values. |
| `cacheExports`, `cacheExportBytes` | Successfully persisted cache snapshots after the file replacement completed. `cacheSave` includes failed attempts; exports do not. |
| `virtualDependencySingle`, `virtualDependencyMultiple` | Visits to the new one-dependency branch and retained sorted branch, across GPU synchronization and CPU readback. No per-binding stopwatch is added. |
| `managed.allocatedBytesApprox` | Approximate allocation delta across all managed threads, including diagnostic work. |
| `managed.collections`, `gcPauseMs` | Collection-count deltas for generations 0/1/2 and cumulative GC pause-time delta. Background GC CPU cost is a separate host-thread measurement. |
| `lastGc*` | Statistics from the last completed GC, identified by `lastGcIndex`; these are not current process RSS or physical memory pressure. |

Phases overlap through nesting and parallel execution and must not be summed
as frame time. Their call/time/allocation counters are independently sampled,
so a boundary can contain time or bytes before the corresponding completed
call appears. A long dispatch or drain is charged to its completion window;
the `active` fields distinguish this from an idle path.

Sixteen owner-thread counter slots are preallocated per accepted session. After
registration, per-command increments use no locks, formatting, IO, callbacks
or allocation. Additional threads are explicitly counted in
`untrackedCounterThreads`; their command counts are incomplete, while coarse
phase timing still uses shared atomic totals.

## Ownership and transport

Start occurs inside the accepted `EmbeddedSessions.Run` callback immediately
before loading. Stop detaches the epoch in the existing `finally`. A scope
retains its original epoch; late completion cannot charge a new game. If a
reader overlaps Stop, it finishes the current sample and one final partial
window without making the session thread wait. Registering a new generation
also rejects an old reader's late transport before the new game's first sample.

Performance events are outside the general 64-event journal. Normal snapshots
retain one performance record; a final record can retain the immediately
preceding sample, so a close cannot overwrite an undrained window. Each event
has sequence, generation, PID and UTC timestamp. The host drains preceding then
current exactly once and adds its cached title/build/Core context.

The native observer never writes these metrics to the Core file. Swift alone
owns `Diagnostics/Switch/MeloNX-performance.log`, including its bounded rotation.
This avoids resending 64 historical metric objects every 300 milliseconds and
avoids two independent writers rotating the same file.

`MeloNX-core.log` retains the existing redaction and fatal-append behavior and
now rotates at 5 MiB to one `.1` predecessor. Legacy shared `app.log` keeps its
old ceiling. A fatal append crossing the rename/create gap gets one creation
and open retry; normal creation uses `OpenOrCreate` so it cannot truncate a
fatal writer's replacement file.

## Fresh verification scope

The Linux .NET 10.0.100 fixture executes the complete production collector and
journal, including native append calls: **103 assertions passed**, plus **22
source-composition checks**. It exercises generation isolation, reader/Stop
overlap, bounded final transport, counter-slot overflow, GC deltas, active
phases, real redaction, file errors, rotation and fatal append across a missing
destination. Warmed command counters and coarse scopes allocate **zero bytes**.

The isolated latest-only snapshot measured 1,854 serialized bytes and 18,544
allocated bytes per read in this fixture after 64 samples. Its maximum-width
metric payload was 2,495 characters, below the journal's 4,096-character bound.
These are host measurements, not iPhone cost predictions. The final-source mode
recompiles the actual prepared collector and journal and binds all hook
postimages. The other ten hook classes require the separate complete NativeAOT
build; this fixture does not pretend to compile them.

The changes do not establish an iPhone FPS gain. The next device journal must
show how often the optimized branches run and where allocations and waits
remain, with matching title, generation and binary provenance.
