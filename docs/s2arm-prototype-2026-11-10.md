# Switch 2 playlist (S2Arm) — feasibility prototype

**Status, 10 November 2026: step 1 (source reading) and step 2 (host proof in CI) done.
Nothing has run on an iPhone.** The sections on loading and on the JIT helper come from
reading the pinned sources; only the "Step 2" result is an executed check. Only the
prototype is approved; integration is not.

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

## Step 2 — host proof (passed)

Run `42920636820` attempt 1 on commit `ab4619be`, workflow `s2arm-prototype-host.yml`,
sources in `tools/s2arm_prototype/`. It runs in CI because the session container is x86-64
and may not build third-party source.

- **Rewrite**, ubuntu-24.04 and macos-15 (arm64): the pinned rewriter turns the synthetic
  module (`make_synth_nso.py`, no game content) into 9 redirected sites and 2 gates with
  0 gaps. Layout: `LOAD_BIAS 0x2000`, `TEXT_END 0x1000`, `KEY_PAGE_OFF 0x6000`,
  `PATCH_OFF 0xe000`. The five output files are byte-identical on both systems;
  `main.patched.bin` SHA-256 `e2341dfd1dc829f06eebbedace773624e8cb5e35faf22a815b32ed086cdc9698`.
- **Execution**, macOS arm64: `host_loader.c` follows steps 1–5 above and links S2Arm's
  unmodified `runtime/src/entry.S`. The module ran to its `cntpct` and `svc` gates; 15 of
  15 checks: `tpidr_el0` read and write through slot KTLS, `tpidrro_el0` through KTLR, x18
  through K18, the gate saw x0 = 0x77 and its results came back, one `brk` handled by SIGTRAP.
- **Negative controls**, each must not pass: KGATE slot empty (signal 11), KTLS reading the
  wrong slot (4 mismatches), key page empty (signal 11), no SIGTRAP handler (signal 5).

Limits: macOS seals the code with `mprotect`, which the iPhone JIT forbids; x18 and
`tpidrro_el0` behaviour, signal delivery and address space on iOS are not covered. Questions
A–F remain entirely open.

## Existing device evidence from RPCS3 (reported by the main session, 11 Nov)

Not measured by this prototype: the main session reports it from its private device logs
(iPhone of the maintainer, "iOS Version 27.0", beta 24A5380h for IPA 674) and from reading
the RPCS3 Core (`Utilities/JITIOS.cpp`, delta in `build-utils/rpcs3/embedded-core.patch`).

- The RPCS3 Core takes a hole by `vm_allocate(VM_FLAGS_FIXED)`, then **maps read-execute
  anonymous pages itself over it** (`mmap` with `MAP_FIXED`), and issues helper command 1 with
  that address for each 16 MiB chunk; the reply must equal the address. The writable alias is a
  `vm_remap` made after all commands 1 and before the detach.
- Logged on device: code arena at about 5.28 GiB (IPA 662), about 482 GiB (IPA 676), and in
  IPA 694 `universal_prepare_chunk … address=516469817344 … response=516469817344`,
  `writable_alias_result … kern_return_t=0`, then PS3 games running their code from it after
  the detach.
- Address census of IPA 674 (iOS 27 beta): a free 64 GiB hole at `0x7000000000`, task maximum
  `0x8000000000` (2^39), 538 MiB free below 64 GiB. The low window varies between launches:
  no fixed address may be assumed.
- One JIT transaction per process in RPCS3 as well.
- Nothing measured under iOS 26.

Consequence: questions A and B have a favourable precedent on iOS 27 beta for the
process-mapped placement. The probe now runs that placement first (`mapped*` steps); the
`vm_remap` placement (`fixed*`) and the single-arena placement (`arena*`) stay as
comparisons. Still specific to S2Arm and unobserved: two small code ranges around data
pages, the redirections and gates (D), a `brk` after the detach (E), memory (F).

## Step 3 — device probe (written, checked on the host, not yet in the app)

`packages/s2arm_probe` (diagnostic only; no S2Arm source, no game content). The module it
runs is the rewriter's output for the synthetic module, committed as generated data
(`S2ArmSynthModule.h`, SHA-256 of the image `e2341dfd…9698`, compared with the rewriter's
output in CI). Host check: run `42924925273`, commit `92f5007`: with a stand-in for the JIT
helper on macOS arm64 both placements ran the module (16/16 checks each), and the three
sources compile for iOS arm64 with `-Werror`. Run `42925954171`, commit `c70f229`, repeats this
with the committed header compared byte for byte and the window released after phase 2.
This checks the probe's logic only.

### Hook specification for the MeloNX bridge (owner: session 01)

- **Lookup, no link dependency:** `NSClassFromString(@"S2ArmProbePlugin")`, then
  `+attachedFunction` and `+detachedFunction` return the two C functions declared in
  `packages/s2arm_probe/ios/Classes/S2ArmProbe.h`. Class absent: one journal line, nothing else.
