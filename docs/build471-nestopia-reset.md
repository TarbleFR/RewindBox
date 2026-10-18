# Build 471 — Nestopia NTSC startup crash

## Evidence from the maintainer's Build 470

The supplied native termination and session journal share session
`C419A406-62F6-4088-AA4B-AE83C56D9B1F`, PID 49734. The game is 10-Yard Fight,
Nestopia 2.0.0 / 135dfa6, original NESThumbstick `2cb17f0364a285dd`, iPhone,
landscape edgeToEdge. Core startup ends at +0.148 s, before the first game
video callback. The recorded fatal signal is 11, code 2, address
`0x0000028dba521100`, PC `0x000000015e375cc8`.

The journal gives the Nestopia image base `0x15e330000` and UUID
`AB4FBC0A-FF62-367B-A96B-01480A9B8DAF`. The actual delivered Build 470 IPA
contains that exact UUID. PC minus base is **0x45cc8**, in
`Nes::Core::Video::Renderer::FilterNtsc::BlitType<unsigned int,32>`
(start 0x45c2c, offset +0x9c). The actual ARM64 instruction is
`ldr q5, [x4, #0xd0]`.

Disassembly establishes the first background lookup:

- Load `Filter::bgColor` from `this + 0x18` into w13.
- Shift the zero-extended value left by 10, the lookup-entry size.
- Add the lookup table and burst-phase offsets.
- Load from that computed background entry at 0x45cc8.

This is a CPU access in Nestopia before NeoStation receives its first frame.
The concurrently running PDF decode is not a stack location in this fault.
Neither Metal nor the valid 602-pixel output width is identified as its cause.

The video is a distinct launch: it shows Adventures of Lolo returning to the
home screen before gameplay. Its recording time is later than the supplied
10-Yard Fight journal. Do not present these as the same session. The two other
text logs are duplicate older Beetle PSX sessions, dated 21:25 UTC, without
this native fault; this Nestopia finding does not diagnose their termination.

## The defect and the targeted correction

