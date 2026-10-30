# Prehash publication review and new native checks

## Production scope

The baseline and candidate are the actual `rpcs3/ios/IOSTexturePrehash.h` files from `device597-core-base` and `device597-core-memory`. The root agent changes production; this review writes only standalone adapters, runner and evidence. The runner copies each whole header and changes its namespace identifier solely to permit both versions in one translation unit. `lookup`, `publish`, the slot layout and indexing bodies execute unchanged.

The candidate prevents an obsolete epoch from evicting a newer completed result in a direct-mapped slot. Both a delayed result for the same key and a delayed colliding key can cause this before the fix. Old epoch lookup already rejects stale bytes: the defect is avoidable displacement of a reusable hash, not demonstrated stale texture acceptance.

## Ordering review

The candidate's initial sequence load must be **acquire**. A relaxed initial load followed by an acquire read of `slot.epoch` is insufficient: the sequence can observe the last writer's new stable value while the earlier epoch store is not yet ordered before the epoch read. The later acquire CAS cannot retroactively order that preceding epoch read. This was raised during review and the root agent corrected it before these executions.

With the acquire sequence load:

1. Reading a writer's stable even sequence acquires its release completion. That writer's epoch/key/hash stores precede the subsequent epoch read.
2. A sequence observed odd immediately rejects the attempt.
3. If a newer publication starts or completes after the initial sequence snapshot, the sequence changes. The one-shot CAS cannot acquire the slot with the old expected sequence. A publication occurring between the epoch read and CAS is covered by this case.
4. If the CAS succeeds, there has been no intervening owner. The observed slot epoch is no older than the stable publication acquired at step 1, so the earlier comparison against the candidate epoch is sufficient.
5. The winner writes the ordinary fields and release-publishes the next stable sequence. A rejected publication does not modify the slot. Same-epoch last-writer-wins and newer-epoch replacement remain permitted.

This reasoning retains the existing sequence-counter assumption: the counter does not wrap all the way around while one publication is pending. Epoch ordering is process-monotone in the reviewed source; no reset to an earlier epoch occurs between emulator sessions. Concurrent stress and TSan alone are not proof of all weak-memory executions; the acquire reasoning is necessary separately.

## Executed checks

**GCC 13.3.0, Linux x86_64**, C++20, `-O2 -UNDEBUG -Wall -Wextra -Werror -pthread`.

All three modes pass:

- Ordinary optimized build, with benchmarks.
- AddressSanitizer + UndefinedBehaviorSanitizer (`detect_leaks=0`, LeakSanitizer not claimed).
- ThreadSanitizer, **without suppressions**.

Each mode executes both exact headers. No historical unrelated suite is replayed.

| Deterministic case | Baseline | Candidate |
| --- | ---: | ---: |
| Same-key obsolete publications displacing a newer result | 1 024 | 0 |
| Colliding-key obsolete publications displacing a newer result | 1 024 | 0 |
| Same-epoch replacements accepted and checked | 1 024 | 1 024 |
| Newer-epoch replacements accepted and checked | 1 024 | 1 024 |
| Busy odd slot returns without mutation | 3 | 3 |
| Fallback lookups in 4 096 delayed-worker replays | 4 096 | 0 |

The replay uses 64 KiB logical ranges, representing **268 435 456 bytes of fallback requests avoided in the model**. The payload is a deterministic key/epoch oracle, not a real texture hash. The test does not time reading these bytes, and the count is not an estimate of iPhone traffic.

Each variant also executes **300 000 concurrent writer calls** (three writers) while a reader checks lookup payload integrity and observed slot epoch order. In the ordinary run, the reader observes 401 epoch regressions before and zero after; ASan/UBSan observes 1 778 before, TSan 5 380 before, and zero after in both. The scheduling-dependent baseline counts are diagnostic observations, not fixed expected totals. All modes report **zero wrong successful lookup payloads** for both variants. The test permits benign misses from contention and current-epoch collisions.

## Ordinary publication cost, including regressions

Seven alternating baseline/candidate samples per pattern, 300 000 calls per sample. No exclusive CPU or fixed frequency is claimed. Raw samples remain in `publication-plain.json`.

| Pattern | Baseline median (ns/call) | Candidate median (ns/call) | Change |
| --- | ---: | ---: | ---: |
| One key, same epoch | 3.13451 | 3.13735 | +0.09% |
| 4 096 keys, same epoch | 3.80290 | 3.94956 | +3.86% |
| 4 096 keys, advancing epochs | 3.85057 | 4.00974 | +4.13% |

The guard has a small ordinary-path cost in two measured patterns. Its benefit depends on obsolete publications that would otherwise evict newer hashes. No net game speedup or FPS gain follows from these isolated host timings. The iPhone frequency of this precise race is not measured by existing logs.

## Reproduction

```sh
python3 validate_prehash_publication.py \
  --baseline /path/to/baseline-core --candidate /path/to/candidate-core \
  --compiler g++ --work /tmp/publication-plain \
  --report /tmp/publication-plain.json --benchmark
```

Use `--sanitizer address,undefined` or `--sanitizer thread` and distinct work/report paths for the two sanitizer modes. Sanitizer executions do not collect timing samples. Source hashes are captured before generation and rechecked after execution; changed source bytes fail the runner.

The checks exercise only the new publication guard and its lookup interactions. They do not execute a GPU, an iPhone, the speculative hash kernel or the separate cancellation candidate.
