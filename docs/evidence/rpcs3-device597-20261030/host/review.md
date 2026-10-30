# Compact RPCS3 causal history — integration candidate

This isolated copy changes one application source file:
`packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm`.
Its public header is unchanged. The copy is based on the unchanged logger in
`device597-work`; that working application's logger has not been edited here.

## Implemented behavior

`RPCS3-causes.log` holds up to 4 MiB, with one previous
`RPCS3-causes.1.log` generation. It uses the existing serial diagnostic queue
and bounded append implementation. No new queue, fsync or per-draw/per-poll
logging call is added. Exceptions in the new cause append are isolated so that
they cannot suppress the existing diagnostic write.

Admission retains the complete raw messages for `CONFIG_LAYERS`,
`JITPROF_BOOT`, `SAVESTATE_BOOT`, the existing restart marker,
`COREPROF FRAMEPROF527`, `FRAMECAUSE` and its `_EVENT`, `RENDERCAUSE` and its
`_EVENT`, `SIGNALCAUSE`, its `_EVENT` and `_PRODUCER`, `RSX_ACQUIRE`, complete
`FREEZE_DUMP snapshot` records, and `LOG_BUDGET`. Actual host
`game_boot_begin`/`game_boot_return` milestones are also mirrored once.
Other profiler families, `_DRAW`, `_POLL`, and verbose restore steps do not
enter the cause file. Producers remain responsible for their bounded event
budgets; this change adds no event producers.

Each cause record retains the original stage/message, PID/build, timestamp,
both monotonic capture anchors and their scope. It adds the known title,
session and boot kind. The title/session state belongs to the diagnostic
queue. A real new boot or new `CONFIG_LAYERS` clears the previous session and
boot kind; an unknown session is omitted rather than inherited. Thus a cause
record still identifies the title after the initial boot record rotates out.
The raw message is neither filtered by field name nor truncated.

Rotation markers are enabled for the new file, and its rotation count appears
in the timeline's existing loss summary. The shared append path includes a
marker only if marker plus record fits; a complete near-limit record takes
precedence over the optional marker.

The compact timeline adds only summary data:

- `frame_ms`: `total_interval_ms`, `window_guest_flips`, `wall_guest_fps`,
  `completed_interval_fps`, `last_guest_flip_age_ms` and the approximate
  progress-boundary flag.
- Existing frame summary: `wall_guest_fps`, `last_guest_flip_age_ms` and
  `avg_fps_scope`, while retaining the old `avg_fps` unchanged.
- `frame_cause`: captured/frames/slow/sampled/retained/unretained/contended,
  threshold and capacity.
- `render_cause`: captured/retained, vertex-range/sampler counters,
  dropped/contended.
- `signal_cause`: watch state, acquire/address/expected/observed, loss and
  stall counters, dump state, `coverage` **and** `excluded`.

Events and producer snapshots stay in the raw cause history. Their individual
fields are not folded into the timeline or incorrectly summed with other
families.

## Verified here

The exact new C++ admission functions are extracted and compiled by
`test/rpcs3_causes_history_test.py`. **85 cases pass both ordinary and
ASan/UBSan modes** on Linux x86-64/GCC 13.3.0. They cover all retained families,
log prefixes, token boundaries, unknown long raw fields, null input, and the
rejection of poll/draw/near-match tokens. The host source contract verifies
unchanged old runtime admission and public header, the original JSON capture
fields, bounded append wiring, no new queue/fsync, cause-write exception
isolation and summary-only timeline field lists.

`git -C device597-work apply --check
/workspace/scratch/82df14a3df84/app-log-review/causes-history.patch` succeeds.
This is a read-only application check; the patch was not applied there.
Previous prehash/publication/kernel tests were not rerun for this app change.

### Explicit remaining runtime check

**Foundation is unavailable on this Linux host. The Objective-C++ application
logger has not been compiled or executed here.**

The new `test/native/rpcs3_causes_history_test.mm` fixture is ready for actual
macOS Foundation. It checks full raw-message equality and capture anchors,
title/session identity, the distinct completed-interval/wall FPS fields,
summary-only timeline data, rejection of 400 poll/draw messages, a real
4 MiB rotation with one previous generation, reopening after export and a
new boot that cannot inherit the previous session. These are prepared checks,
not executed results. The runner automatically builds/runs this fixture on
Darwin; it reports an explicit Foundation skip on Linux.

No iOS execution, retention duration in gameplay, logging-time measurement,
rendering fix, freeze resolution or FPS change is claimed by this app work.

## Files and identities

| File/scope | SHA-256 |
|---|---|
| Baseline logger | `1bfbab2e7b07c78f17981f03aabb88f8c477b4ce44badf3275ab59bf6c202f98` |
| Candidate logger | `134862d8fd6ab9dd68ded1cb6b9c358890f7b9c1c1c27045cc19d61b31a322d8` |
| Portable runner | `883c509fa6ace799d568c090f7f222441466b437b8c8f4f5d3e9e8cedf4fde66` |
| Foundation fixture | `c6ad3e06ac56015031fad836c852895e26d480031bfa355b96a0ab063213da51` |
| Three-file patch | `f24a32766f498d4896b29d77bc14f5aff0f9fea7b71b8fd4222e64929f0fbb5a` |
| `causes-plain.json` | `eb0c51603189f1d99c3296da6eacd3499719b7ab6d372ecb230cacfa6787efe6` |
| `causes-asan.json` | `e26f19554e68256cef9d8e69b7f61bddbc1150d7d2876e78c66f652b2667bb5e` |

The patch contains the production logger and the two new test files. The
baseline copy, raw results and this review remain separate evidence.

## Reproduction

From `/workspace/scratch/82df14a3df84`:

```sh
python3 app-log-review/test/rpcs3_causes_history_test.py \
  --app app-log-review \
  --baseline app-log-review/baseline \
  --work app-log-review/repro-work \
  --report app-log-review/repro.json
```

Add `--sanitizer address,undefined` for the portable sanitizer case. When
integrating the test files into a repository, point `--app` to that checkout
and `--baseline` to the authenticated unchanged logger snapshot (for example
the matching `ipa597-verify-src` snapshot), rather than assuming its local
`baseline/` evidence directory exists in the repository.