The pinned Nestopia source is
[135dfa6dfda5e7603d61e751b9ddd0cc42546bc3](https://github.com/libretro/nestopia/tree/135dfa6dfda5e7603d61e751b9ddd0cc42546bc3).
`Ppu::Output::Output` initializes `pixels` but not `bgColor`. `Ppu::Reset`
initializes the power-up palette but also leaves `output.bgColor` untouched.
That field is otherwise assigned only by palette writes and state loading.
A game can reach its first video output before writing its palette.
`Machine::Execute` copies the uninitialized value into the renderer, which
uses it as an unchecked NTSC lookup-table index.

The correction adds exactly one executable source line to `Ppu::Reset`:

```cpp
output.bgColor = palette.ram[0] & uint(Palette::COLOR);
```

This derives the background from the actual current palette for both hard
and soft reset. It does not replace valid image sizes, disable the NTSC
filter, alter the skin, delay launch, change cheats, or reset preferences.
The Build 470 menu/catalogue retention correction is retained; it was a
separate demonstrated defect, not a sufficient fix for this startup fault.

Canonical patch and pinned original/corrected source identities are in
`native/nestopia/reset-background.patch` and `native/nestopia/source.json`.
The core build compiles the same upstream revision with that one-line change,
retains GPL attribution, replaces Nestopia alone and checks every other file
against the previously delivered 34-core collection. All other 33 cores,
MoltenVK and system assets remain byte-identical.

## Reproduction and validation

Local Linux reproduction compiled the original upstream core and used the
same original NES program (SEI; JMP, no palette writes), actual libretro API,
composite filter and 120 frames including reset. With default allocation it
passed. With `MALLOC_PERTURB_=85` it failed before the first frame with signal
11 in the same NTSC blitter, source `NstVideoFilterNtsc.cpp:60`. Applying only
the line above removed that failure. Composite, S-Video, RGB, monochrome and
disabled filter each passed 120 frames and reset with the nonzero heap.

This explains why ordinary simulator repetitions could miss the defect:
the field can accidentally contain a valid small value. Skin allocations
may change the reused heap contents, but their causal contribution to this
particular run is not measured. The bug itself does not require a skin.

The focused iOS CI additionally tests the actual old shipping ARM64 binary,
retargeting only its platform declaration/signature for Simulator, with explicit pre-construction C++ allocation poisoning. It requires the exact original device fault offset
0x45cc8 before accepting the negative reproduction. The corrected iOS core
must pass all five video modes, crop to 224 rows, real frame delivery and
reset. A separate six-session integration uses unchanged production UIKit,
Metal, input and session sources, the original NESThumbstick, native controls,
live skin/layout transitions and deterministic nonzero C++ allocations. The actual results and delivery identity are recorded below.

The core witness step in run **39081741396**, source
`a518034e826258b1e2aa20f7abddb00d750411b4`, has passed: original ARM64
crash at exactly **0x45cc8**, then all five corrected modes, 120 frames
including reset each (**600 frames**). Actual nonzero C++ allocation counts
are required in every process. The separate six-session integration also passed, with eight logged
poisoned allocations, zero failures, real 602×224 / 2408-byte-pitch frames
and completed Metal commands in every session. Four sessions use the original
skin and two native controls; two original NES programs include plain and ZIP
loading, live skin/layout changes and 17 passing owner-lifetime checks, including eight live skin/layout
changes under an additional 32 MiB load. Simulator runtime
execution lasted 91.9 seconds; physical-device validation remains false. The already compiled core comes from
`c3408821b2b9c47c6e31ae25b45c113aa9fd3f74`, with SHA-256
`1a04f99e5ae2c10aa5b3c75b002e212e894c2e7934cc46232deb50da62c0e16d`.

Archived earlier cold-start evidence already contains 602×224 frames. Those
successes did not rule out a background index left to the previous heap
contents. The new witness controls that condition explicitly.

No unchanged broad Dart, skin, memory-lifetime, shader, cheat, NeoSwap or
other-console tests are to be repeated. Build 470's successful evidence is
reused only after source/dependency identity checks. Its old Nestopia launch
counts are historical evidence, not execution of the corrected core.

### Retained preparation failures

Run 39080239166 compiled the core but its compatibility gate rejected the
linker's default minimum OS 26.2. The build recipe now explicitly passes iOS
18.0 to the linker as well as the compiler and checks the three-component
Mach-O version. No IPA was built from that rejected core, and no successful
unrelated validation was repeated.

Run 39080335074 passed the corrected iOS 18 core compilation and preservation
checks, but the probe did not compile: its Linux-only `ucontext.h` include
was visible on Apple. No probe application ran. The include is now restricted
to Linux; probe compilation precedes simulator boot. The compiled core is
retained before tests so a future harness failure cannot discard it. Neither
preparation run produced an IPA.

Run 39080789997 preserved the corrected core successfully. Its negative probe
then showed that merely requesting `MallocPreScribble=1` did not expose the
defect on that Simulator: the old core passed 120 frames. This is retained as
a failed reproduction, not a successful fix validation. The test executable
now fills only fresh C++ allocations called by Nestopia with 0xaa before their
constructors run, using dyld interposition. It verifies actual allocation
counts. It does not modify any core instruction or field after construction.
The identical preserved core is reused in subsequent tests; it is not rebuilt.

Run 39081338162 stopped before running the original game core: its allocation
count was zero. dyld explicitly skips executable images when collecting
interposition sections ([`RuntimeState::buildInterposingTables`](https://github.com/apple-oss-distributions/dyld/blob/main/dyld/DyldRuntimeState.cpp)); the probe
now puts its allocator instrumentation in a signed test dylib loaded at
startup. This instrumentation is excluded from the product build. The
precondition remains mandatory; an inactive allocator hook cannot pass.

## Changed files

- `native/nestopia/reset-background.patch`: the single runtime correction.
- `native/nestopia/source.json`: upstream and before/after source hashes.
- `.github/diagnostics/nestopia_bgcolor/{build.py,core_probe.c,app.m,probe.py,skin.py,poison.cpp}`: isolated core build, original/fixed executable reproduction and six-session integration.
- `.github/workflows/nestopia-bgcolor.yml`: targeted macOS/iOS regression and retained compiled artifact.
- `.github/diagnostics/nestopia_delivery.py`, `.github/diagnostics/nestopia_delivery_test.py`: source-closed reuse of successful 470 checks and requirement for the new core witness.
- `.github/workflows/retroarch-delivery.yml`: Build 471, corrected-core artifact pins, reuse of unchanged checks, no automatic broad rerun.
- `AGENTS.md`, this report: diagnosis, results, retained failures and delivery receipt.

No production UIKit, skin, touch, Metal, session, cheat or other-console source is modified in this cycle.

## Delivery gate

The latest successful private delivery was Build 470, run `39078262825`;
471 is the next number. The delivered corrected binary was compiled at source
`c3408821b2b9c47c6e31ae25b45c113aa9fd3f74` and reused unchanged by the
successful regression source `a518034e826258b1e2aa20f7abddb00d750411b4`,
run [39081741396](https://github.com/TarbleFR/neostation-ios/actions/runs/39081741396).
The successful run preserves the same core collection as artifact
`12120040068`; the proof artifact is `12119282825`, ZIP SHA-256
`d2ba83c34e4a555c894f577fdfb436cc88641e8e323f49de639cde8c8abb17b4`.
The delivery pipeline requires both this witness and the unchanged Build 470
app evidence; only four new delivery-guard tests execute. No warm benchmark
or public release is requested. The delivery completed successfully as recorded below.

## Verified private delivery

- Version **0.0.7 (471)**; source commit [`9429a1627a2f72dddc07a5fe3c4cda35cdbd7db9`](https://github.com/TarbleFR/neostation-ios/commit/9429a1627a2f72dddc07a5fe3c4cda35cdbd7db9).
- Run [39082560152](https://github.com/TarbleFR/neostation-ios/actions/runs/39082560152): `checks`, `native` and cold Release build succeeded; optional warm build skipped. Four new delivery-guard tests passed. All 107 unchanged NeoSwap native inputs and prior app/skin/cheat checks were reused, not rerun.
- Final file **NeoStation-Build471-9429a162.ipa**, **218,606,105 bytes**.
- Final IPA SHA-256: **8484d2003a35de7c4ddedc199f9be9c80d540222b3fe2ca3e21e09c0f123682c**.
- Encrypted artifact `12120055879`, ZIP SHA-256 `7a5ad1e997192aebfb71d527166294384b31b52b2c37e6630d9509ae47d7752f`, decrypted with the authorized 470 delivery recipient key. No key material is included in this report or the evidence bundle.
- Independent inspection of the decrypted IPA confirms the app and five extensions at 0.0.7 (471), 34 cores, source stamps, 76 sealed ARM64 code/data/ABI image fingerprints and the record of 79 successful CI ad hoc signature checks. Linux does not run Apple's `codesign`; the delivered bytes match the CI-sealed identity. SideStore applies the normal Apple re-signing/provisioning for installation.
- The packaged Nestopia UUID is **2321DDEC-E187-3AC6-80FD-C94C63C718C0**, iPhoneOS / minimum iOS 18.0.0. Its sealed-file SHA-256 is `47a017a4ce1bc8c1873a4279cde3e929767e8c5a8f409be6a618a7bf0ea2aeb0`; its code, data and ABI exactly match the tested compiled core. The other 33 cores and MoltenVK retain the delivered 470 code/data/ABI fingerprints. The test allocator dylib is absent from the IPA.
- Windows copy verified through Desktop Commander: `C:\Users\Coren\Downloads\NeoStation-Build471-9429a162.ipa`, identical bytes and SHA-256. Existing IPAs were preserved.

Only one Build 471 IPA was produced. The four retained preparation failures
above concern the core's minimum-OS build recipe and the regression harness;
none produced an IPA. The actual old/fixed core and six-session tests that
passed were not repeated. **Do not reuse build number 471.**

## Limits

No physical iPhone is connected to the execution environment. The maintainer's
actual device fault is symbolicated; the corrected core is not yet confirmed
on that iPhone. No commercial ROM is downloaded or included. The test program
is original and intentionally reaches video output without a palette write.
No system crash reports are requested. The original attachments are preserved.
No public GitHub release is authorized.
