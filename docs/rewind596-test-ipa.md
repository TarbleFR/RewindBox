# RewindBox private IPA596 — compiled and independently verified

The maintainer requested a new IPA containing the latest compiled RPCS3 and MeloNX cores. **RewindBox 0.0.8 (596)** was built once, completed successfully, downloaded, decrypted, and independently checked against its source checkout and the original core artifacts. The verified IPA has been saved privately and made available to the maintainer. No public release or tag was created.

The delivery job completed on **29 October 2026 at 23:00:06 UTC** (**30 October, 00:00:06 Europe/Paris**). Build596 must not be reused for another candidate.

## Exact delivery

| Item | Verified value |
| --- | --- |
| Source | `d5c5f107f7b514980033d1b95218aa9d2f640609` on `Claude` |
| Source tree | `1e50d20224dc1461d0e15b2530736688d1039cfa` |
| Workflow | `.github/workflows/rewind596-baseline-delivery.yml` |
| Successful run / job | [40968162236](https://github.com/TarbleFR/RewindBox/actions/runs/40968162236) / `123777850588`, attempt 1 |
| Private IPA | `RewindBox-Build596.ipa` |
| IPA bytes | `188327690` |
| IPA SHA256 | `b8d665ab4503fc4f3492b80bb46ed582dcfed71e99982f82a8c2a8a04a842d07` |
| Encrypted artifact | `12939403565`, `188885533` bytes |
| Encrypted artifact SHA256 | `3e990b63f051d42b028f1688c6982a7756f9b5676ac88feeb59bc9ac69308ce3` |
| Target | iPhone ARM64; package minimum iOS18.0; SideStore re-signing required |

The encrypted artifact digest was authenticated before decryption. The actual IPA agrees with the delivered checksum and signed-payload receipt. The archive contains **5,350 members**, with valid CRCs and no duplicate entries. The main application and all seven extensions declare **0.0.8 (596)**.

## Components actually embedded

| Component | Source and producer | Original binary SHA256 |
| --- | --- | --- |
| RPCS3 | `e97137b1d907b4c0b0c102435d55b1f96d891d38`; [run 40963062736](https://github.com/TarbleFR/RewindBox/actions/runs/40963062736); artifact 12937551950 | `9b0af4f1bae9daa3b0da1641682ef72e37b9cbe703ab4af8d9ca94a80c63d192` |
| MeloNX Core 87 | `07f350480ab53b15d50953fb854dd8e3fc4e8d6c`; [run 40949501203](https://github.com/TarbleFR/RewindBox/actions/runs/40949501203); artifact 12931177865 | `834a64d617b178112b25eeb7dc02e80316959a2509120f9ffa78d8b9d1ee3840` |

Neither core was rebuilt for packaging. Both actual signed payloads were compared with their authenticated original binaries. RPCS3 retains ABI30 and 88 defined exports. MeloNX retains ABI2 and all 47 required exports; its permitted install-name rewrite is accounted for explicitly.

RPCS3 includes both source lots `543996ad1e79330fda81d086af27566dce0fd79e` and `a363d92332657196fb3b6085a98c62e119310bcc`, followed by the deep-audit changes. Its canonical patch is `5ba1424bcd40afc96f3263e236d84ed643cb7aac15cbcd1fb513e85d24e27ec8`: 319 postimages, 92 core-build inputs and 1,888 validation inputs are bound to the successful producer. The proof covers 31 Apple modes: six executed in that successful run and 25 retained from their recorded partial failed runs. No native mode was replayed for this IPA.

The PPU codegen identity stays `a987639e9f838d1c`; the SPU identity is now `477a3fa442d27917`. Existing SPU caches can therefore require first-use compilation. The core changes cover SPU/MFC protocol handling, texture/view selection and invalidation, allocation and address lookup costs, shader formatting, JIT free ranges and lazy asynchronous GPU objects. Their inclusion does not establish a physical-device FPS or scene-fix result.

MeloNX Core 87 binds 102 adaptation inputs and 139 prepared source members. Its producer ran 15 new Apple gates, retained 14 unchanged Core 85 gates and completed two real NativeAOT sessions on an ARM64 iOS simulator with guest execution and teardown evidence. The fifteen continuation adapters affect 22 engine files, covering pipeline keys and vertex state, renderer queries and bindings, buffer snapshots/readback, barrier batching, descriptors, overlap lookup and allocator interval updates. Those producer tests were authenticated and reused during packaging.

## Application and baseline preservation

The baseline is the delivered private IPA595 from source `d2e5029f8d7ca33eec279546d64a7f908285e804`, run 40928805790, IPA SHA256 `cfc1079249e4168349896a69f34a150ddbc68e318aafbb954a06cb019b00374e`.

The reviewed `lib`, `packages`, `assets`, `pubspec.yaml` and `pubspec.lock` roots remain identical to 595. The only product-source delta is `native/neoswap-storage/Store.cpp`, SHA256 `a812b0834df8c7301d59ac780b84a4ecc7c306b7b55f7ab02178e5705dca8571`. The workflow checked byte equality with the CocoaPods source and its Xcode sources entry before compiling the application. This includes the latest host-side NeoSwap change; the delivery is not merely a binary swap in an older IPA.

The nine immutable component pins were checked before compilation. Dolphin, ARMSX2, libretro, native MeloNX dependencies and the existing StikJIT interfaces were reused. The StikJIT compilation step was skipped after a verified cache hit. Historical product recipes and unchanged native tests were not replayed. Existing compatibility identifiers and licensing notices were preserved.

## Verification scope

Apple CI verified **88 ad hoc signing targets**. Independent inspection of the downloaded IPA found **88 Mach-O images**: 85 thin ARM64 images and 3 containers each holding a single ARM64 slice.

For the 85 thin images, compiled code/data and ABI fingerprints match the Apple signing receipt. The three containers are `App.framework/App`, `objective_c.framework/objective_c` and `sqlite3.framework/sqlite3`; they have verified structure and post-signing fingerprints, and are bound by the whole-IPA SHA256. **No before/after-signing fingerprint comparison is claimed for those three containers.** Cryptographic signature verification comes from the Apple CI evidence; the independent Linux pass did not run Apple `codesign`.

The independent pass also rechecked exact source inputs, both core payloads, the NeoSwap host receipt, all eight bundle versions, archive integrity and the final structural report. It compiled no engine, executed no native binary and modified no source checkout. The full scope and hashes are recorded in `docs/evidence/rewind596-delivery.json`.

## Observed duration

| Measurement | Duration |
| --- | --- |
| Workflow creation to completion | 924 seconds — 15m24s |
| macOS job | 915 seconds — 15m15s |
| Xcode Release application build, measured phase | 353.823 seconds |
| Package application and run structural checks, GitHub step | 104 seconds |
| Flutter setup, GitHub step | 76 seconds |
| Configure release host, GitHub step | 61 seconds |
| Signing and IPA export, measured phase | 52.201 seconds |

The job took 102 seconds less than the recorded595 job (1,017 seconds). These are observed build times, not an emulator performance measurement. Only one application compilation was required for 596; the whole job remained below the maintainer's 40-minute target.

## Remaining device validation and delivery status

Installation and gameplay on the maintainer's iPhone have not been tested here. SideStore must apply the user's Apple signing and provisioning. No improved iPhone FPS, fixed GOW3 freeze, corrected BO2 weapon rendering, fixed Assassin's Creed torch flicker, or Hogwarts memory gain is claimed from compilation or simulator evidence.

The verified IPA has been saved privately and handed to the maintainer. The ephemeral recipient private key was deleted after saving succeeded. No private download location or access material is included in this public receipt. The next build must use a new number; documentation-only receipts do not require another compilation.
