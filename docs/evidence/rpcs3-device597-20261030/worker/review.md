# Cancellable prehash worker integration — 30 October 2026

The candidate integration passes **19 focused cases in ordinary mode,
ASan/UBSan and TSan** on Linux x86-64 with GCC 13.3.0. TSan uses no
suppressions. ASan leak detection is disabled; LSan is not claimed.
Two deliberate integration defects are independently rejected by the tests.
No Core, application or existing historical test was rebuilt or modified.

## Executed production scope

The runner extracts the entire `rpcs3::ios::texture_prehash` namespace from
the actual candidate `texture_cache.cpp`. Its worker, range-lock helper,
record/frame/epoch/stop lifecycle and hashing dispatch bodies remain unchanged.
The actual cancellation guard, result table, epoch listener, QoS header,
measurement counters and pinned xxHash are compiled.

Only the existing `hash_long_cancellable` predicate is observed: its two
architecture-selected lambda expressions call a harness function which can
pause at `processed == 65536`, then returns the **actual**
`cancellation.current()`. No condition, hash operation or production result is
substituted. This makes the interrupt occur after a real processed prefix,
without modifying the worker or the guest-range helper. The ordinary public
hash function remains unchanged. The observation pause is disabled for the
completed-hash cases.

VM/thread adapters are the exact slice from `rpcs3_prehash581.inc`, from its
first standard include to the first iOS header. Its old tests are neither
included nor executed. The adapter reserves real guest address space, maps
main/local ranges, models the original range-slot and exclusive-bit protocol,
and uses `mprotect(PROT_NONE)` during unmap. The full emulator VM is outside
this test's scope.

## Results

| Cases in each mode | Verified result |
|---|---|
| Entry guard group: disabled, passed position, exclusive VM operation, absent main-memory lock, stale epoch | Five rejections; zero processed bytes; output and lock unchanged |
| Direct main-memory helper interrupted by an epoch change | False return; exact 65,536-byte processed prefix; output sentinel unchanged; range lock released |
| Four complete helper cases: main/local memory, hybrid/fallback | All match independent `XXH3_64bits_withSeed` reference, including a 33-byte tail beyond 1 MiB; full length recorded |
| Eight worker cases: epoch/position/disable/stop × main/local memory | Each accounts for 65,536 bytes, one skip, zero completed hashes, no result-table publication, and nonzero measurement ticks |
| Two worker cases: concurrent unmap with epoch change or stop | Unmap remains blocked while the range is held, completes after cancellation, then remaps with verified replacement content; no lock/reservation remains |
| Three complete worker cases: main/local hybrid and main fallback | The published result matches the reference; exactly one full completed hash, zero skips, and full range length recorded |

There are 19 result rows per mode; the first row contains five entry checks.
The ten interrupted worker cases process 64 KiB of a planned 1 MiB range in
the controlled schedule. This is a logical prefix count, **not measured memory
traffic, bandwidth, iPhone time or FPS**. The pauses intentionally affect
elapsed ticks, which are tested only for being accounted on cancellation.

The stop cases exercise the actual `stop()` from a separate thread while the
worker is hashing. They verify that `stop()` joins the worker and releases its
reserved VM slot. The epoch cases use the actual epoch listener and an empty
frame transition to prevent a second prediction batch from obscuring the first
cancellation. The position cases advance through the actual `record()`.

## Negative controls

- `mutation-publish.json`: replacing the worker's incomplete-result branch
  with a false condition is rejected at `tp::worker_hashes.load() == 0`.
- `mutation-lock.json`: removing the final range-lock release is rejected at
  `slot->load() == 0` in the direct cancellation case.

Both mutations exist only in generated test copies. Their recorded nonzero
program exits are expected failures, not successful production runs.

## Frozen inputs

| Input | SHA-256 |
|---|---|
| `texture_cache.cpp` | `85c75155f09f2ffd0554fadfbaf9987510173323e008ad09edb70cd6809707ed` |
| `IOSTextureHash.cpp` | `b01ceabbed2f50f5a044f1c277f5bd561433c4220f40bcb0ffb3731245b5c6dc` |
| `IOSTextureHash.h` | `f7fdff357f542f69a08860716f17e6057b582097be378cb87f6bc1bd6c691816` |
| `IOSTexturePrehash.h` | `4b615553f3e4684b76f6b4b6bc1b2aba502879a69bf6053972ae053db194e235` |
| xxHash dependency | `4eeb0db9470a10e82a820ab504d99b8aafe46077582239479b897009ea243f7c` |
| Exact VM adapter slice | `eaf6c5798a96b12e1389f2afb1141fec1e008f9935e321cde077c65e4d2ad46b` |
| New test template | `4a3bc57f9be6b37cd3ecc830abf5999407957ac5b41a334f17941646451a2c76` |

The JSON results also retain full support-file and extracted-function hashes,
compiler flags, generated harness identity and source stability checks. All
three ordinary/sanitized runs use identical production and harness inputs.
The previous publication-only tests are not repeated here.

## Reproduction

From `/workspace/scratch/82df14a3df84`:

```sh
python3 device597-prehash-review/worker/run_worker_cancellation.py \
  --source device597-core-memory \
  --dependencies device597-upstream \
  --vm-adapter ipa597-verify-src/test/native/rpcs3_prehash581.inc \
  --work device597-prehash-review/worker/repro-work \
  --report device597-prehash-review/worker/repro.json \
  --expect-report device597-prehash-review/worker/worker-plain.json
```

Add `--sanitizer address,undefined` or `--sanitizer thread` for the recorded
sanitizer modes. For a negative control, add
`--mutation publish-incomplete` or `--mutation retain-range-lock`; the runner
checks the specific expected assertion and preserves the failed program output.
The runner accepts `--compiler` and `HOST_MACOS_SDK`; only the recorded Linux
x86-64 execution is claimed.

Kernel equivalence across many sizes, page-boundary coverage and uncancelled
cost are separate results owned by the kernel review. These integration checks
do not replace that evidence or an Apple ARM64/iPhone measurement.
