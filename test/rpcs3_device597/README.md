# Device597 follow-up tests

This directory contains only the new source-scoped regressions. It does not
build RPCS3 or run a game. Native evidence currently records Linux x86-64;
Apple ARM64 execution and iPhone validation remain separate gates.

The canonical source is materialized by the existing
`build-utils/materialize_rpcs3_core.py` on the pinned upstream checkout.
`test/rpcs3_device597_contract_test.py` authenticates the canonical patch,
all postimages, repository inputs and the byte-preserving inverse delta. Its
`--baseline-out` option reconstructs the immediate delivered597 source for
before/after tests. The destination must be absent or empty. Submodules are
kept separately by links, without fetching or mutating their contents.

```sh
python3 test/rpcs3_device597_contract_test.py /path/to/candidate \
  --repo . --report /tmp/device597-contract.json \
  --baseline-out /tmp/device597-baseline
```

The exact future Apple commands and expected JSON results are declared in
`build-utils/rpcs3/canonical-source.json`, under
`device597_20261030.apple_validation.jobs`. There are 28 native jobs, in
plain and ASan/UBSan modes, and one source-only codegen audit. The established
runtime592 workflow selects the new gate; this declaration is not evidence
that the Apple jobs ran. No release or workflow is launched by these scripts.

The native runners use `CXX` or an explicit `--compiler`, retain assertions
with `-UNDEBUG`, and accept `HOST_MACOS_SDK` where needed. The gate observes
the actual compiler invocations without changing their flags. The host log
runner is `test/rpcs3_causes_history_test.py`; it must execute the real
Objective-C++ Foundation fixture on Apple. Linux admission tests alone do
not satisfy that job.

| Directory | Production scope |
| --- | --- |
| `cpu` | Late-SNR full MFC queue race, bounded signal history, real acquire/release/DMA/list hooks; source codegen audit |
| `renderer` | Actual vertex upload range, sampler shader state refresh, bounded render contexts |
| `prehash` | Actual before/after publication and lookup headers |
| `hash` | Unchanged foreground hash versus cancellable speculative kernel |
| `worker` | Actual worker/range-lock integration with deterministic scheduling observation |
| `frame` | Actual bounded frame header and extracted reporter bodies |
| `host/baseline` | Small immediate597 host logger/header fixtures for the new history test |
| `device` | Read-only parser of the uploaded597 logs; not a performance benchmark |

Each native report documents its adapters, input hashes, compiler and limits.
Historical receipts are preserved in
`docs/evidence/rpcs3-device597-20261030`; they are not silently relabeled
when a harness, source or platform changes. The main findings and device
protocol are in `docs/rpcs3-device597-2026-10-30.md`.