- **Trigger:** the Info.plist boolean `RewindBoxS2ArmProbe`, set only in a test IPA (hook
  `d32738b5`, now in `Claude`, inert without the key). `RewindBoxS2ArmProbeMapped` is no longer
  needed: the process-mapped placement always runs.
- **Phase 1** `rb_s2arm_probe_attached(prepare, log, flags)`: after
  `MeloNXJitConfirmCoreLoadHandoff`, before `runtime.prepareJit()`. `prepare(address, length)`
  issues helper command 1 and returns x0. Calls made: `(0, 0x8000)` and `(0, 0x14000)`; with the
  flag, also two calls with a chosen address and 0x4000. It executes no `brk` of its own.
- **Phase 2** `rb_s2arm_probe_detached(log)`: after `MeloNXJitWaitForDetach` succeeded and before
  any guest thread exists; call it whenever phase 1 returned 0 or more.
- **Journal:** `log(step, status, detail)` must be durable when it returns, under a recognisable
  prefix such as `s2armProbe.<step>`: the next step may end the process.
- **Signals:** around risky accesses the probe installs SIGSEGV/SIGBUS/SIGILL handlers and
  restores the previous ones. In phase 2 its SIGTRAP handler advances one exact address (the
  module's own `brk #0x123`), passes anything else to the previous handler, and is removed
  after the run. It never skips a JIT helper `brk`.
- **Memory and address space:** 0x1C000 bytes of helper-prepared memory (kept), up to 64 GiB
  reserved without access below 2^39 and released at the end of phase 2.
- **Outcome:** the probe's result never fails the launch; the game then starts as usual.

### What the journal must show

| Question | Journal steps |
| --- | --- |
| A window below 2^39 | `holes` (largest hole), `window` (size obtained) |
| B code at a chosen address, mapped by the process | `mappedData`, `mappedCode`, `mappedAlias`, `mappedExecuteText`, `mappedExecutePatch` |
| B same, helper-allocated then remapped | `helperRegion`, `fixedAlias`, `fixedExecuteText`, `fixedExecutePatch` |
| B fallback, one region with data inside | `arenaRegion`, `arenaDataProtect` or `arenaDataOverlay`, `arenaExecuteText/Patch` |
| C write after detach | `mappedWrite` / `fixedWrite` / `arenaWrite`, `lateAlias`, `lateAliasExecute` |
| D redirections and gates | `mappedSlots`, `mappedRun` with `checks=16/16` (same for `fixed`, `arena`) |
| E `brk` after detach | `brk=1` in `mappedRun` / `fixedRun` / `arenaRun` |
| F memory | `footprint` in `phase1` and `phase2` lines |

A step with `begin` and no result is the step that ended the process.

## Step 3 — first device run (IPA 801, 11 Nov, observed)

Input: IPA 801 (SHA-256 `0b277b25…a6ab`, receipt `docs/evidence/rewind801/`), installed by the
maintainer, one Switch game launched first; journal `MeloNX-launch.log` received in this session
(not committed: raw private journal). Session pid 52831, 09:27:40 UTC; MeloNX's own `jitProbe`
passed just before the hook, flags 0x0, footprint 480.9 MiB at phase 1.

| Step | Observed |
| --- | --- |
| `holes` | largest free range 62.74 GiB at `0x70506ec000`, 63.01 GiB free, nothing above 2^39 |
| `window` | 64 GiB refused (`Cannot allocate memory`), 32 GiB reserved at `0x7080000000` |
| `mapped*` | process `mmap` R\|X at the chosen address + command 1 on that address: prepared, for text and patch; `vm_remap` alias RW (cur=5 max=7); code written through the alias and executed at the chosen address, both pages: `signal=0 value=0x4d4c` |
| `arena*` | helper region (command 1, address 0) at `0x142bac000`; alias, execute, `vm_protect` RW of data pages inside it, execute again: all passed |
| `fixed*` | data pages, helper region, its own execution: passed; `vm_remap` onto the chosen address with RX (kr=0): passed; **`fixedExecuteText` begin with no result**: the launch hung there and the maintainer closed the app |

What this answers (device, iOS 26+, universal helper attached; not yet after detach):
- **A/B (placement):** a 2 MiB-aligned slot at a chosen address below 2^39 can hold executable
  code through the RPCS3-style path (process maps R|X, helper prepares it, writable alias). This
  is the placement S2Arm's loader needs. The arena placement also works.
- **Fixed placement:** helper pages mapped again elsewhere are not usable: their first execution
  does not return. Most likely a fault taken under the attached debugger, which the helper does
  not hand back as a signal (inference from the hang; no crash report was read).
- **Not answered yet:** everything of phase 2 (D redirections and gates, E `brk` after detach,
  F memory during the run), because the hang came first.

Fix: commit `7195731` (executes the fixed placement only with the opt-in flag
`RB_S2ARM_PROBE_FIXED_EXECUTE`; the bridge passes 0). Next: IPA 802 with that fix, same trial.
