# Source-extracted CPU regression harnesses

Keep the four Python files and seven C++ fixture files in the same directory. The scripts accept RPCS3 **source roots**, containing `rpcs3/Emu/...`; neither the baseline nor candidate path is implicit.

```sh
python3 run_dma_list_test.py --baseline /path/to/before --source /path/to/after --output /path/to/results
python3 run_vm_mmio_test.py --baseline /path/to/before --source /path/to/after --output /path/to/results --sanitize
python3 run_dma_mmio_test.py --baseline /path/to/before --source /path/to/after --output /path/to/results --compiler clang++ --sanitize
```

Use `--generate-only` when the relevant production bodies have already been verified. It writes the generated C++ and a JSON report without compiling or executing. `--reference-result` additionally requires its SHA256 to match the generated program recorded by an earlier execution:

```sh
python3 run_dma_mmio_test.py --baseline /path/to/before --source /path/to/after --output /path/to/generated --generate-only --reference-result /path/to/earlier/dma-mmio-asan-ubsan-result.json
```

`--compiler` defaults to `CXX`, or `g++` when unset. `--report` selects an exact JSON result path. `--timeout` sets the executable timeout (120 seconds by default). A generated-only report has `executed: false`, so it cannot be mistaken for a fresh test run. A reference mismatch exits with status 1; a timeout is recorded separately and exits 124.

Required input files:

- List and DMA harnesses: `rpcs3/Emu/Cell/SPUThread.cpp` in both source roots.
- VM harness: `rpcs3/Emu/Memory/vm.cpp` and `vm_locking.h` in both source roots.

## Scope

The list harness compiles the complete production list-transfer and queue-draining bodies. The VM harness compiles the complete fast/slow range-lock functions and lock sweep. The DMA harness compiles the complete `do_dma_transfer` body. Production control flow is retained; function/class/namespace identifiers are changed only to coexist before and after versions in one program.

The C++ fixtures model bounded memory, channels, locks, atomics, scheduler callbacks and vector storage. They do not run an emulator, native ARM64 code or iOS vector-copy specialization. The DMA harness's 128-byte atomic helper models effective-address resolution and copying; the real helper's concurrency is not executed. VM lock behavior is separately checked by the complete production lock harness. Synthetic mappings do not model absent-thread hardware page faults. For the old zero-size RSX-element bug, a bounded adapter intercepts the copy after its initial 16-byte store and before the next 128-byte copy, proving the underflow path without performing a huge overwrite.

The portable scripts were verified by generation only: all three produced exactly the same C++ SHA256 as the already-passing normal and ASan/UBSan runs. No unchanged binary was rebuilt or re-executed for the portability change. The copied source roots must be genuinely different before/after states; pointing `--baseline` at an already-integrated tree is detected by `--reference-result`.

These are host behavioral regression checks. They establish no FPS gain, device memory reduction or resolution of any reported game scene.
