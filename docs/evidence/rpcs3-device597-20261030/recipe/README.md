# Device597: dedicated validator, historical recipe preserved

## Deliverable and scope

The isolated candidate is `.github/diagnostics/rpcs3runtime_device597_core.py`.
`dispatch-only.patch` adds one 12-line leading branch to the existing runtime592
dispatcher. The workflow and `build_rpcs3_embedded_core.sh` stay byte-identical.
The main application checkout was read only during this preparation.

The current catalogue contains 29 jobs: 28 native modes (14 families, each plain
and ASan/UBSan) and one separate compiler-free `audit_codegen` source job. Every
job must execute on the future Apple preflight. No new mode can reuse a result
from a different Core. This preparation did not start CI, compile a Core, run
Foundation or create a release.

## Call path

1. The unchanged workflow materializes the pinned source and calls
   `rpcs3runtime592_core.py --source SOURCE` using its existing LLVM22/macOS SDK.
2. The new leading manifest branch selects this validator before the retained
   `continuation_20261030` metadata can select its older validator.
3. `prepare` runs the exact source contract with `--repo`, authenticates all 319
   previous canonical postimages by inverse delta, checks the unchanged build
   recipe, authenticates historical artifacts under their original commit, and
   runs every new job. It writes the existing `runtime592-proof.json` filename.
4. The unchanged build shell passes that proof to the same dispatcher with
   `--verify-reuse`. Verification checks exact current source and input closure;
   it executes no native job. The build shell then compiles the Core once.
5. The unchanged workflow calls `--write-core-identity`. The new validator checks
   the actual Mach-O platform, ARM64, ABI30, 88 exports, MoltenVK hooks, optional
   configured diagnostic markers, and codegen identities from the real build log.

No workflow path trigger is added: the existing canonical patch and dispatcher
paths already trigger this recipe when an authorized future run is requested.

## What the new proof binds

The source contract binds the canonical patch, all 325 current postimages, the
inverse delta, the reconstructed baseline319 and the complete repository input
map. The new gate additionally binds itself, the exact leading dispatcher
branch, workflow, build shell, source contract record, runner catalogue,
codegen proof, historical receipt, and export/build validators.

For support files outside the canonical patch, every ordinary tracked upstream
file is checked against its original Git blob. The resulting SHA256 map includes
1,861 ordinary inputs in the current source, including `Utilities/xxhash3.h`,
`Utilities/Thread.h`, `rpcs3/Emu/Cell/MFC.h` and RSX types. Unexpected untracked
source files outside the canonical patch are rejected. The 28 submodule commit
pins are recorded separately; this gate does not claim to authenticate all
submodule contents. Those remain under the unchanged dependency recipe.

A local CXX wrapper observes the actual compiler selected by the workflow. It
forwards the arguments unchanged and retains source units plus an append-only
JSONL trace. Each native job needs at least one successful compilation, explicit
`-UNDEBUG`, no `NDEBUG` definition, and exactly its declared sanitizer mode.
Compiler queries, preprocessing, assembly-only and syntax-only invocations do
not satisfy the compile gate. The wrapper never participates in the Core build.

The two host jobs must compile the actual `Rpcs3Diagnostics.mm` and
`rpcs3_causes_history_test.mm` together with Foundation, and their result must
state that Foundation executed successfully. A successful Linux admission-only
test is rejected as Apple evidence.

The codegen source job is separate from the byte contract. Its fresh report must
match the reviewed report except for absolute input root paths, and must bind
the current SPUThread, compatibility alias, trace header, runner and historical
input evidence. Its exact PPU/SPU identities are reconciled with the compiled
Core log. The current reproduced identities are `a987639e9f838d1c` and
`477a3fa442d27917` respectively. No fresh LLVM object comparison is claimed.

Immediate reuse additionally requires the same application commit, patch,
canonical postimages, upstream support files, repository inputs, job argv,
report and trace hashes, captured compilation source hashes, execution modes,
and historical provenance. All new jobs remain mandatory.

