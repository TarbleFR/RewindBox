# Rejected sampler invalidation mask

The production sampler helper is unchanged. The candidate in this directory
was measured and withdrawn, rather than adding a conditional speedup with an
unmeasured net effect to the Core.

The candidate indexes published sampler ranges in one atomic bitmap, retaining
unknown/in-flight ranges and the original range/revision checks. Binding
publication preserves concurrent updates of independent slots. The exclusive
cache invalidator retires empty slots; unbinding keeps its original single
range store. A full-mask sequential fallback was also evaluated.

`result.json` is the final Linux x86-64/GCC 13.3 result, with 2,040,084
state/match checks and reader/writer publication interleavings. It is not an
ARM64, GPU or iPhone test; no sanitizer execution is claimed for this rejected
candidate.

The sparse case is favorable: four active, non-overlapping bindings take
12.1739 ns before and 4.5068 ns after. However, 20 active, non-overlapping
bindings take 12.0121 ns before and 24.1434 ns after. The mixed full-occupancy
cases also regress by approximately 3–13%, despite eliminating the additional
atomic unbind operation in the earlier experiment. Binding publication itself
increases from 1.08571 to 1.26351 ns; publication with unbinding increases
from 1.02288 to 1.32313 ns.

The iPhone logs do not measure binding occupancy. Sampler ranges remain
registered while their slots are temporarily unreferenced, so current shader
texture count cannot establish sparse occupancy. There is insufficient
evidence that the favorable case offsets the dense-case and publication costs.
This is a rejected optimization, not a new runtime option or an FPS claim.

Reproduce the preserved candidate against its exact previous helper:

```sh
python3 test/rpcs3_sampler_invalidation_active_test.py candidate --baseline baseline --benchmark --report replay.json
```

Run that command from this directory. The runner extracts both actual helper
bodies; only the enclosing cache reader/writer lock is adapted with
`std::shared_mutex`. Source, runner, adapter, generated program and compiler
identities are recorded. Timings from another host need not match.
