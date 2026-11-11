# Switch 2 (S2Arm) — handoff for the trial IPA "B"

**For the integration owner. 11 November 2026.** IPA B = the common IPA A (same base, same
pins, same identifier) plus the S2Arm device probe. Built by the principal session with its
recipe; this session builds nothing. Maintainer's words are in the board entry.

## 1. What IPA B contains and activates

| Item | Value |
| --- | --- |
| Package to add | `packages/s2arm_probe` only (9 files: `ios/Classes/S2ArmProbe.c`, `.h`, `S2ArmProbeGate.S`, `S2ArmProbePlugin.h`, `.m`, `S2ArmSynthModule.h`, `ios/s2arm_probe.podspec`, `pubspec.yaml`, `lib/s2arm_probe.dart`) |
| Root `pubspec.yaml` | `- packages/s2arm_probe` in `workspace:`; dependency `s2arm_probe:` / `path: packages/s2arm_probe`. Workspace members are not in `pubspec.lock` in this repository (read, not executed) |
| Host Info.plist | `RewindBoxS2ArmProbe` = boolean true. **Do not** set `RewindBoxS2ArmProbeMapped`: the probe no longer reads that flag (the placement it used to gate always runs; it is the one RPCS3 uses) |
| Bridge hook | `d32738b5`, already in `Claude` (`MeloNXS2ArmProbeHook.m`), finds the class `S2ArmProbePlugin` by name |
| Not in this trial | `S2ArmPrepare.xcframework`, `native/s2arm/`, any S2Arm source, any playlist, skin or UI change. Nothing else of this branch is linked into the app |

The rest of the branch (`native/s2arm/`, `build-utils/s2arm/`, `tools/s2arm_prototype/`,
`.github/workflows/s2arm-*.yml`, `docs/s2arm-*.md`) is inert for the app. The three workflows
trigger only on `work/s2arm-switch2-prototype-20261110` or by hand, and use the protected
artifact upload (`check_workflows.py` passes on this commit).

## 2. What is proved, and where

| Claim | Evidence |
| --- | --- |
| Probe sources compile for iOS arm64, `-Wall -Wextra -Werror` | run `42948708967` (macos-15, Xcode 16.4), code commit `831c0c2` |
| Probe logic: three placements run the module, 16/16 checks each, with a stand-in for the JIT helper | same run, macOS arm64 |
| Module data = S2Arm rewriter output, byte-compared in CI | same run; S2Arm `6b6a5715` |
| Hook contract (lookup, phases, journal) | session 01's run `42933024817`, commit `d32738b5` |
| **Never done** | the pod inside an Xcode/Flutter app build; anything on an iPhone; the hook calling the real probe (it was tested with a fake class) |

## 3. Notices for what enters the binary

The probe is RewindBox code (repository licence). Its `S2ArmSynthModule.h` embeds, as data,
about 600 bytes of AArch64 produced by the S2Arm rewriter (Apache-2.0, commit
`6b6a571553f7a687af46e03e2cdbf8ef4d77f335`, https://github.com/jhaizhou-ops/S2Arm) from a
synthetic module written for the test. No S2Arm source, Capstone or LZ4 is linked.
Ready text: *"Diagnostic data generated with the S2Arm rewriter (Apache License 2.0,
Copyright 2026 S2Arm contributors, https://github.com/jhaizhou-ops/S2Arm)."* Fuller entries
for later components: [s2arm-legal-notices.md](s2arm-legal-notices.md).

## 4. What could break the standard recipe

- **Runner binary changes** (static pod linked into it): declare it among the images that
  must change. No new Mach-O image is expected (`static_framework = true`; read, not built).
- **Package list / plugin registrant:** `GeneratedPluginRegistrant` gains
  `S2ArmProbePlugin`; any contract that pins the plugin or package list needs the entry.
- **Info.plist key:** new key; validators that pin the key set need it declared.
- **Pod build never exercised:** `.S` file in a CocoaPods static framework, public headers
  `S2ArmProbePlugin.h` and `S2ArmProbe.h`, `registerWithRegistrar:` taking `id` (no Flutter
  import). A compile or link error here is possible and would be this session's to fix.
- **Size, signing:** a few kilobytes of code, no entitlement, no extension, no resource.
- **Native tests:** none added by this lot beyond session 01's hook test.

## 5. Trial protocol for the maintainer

Needs iOS 26 or later (the hook runs only with the universal JIT helper).
1. Install IPA B (it replaces the common app; data kept).
2. Open RewindBox and start one Switch game, first thing after opening the app.
3. Let it reach the game or close by itself, then send `MeloNX-launch.log`.

Journal lines are `[MeloNX:native]` JSON with `stage` = `s2armProbe.<step>`:
`hook` (phase1, phase1Done, phase2, phase2Done), `holes`, `window`, `mappedData`,
`mappedCode`, `mappedAlias`, `mappedExecuteText`, `mappedExecutePatch`, the same for `arena*`
and `fixed*`, then after the detach `mappedWrite`, `mappedSlots`, `mappedRun`
(`checks=16/16 brk=1 svc=1 cntpct=1`), `lateAlias`, `windowRelease`, `phase2`. A step with
`begin` and no result is the step that ended the process. What each answers:
[prototype document](s2arm-prototype-2026-11-10.md), "What the journal must show".

Effect while this IPA is installed: the probe runs at the first Switch launch of every app
session, before MeloNX prepares its JIT and after the helper detaches; its result never
changes the launch. Accepted risk: the app stops during that launch. IPA A has no probe.
