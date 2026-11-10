# RPCS3 continuation regression sources

This directory contains portable, source-extracted regression harnesses for the
continuation of `Claude` at `de8169848ecfa9c95946fc957861263a9fd1b879`.
The production Core remains the single delta in
`build-utils/rpcs3/embedded-core.patch`. `core-delta.patch` here is only the
review/test fixture from that prior canonical state to this lot; do not stack
it on top of the already updated canonical patch.

The complete explanation and limitations are in
[`docs/rpcs3-continuation-2026-10-30.md`](../../docs/rpcs3-continuation-2026-10-30.md).
Execution receipts are under
[`docs/evidence/rpcs3-continuation-20261030`](../../docs/evidence/rpcs3-continuation-20261030/).
The subdirectory READMEs retain their original local package terminology;
their `evidence/` and `results/` references map to the corresponding `cpu/`,
`renderer/` and `texture/` evidence directories there.

## Authenticate the integrated source without rebuilding

Use a materialized RPCS3 candidate tree for the `--source` argument:

```sh
python3 test/rpcs3_continuation_contract_test.py \
  --source /absolute/path/to/materialized-rpcs3 \
  --report /absolute/path/to/continuation-contract.json
```

This checks the canonical patch pin, every canonical postimage, the exact
changed-source inverse delta, the frozen repository/test/evidence inputs and
the existing PPU/SPU digest recipes. It reconstructs the affected baseline
files in a temporary directory and regenerates the CPU, renderer and texture
harnesses. Generated SHA256s must equal those of the successful recorded
executions. It does not invoke a compiler or native executable.

The unchanged external LLVM frame-lowering source was not materialized during
this review. Its recorded digest is disclosed as reused evidence. If the file
is present in the supplied tree, the contract hashes and verifies it normally.

## Native reproduction when an affected source changes

The runners take explicit source and output paths. Consult `--help` and the
adjacent README for the applicable scope. A C++20 compiler is required. These
are host regression harnesses, not a complete RPCS3 build or Vulkan driver test.
Their default native modes do not run when `--generate-only` is supplied.

| Area | Runner | Required source paths |
| --- | --- | --- |
| Deferred list/zero-byte DMA | `cpu/run_dma_list_test.py` | `--baseline`, `--source`, `--output` |
| VM range-lock MMIO | `cpu/run_vm_mmio_test.py` | `--baseline`, `--source`, `--output` |
| Full DMA dispatch | `cpu/run_dma_mmio_test.py` | `--baseline`, `--source`, `--output` |
| Shader invalidation | `renderer/test_pipeline_reload.py` | `--core`, `--output-dir`, `--label` |
| GPU chunk retirement | `renderer/test_gpu_wait_retirement.py` | `--core`, `--output-dir`, `--label` |
| DMA fence ownership/readback | `renderer/test_dma_wait_ownership.py` | `--baseline`, `--candidate`, `--support-core`, `--output-dir` |
| Retired image pressure/depth scale | `texture/verify_texture_lifetimes.py` | `--source`, `--report-dir` |
| Atlas clear coverage | `texture/verify_atlas_coverage.py` | `--baseline`, `--source`, `--report-dir` |
| Atlas wide arithmetic | `texture/verify_atlas_area.py` | `--baseline`, `--source`, `--report-dir` |

The DMA ownership runner executes both versions in one ASan/UBSan program.
Other runners expose `--sanitize`; the CPU runners additionally accept
`--reference-result` to check the generated program before compilation.
Keep the unchanged renderer fixtures adjacent to their runners.

NeoSwap's separate full Store and trim check is:

```sh
python3 test/neoswap_bulk_trim_test.py \
  --baseline-commit de8169848ecfa9c95946fc957861263a9fd1b879 \
  --compiler c++ --report /absolute/path/to/neoswap-plain.json
```

It requires LZ4 and zlib headers/libraries. For the sanitizer mode, add
`--sanitizer address,undefined`. The current evidence used a supplied LZ4
1.9.4 header and the host `liblz4.so.1`; those historical command arguments
are recorded rather than imposed on other platforms. Leak detection was
disabled in the recorded sanitizer runs.

Do not rerun native suites for documentation-only edits or a relocation of
these fixtures when the generated programs are byte-identical. Future source
changes require the affected semantic checks; matching a historical hash is
not a substitute for testing new behavior. This directory adds no runtime
telemetry and changes no CI workflow.
