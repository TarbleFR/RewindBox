# Switch 2 playlist (S2Arm) — feasibility prototype

**Status, 10 November 2026: step 1 (source reading) done. Nothing from S2Arm has been
compiled or executed yet.** Every statement below comes from reading the pinned sources;
none is a host or device measurement. Only the prototype is approved; integration is not.

## Pinned inputs

| Input | Identity | Licence |
| --- | --- | --- |
| [S2Arm](https://github.com/jhaizhou-ops/S2Arm) | commit `6b6a571553f7a687af46e03e2cdbf8ef4d77f335` (10 Nov 2026) | Apache-2.0, `NOTICE` to keep |
| Capstone (PyPI sdist, C core) | 5.0.7, SHA-256 `796bdd69b05fa124fc2aa2e74b9a0b3d4c4e7f3e02add5e583cf2f3bca282ede` | BSD-3-Clause + LLVM release licence |
| LZ4 (python-lz4 sdist, `lz4libs/lz4.c`, LZ4 1.9.4) | 4.4.5, SHA-256 `5f0b9e53c1e82e88c10d7c180069363980136b9d7a8306c4dca4f760d60c39f0` | BSD-2-Clause |

The dependency hashes are the ones S2Arm pins itself (`runtime/rewriter/prepare_deps.py`,
`THIRD_PARTY.md`). No S2Arm source, game, key or protected content is in this repository.

## What loading a module without a per-game signature requires

The rewriter (`runtime/rewriter/rewriter.c`, entry `s2a_rewrite_files_with_options`, C11,
no subprocess, no environment read by the library) turns one NSO into `<name>.patched.bin`,
`<name>.fixups.tsv`, `<name>.gates.tsv`, `<name>.sites.tsv` and `<name>.gaps.tsv`.

S2Arm already loads that output from plain data files on macOS
(`runtime/src/loader.c`, the non-iPhone `map_image`). That path is the reference:

1. **Layout** from the `# KEY value` header of `fixups.tsv`: `PATCH_OFF`, `IMAGE_SIZE`,
   `FILE_IMAGE_LEN`, `LOAD_BIAS`, `TEXT_END`, `RO_OFF`, `DATA_OFF`, `KEY_PAGE_OFF`,
   `KEY_PAGE_SIZE` (0x4000), `KEY_{K18,KTLS,KTLR,KGATE}_IDX` (0–3), optional
   `PATCH2_OFF/LEN`, `TRAP_SITES`/`TRAP`, `FAR_JUMPS`/`FAR`. A `# TARGET` line means a
   non-Apple output and must be refused.
2. **Mapping**: anonymous read-write memory at the module slot (2 MiB aligned, inside the
   guest window), `patched.bin` copied in. Near layout: image then patch area after it;
   far layout (`PATCH_OFF < 0`): patch area before the base, bss and key page as zero pages.
3. **Key page**: four 64-bit thread-slot offsets (`pthread key × 8` on Apple) written at the
   given indexes, then the page made read-only.
4. **Sealing**: `[base − LOAD_BIAS, TEXT_END rounded to 16 KiB)` and the patch area(s) become
   read-execute; gaps are inaccessible. Code and data therefore alternate at fixed
   offsets inside one module span: text (RX), ro/data/bss/key page (R or RW), patch (RX).
5. **Redirections** (all through `tpidrro_el0`, the Apple thread-slot base, never through
   the host's x18 or `tpidr_el0`): guest x18 → slot K18, `tpidr_el0` → slot KTLS,
   `tpidrro_el0` → slot KTLR. `svc`, `cntpct`, `cntvct` become a branch to a patch block that
   loads the gate address from slot KGATE and calls it; `gates.tsv` maps each block's return
   address to its kind, argument and original address (`runtime/src/gate.c`,
   `sw_gate` in `runtime/src/entry.S`). Each guest thread needs the four slots set.
6. **Relocation** as an ELF module (`DT_RELA`, `DT_RELR`, `DT_JMPREL`), not needed for a
   synthetic position-independent module.

**`brk` is not part of the normal path.** The rewriter emits `brk #(0x8000 + n)` and
`brk #0xA000` only in dual-island mode, when a patch island is out of branch range
(`runtime/src/traps.c`); a game's own `brk` is left in place. Both reach a SIGTRAP handler.

## What the RewindBox JIT helper allows (read in this repository)

- `packages/melonx_jit_helper/ios/Resources/melonx-universal.js` is a debugserver script.
  Command 1 (`brk #0xf00d`, x16 = 1) prepares executable memory: the sized MeloNX arena
  (address chosen by debugserver), or — unused today — **a region at an address supplied by
  the process** (x0 = address, x1 = length).
- While the helper is attached, a `brk` whose immediate it does not know is logged and
  the process is continued at the same instruction. Guest code must therefore not run
  before the helper detaches. `MeloNXInternalBridgePlugin.swift` already waits for the
  detach before starting a game; after it, `CS_DEBUGGED` stays set and no debugger is attached.
- Under iOS 26 the arena is prepared once per process and “no later mapping is possible”
  (`build-utils/melonx/adapt_jit_arena.py`); preparation writes one byte in every 16 KiB
  page, so a prepared region is resident memory from the start.

## Consequences for the prototype

The Mac path cannot be reused as is on iPhone: step 4 (`mprotect` to RX after the copy) is
exactly what the JIT restriction forbids. The device prototype has to prove this instead:

| # | Question the device must answer | Why |
| --- | --- | --- |
| A | Largest free hole below 2^39 when the diagnostic runs (Flutter, MeloNX frameworks loaded) | S2Arm reserves its window in a constructor; RewindBox cannot |
| B | Can the helper prepare RX regions at addresses chosen inside that window, several of them, before it detaches | text and patch areas sit at fixed offsets around data |
| C | Can code be written after the detach through a `vm_remap` writable alias and run at the fixed address | on-device recompilation happens after JIT preparation |
| D | Does the rewritten synthetic module run to its first gate with the K18/KTLS/KTLR/KGATE slots | the redirections of step 5 |
| E | Does a `brk` in that module reach a SIGTRAP handler and resume after the detach | traps, far jumps, game `brk` |
| F | Resident memory added by the prepared regions | prepared pages are dirty, signed file pages were clean |

Known design constraint, whatever the answers: on iOS 26 every executable page must be
requested before the helper detaches, so the module layout (or one arena large enough)
must be known at JIT preparation, and a second game in the same process cannot get new
executable memory under the present helper policy.

## Step 2 — host proof

Feasible, **in CI only**: the session container is x86-64 without an AArch64 toolchain or
emulator, and building third-party source inside it is refused by the session's
permission policy. Planned jobs, on this branch only:

- Linux: build the pinned rewriter, rewrite a synthetic NSO written for this test (no game
  content: `svc`, `mrs`/`msr tpidr_el0`, `mrs tpidrro_el0`, x18 use, counter read, `brk`),
  check zero gaps and the expected sites and gates.
- macOS arm64: same build, byte comparison with the Linux output, then a small loader
  following steps 1–5 above with S2Arm's own `entry.S` gate, executing the module to its
  first gate. Negative controls must fail: KGATE slot left empty, wrong KTLS slot, key page
  not installed, `brk` handler not installed.

A macOS pass proves the format and the redirections, not the iPhone JIT questions A–F.
