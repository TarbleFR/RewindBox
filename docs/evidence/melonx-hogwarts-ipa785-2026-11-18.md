# Hogwarts Legacy on RewindBox IPA 785

The November 18, 2026 capture came from the second RSwitch session in the same RewindBox process, after Super Smash Bros. Ultimate exited. The Hogwarts Legacy title ID was `0100f7e00c70e000` and the IPA contained MeloNX engine `77a5340d07fcb8997c8720b3c995e6c775a2437e`. The app, launch, core, performance and stderr journals agree on the session identity. The performance log has no scene markers.

## Observations on iPhone

| Signal | IPA 785 |
| --- | --- |
| Unpaused FPS samples, 75–105 s after start | Median 20.55 FPS. Seventeen of 20 readings below 25 FPS. Lowest reading 11.1 FPS. |
| Compositor-facing throughput in three successive ~5 s windows | 92, 69 and 87 presents, about 18.3, 13.8 and 17.3 FPS |
| Descriptor preparation in the first and third windows | 1.25 s and 1.28 s across graphics and compute |
| Host synchronization in the same windows | 1.87 s and 1.50 s of waits. The first window had 702 submissions, including 365 strict synchronization submissions. Timers overlap. |
| GPU active during the first two windows | About 37% and 25% of each window |
| Observed first-use pipeline waits | 771 ms and 1,058 ms. Other sustained slow windows had no draw-time compilation wait. |
| Device memory in the sampled stretch | 5–8% available, dropping lower at other times. Process footprint peaked at 4,819 MiB. The process still had roughly 1.9 GiB of headroom at the first warning. |
| Launch to first confirmed Metal presentation | Roughly 7.4 s with a warm shader cache. The main cache mapped about 98.5 MiB and became ready in about 1.3 s. |

The close first stopped the guest, then the render worker faulted at `GPFifoDevice.DispatchCallsCore + 0xc4`. Disassembly of the exact device library shows a null check of the channel memory manager immediately before the uncached FIFO read. The old deferred destruction could unbind the channel ahead of its accepted entries. The failed teardown quarantined the engine and retained the donor lease.

## Changes for the next core

- Retire channel resources and their syncpoints after the accepted FIFO entries in order. Keep the physical memory caches alive through the last channel. Recycle fragmented late-read buffers after processing. On shutdown, preserve the existing stop fence and release queued resources after the consumer has stopped.
- For the Hogwarts rendering policy, give ready frames time to present during a sustained FIFO backlog. Coalesce nearby occlusion report submissions with a 4 ms fallback and submission on demand. Look up host sync handles by ID.
- Retain compatible buffer descriptor sets on program switches. Skip buffer-texture storage commands that repeat an identical logical range, invalidating the shortcut when a buffer is deleted. Skip pool-array descriptor updates when the resolved host binding is identical.
- Record slow first-use pipelines even if a worker logged that variant first or the state matches the default. Keep the strongest timing across out-of-order writes. Prioritize costly entries during warm-cache replay within the existing launch priority, replay budget and device memory limit.

## Follow-up on shader stalls

The same session filled the 2,048-entry variant journal. Seven variants were evicted, with no cost recorded for those evictions. The previous admission policy ranked variants by recency and use count. Within each recency tier, the Hogwarts policy now ranks candidates by their recorded cost when either candidate reaches 100 ms. It can decline a cheaper candidate once only more expensive recent victims remain. It also accepts a later, costly draw note if an earlier worker note for the same variant could not be admitted. The entry count and disk format have the same bounds.

Cached programs offered while the journal was loading are ranked as a batch before replay starts. For Hogwarts, the replay queue also waits for the Vulkan driver's primary cache while that snapshot loads. The cache loader wakes the queue as soon as the snapshot can serve lookups, or when the load ends after a failure. Speculative work still respects the device memory threshold, worker limits and compile budget. Actual draws can still demand a pipeline through the normal queue.

The target is a repeatable 25–30 FPS in the gardens on the same phone and save after thermal stabilization. A matching route with a warm cache can separate sustained performance from new shader misses. The capture establishes a baseline. The new core's throughput, thermal behavior and user-visible exit still need device measurements.

## Sustained load on iPhone

The last nominal sample was at 61 s and the first fair sample was at 69 s. The session recorded 58 nominal and 64 fair samples. One five-second window contained 139,691 indexed draws, 100,462 buffer uploads and 12 synchronous render requests. The local freeze recorder reported 955.9 ms of its own CPU time across 14 reporting intervals with live forwarding off. The process-wide heap hook recorded 45,104 allocation samples in its first 46 s. Those measurements describe work in IPA 785. They do not attribute the thermal transition to a single subsystem.

The threaded renderer now checks the synchronous request slot with an acquire read before attempting to claim it. The sole consumer publishes completed queue counts in groups of up to 32 already available commands. It releases each ring slot individually, signals each requested result as soon as it is ready and accounts for a partial group on an interrupt. A lone command drains immediately.

For a local Hogwarts session the host leaves the process-wide allocation hook off. Setting a live capture destination before launch enables detailed heap attribution again. The freeze recorder samples threads at a target period of 100 ms locally, or 250 ms from the first observed fair state through 60 s of nominal recovery. The local CPU stack profiler also observes that cooling window. Explicit live capture retains the 50 ms period. Presented frame and drawable timestamps are still recorded individually in either mode.

After the per-second journal has written its 1,800 detail lines, the host stops enumerating threads and gathering the hardware and VM counters for those lines. The exit marker and session totals continue, including frame pacing, audio and thermal state. Measure the next IPA on the same save and route with the cache already populated. Compare time to the first fair reading, share of active time spent nominal, and presented gaps above 40 ms across a sustained run with the same power and display settings.

The production GAL compiled in Release on Linux. With an inert graphics backend it executed 289,296 asynchronous commands and delivered 48 synchronous results in order, with 51 concurrent interrupts, repeated ring wraparound and an empty queue at close. A second run counted the changed operations locally. Over 289,344 commands it made 48 atomic attempts to claim a synchronous result and 9,268 atomic queue-count retirements. The previous loop issued one of each per command. These counts measure queue bookkeeping in that workload. The iPhone's power consumption and game frame times require an on-device run.

[NativeAOT build and iOS simulator run 44274960144](https://github.com/TarbleFR/RewindBox/actions/runs/44274960144) produced both ARM64 libraries. Two homebrew sessions released their backing memory. The archived binaries, prepared sources, ABI receipt and normalized device fingerprint match the pin in this branch.
