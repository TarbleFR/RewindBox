# Hogwarts launch after private602

The maintainer requests a corrected MeloNX Core, retaining all cumulative lots.
The new attachment SHA256 is
`6c9d1361e4dc7acbca5a4ee0ec184777deb4250ba93081de347e375bf15c28d5`.
Only its final Hogwarts session (PID55473) is in scope. Smash remains deferred.

Private602's helper fix works on the actual phone: selection16:28:17.391475Z,
1024MiB arena/probe passed16:28:21.330228Z, first Metal presentation
16:29:29.667106Z. The renderer initializes over59.998149s; the shader cache's
375 entries load over0.222s. No event isolates which pre-cache native call
accounts for the long interval. Cached main data104.40MiB and two recovered
worker snapshots do not by themselves establish corruption or a slow import.
No existing cache is purged, skipped or asynchronously mutated by this change.

After the last nonzero presentation sample at t87, presentation stalls. The
final record at16:30:27.145617Z is an unhandled InvalidMemoryRegionException
from NativePageTable.VirtualMemoryEvent, with no guest PC or instruction.
Peak sampled footprint3151MiB and minimum process headroom3504MiB do not prove
an out-of-memory cause. The 4GiB donor mapping is virtual capacity.

## Confirmed source defects

The pinned LightningJit RewriteLiteralMemoryInstruction gives every integer
literal an I64 operand. Assembler.LdrRiUn therefore emits LDR Xt for a guest
LDR Wt, reads eight instead of four bytes and imports the following four
bytes into the high half instead of zero-extending. It can corrupt values,
addresses or lengths used by subsequent guest instructions. The correction
selects I32 for the 32-bit LDR literal opcode; X and sign-extending LDRSW
retain I64 destinations. A second upstream test incorrectly treats SIMD31 as
the integer zero register and removes valid S/D/Q31 literal loads. The new
condition only elides ADR/ADRP to ZR, preserving vector31 and actual memory
reads to integer ZR, including their faults.

These are independently reproducible translator defects. The uploaded stack
does **not** identify its exact faulting guest instruction, so attribution of
this Hogwarts crash to either defect remains unproven until an on-device
test. Do not label code-generation checks or simulator homebrew as a Hogwarts
launch/gameplay/FPS result.

The guard keeps throwing; its diagnostic adds the relative offset, size and
read/write flag without logging contents or private pointers. Startup-only
timing scopes surround instance, surface, device selection/device creation,
main and worker cache imports, feature setup and swapchain creation. Scope
`scopeEnd` means elapsed interval, not initialization success. Tracing must never
replace a native exception, change the current launch stage, add a wait or change cache ownership.

## Build and validation scope

Base Core827f4653/run41028130487/artifact12964518860 is authenticated by its
actual ZIP, original source identities and live GitHub metadata. All114 old
preparation inputs remain byte-exact except the recipe that appends the two
new adapters. Three new inputs bring the count to117; all151 retained source
members remain present and the new inventory has154 members. Five production
paths differ: literal lowering, guard diagnostic, two startup call sites and
the new trace helper. Native dependencies, ABI2/47 required exports, sized-JIT
negotiation, memory budgets, graphics policy and all other core lots remain.

The Apple literal-lowering gate exercises the real production bodies with
the actual pinned ARM64 assembler. Its successful exact-input proof from
8a82bb25 is reused after the trace scope statuses are corrected to preserve
the launch stage. The affected startup-scope gate executes freshly. Thirty-five
unchanged historical receipts are authenticated without replay. NativeAOT
builds both iOS/simulator ARM64 libraries and runs two actual simulator guest
SVC/close/backing-release sessions. Final Apple run41097173966/job124205742820 succeeds from source
`1630bd0230c9431de92faec9c5e2662262b1ede6`. The downloaded87595452-byte
ZIP SHA256 is `7dd844774ff7991a406db8d37e35bba8f7b3b46284d1a8e05359b1d3ba135928`.
Independent verification passes CRC, both actual ARM64/platform images and
47 required exports among84 public definitions in each. iOS37618024 bytes,
SHA256 `423f2af029a5c1319d518a67114dc0b963ba5399747960cb6155b44014037ddc`;
simulator37928552 bytes, SHA256
`43d3a82ce66e19441190b120b5c3807f82f76659d275ab378c99888980a12a77`.
The corrected startup fixture passes8 checks; the exact reused literal fixture
passes12167 checks and reproduces620 wrong-width cases,60 missing vector31
loads and60 missing ZR reads. Two actual NativeAOT simulator guest SVC
sessions close and release their backing. All117 preparation inputs and154
prepared members match the final contract. No physical Hogwarts execution,
causal crash attribution, GPU-delay removal or FPS improvement is established.

The intermediate8a82bb25 run41094416545 is successful and supplies the
unchanged literal proof. The earlier c79325eb test wrapper lacked an import;
6273364d stopped before the new gate/native build on a GitHub502. Final
metadata reads retry transport failures without relaxing source/byte checks.
See `evidence/melonx-hogwarts-launch-20261030/independent-verification.json`
and the archived Apple reports. Do not rebuild the unchanged Core or replay
its successful native fixtures for closing documentation. No new application
IPA or public release is produced by this core-only request.

The verified ZIP is privately available as `MeloNX-Hogwarts-Core-1630bd02.zip`
(Library receipt `libfile_5fba122decdc81919339c251779ab10b`, version0).