## Historical results retain their original scope

The reference is Core597 from commit
`88cdc5e3e115a0b8587711d77147467baf38128b`, run `40981514937`.
The original Core/archive, identity, proof, native report, compile/output hashes
and original repository objects are checked without rewriting their provenance.

The 24 targeted historical modes retain their original split: 8 executed in
that final run and 16 carried from earlier partial runs. Each original proof
entry is retained, including any earlier reuse chain and the overall failure
status of an originating partial run. The additional 11 older modes also retain
their historical status. They are marked as not executed now and do not validate
new production paths or become new source-lot results.

### Closure audit of the previous continuation jobs

The old source record's 10 generators were run only with `--generate-only`.
Their original pre-continuation baseline was reconstructed by reversing the
old eight-file delta against delivered597. The complete reports and diffs are
under `historical-closure/`.

| Previous job | Current generated closure | Consequence |
| --- | --- | --- |
| vm-mmio | Identical | Historical generated bytes remain applicable to that same scope. |
| gpu-wait | Identical | Historical generated bytes remain applicable to that same scope. |
| dma-ownership | Identical | Historical generated bytes remain applicable to that same scope. |
| texture-lifetimes | Both pressure/depth programs identical | No new pressure/depth native run is introduced by this source lot. |
| texture-baseline | Both programs identical | The original negative baseline stays unchanged. |
| atlas | Identical | Original closure retained. |
| atlas-area | Identical | Original closure retained. |
| dma-list | Changed by two self-contained `RPCS3_IOS` insertions only | Removing the blocks excluded by its old non-iOS flags restores every historical program byte; the new signal jobs cover the added iOS path. |
| dma-mmio | Changed by four self-contained `RPCS3_IOS` insertions only | Same restricted conclusion; no claim that the old execution tested the new instrumentation. |
| pipeline | Changed by actual sampler refresh logic | Its old raw program hash cannot validate the new block. The new renderer sampler family executes the modified block. |

The exact CPU insertion proof is
`historical-closure/historical-cpu-excluded-block-proof.json`. The old runners
properly rejected the changed raw CPU program hashes before compilation. Their
failures were retained; they were not converted to passing native results.

## Local verification performed

`test_preflight_policy.py` passed 50 checks. They include valid job catalogues,
explicit flags and nested native results, and rejection of missing/duplicate
jobs, skipped Foundation, wrong compiler traces, disabled assertions, wrong
sanitizers, changed source snapshots, bypassed CXX, foreign source dependencies,
and altered codegen proof fields. The wrapper test invokes a recording stub to
verify argument forwarding; it invokes no compiler and claims no native pass.

The real locally retained historical Core archive, binary, identity, proof and
191 original repository input objects were authenticated. The larger historical
diagnostics archive was not available locally and was not opened in this check;
the future Apple preflight requires its full authentication.

A fresh compiler-free codegen audit against the final integrated source and an
authenticated reconstructed baseline passed. `git apply --check` accepted the
minimal dispatcher patch. The source gate itself still needs its final integrated
contract input map, which the parent integration owns. The full native Apple
preflight has not executed.

## Integration files

Copy the new validator and apply only `dispatch-only.patch`. Retain
`apple-validation.json` exactly in
`canonical-source.json.device597_20261030.apple_validation`; retain all runners,
fixtures, adapters, codegen evidence and the contract in its repository input map.
The workflow and shell recipe are intentionally not part of this diff.

Useful evidence files:

- `policy-evidence/result.json`: 50 compiler-free policy checks and explicit limits.
- `codegen-fresh-source.json`: current source audit, with no CMake/native execution.
- `policy-evidence/upstream-dependencies.json`: actual upstream support-file closure.
- `historical-closure/historical-closure-report.json`: all generated old closure comparisons.
- `historical-closure/historical-cpu-excluded-block-proof.json`: exact excluded CPU block proof.
- `delivery-manifest.json`: artifact hashes and immutable historical recipe hashes.
