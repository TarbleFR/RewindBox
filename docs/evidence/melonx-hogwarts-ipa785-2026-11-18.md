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
