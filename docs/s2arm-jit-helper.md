# S2Arm JIT helper and engine wiring (Switch 2 test line only)

Fifth JIT helper extension, agreed with main (11 Nov): a renamed copy of RPCS3's, with its own request
type, marker and bundle suffix. Nothing here is in the common IPA. Host-side code that launches the
helper and the engine's use of commands 1 and 0 are separate work (engine guest patches).

## Package `packages/s2arm_jit_helper`

Every file is the RPCS3 file below with only the replacements recorded, in order and with their
counts, in `packages/s2arm_jit_helper/copy-of-rpcs3.json` (checked by `test/s2arm_jit_helper_test.py`
against the source SHA-256 recorded there).

| S2Arm file | RPCS3 source |
| --- | --- |
| `ios/Classes/S2ArmJITRequestHandlerBase.swift` | `packages/rpcs3_jit_helper/ios/Classes/Rpcs3JITRequestHandlerBase.swift` |
| `ios/Classes/S2ArmHelperJournal.swift` | `.../Rpcs3HelperJournal.swift` |
| `ios/Resources/s2arm-universal.js` | `.../Resources/rpcs3-universal.js` |
| `ios/s2arm_jit_helper.podspec` | `.../rpcs3_jit_helper.podspec` |
| `extension/S2ArmJITExtensionEntry.swift`, `extension/Info.plist` | `native/rpcs3_internal_helper/` (same names, Rpcs3) |

Renames: request type `com.neogamelab.neostation.s2arm-jit-request`; classes `S2ArmJITRequestHandlerBase`,
`S2ArmJITRequestHandler` (principal class), `S2ArmHelperReporter`, `S2ArmHelperError`, `S2ArmHelperJournal`;
queues `com.neogamelab.neostation.s2arm.jit-helper[-reporter]`; folders `tmp/NeoStationS2ArmJIT` and
`Library/NeoStationS2ArmStikJIT`; resource `s2arm-universal.js`; Info.plist marker `NeoStationS2ArmJITHelper`
and display name `RewindBox S2Arm JIT Helper`; pod and module `s2arm_jit_helper`; script and journal markers
`NEOSTATION_S2ARM_STIKJIT_UNIVERSAL_V1`, `NEOSTATION_S2ARM_DEBUGGER_ATTACHED_V1` (the line the handler waits for
before `pid_attached`), `NEOSTATION_S2ARM_DEBUGGER_PROBE_V1`, journal `S2ARM_JOURNAL_BEGIN` and prefixes `S2ARM_`,
`NEOSTATION_S2ARM_PREPARE_`, `NEOSTATION_S2ARM_DEBUGGER_`; the comment on `requiresCoreHandshake` now names the
S2Arm host (handshake from iOS 26.0, main's answer). Unchanged: request fields (protocolVersion 1, probeNonce,
targetPID, port, token, pairingData, requiresCoreHandshake), reporter events (helper_connected, log,
pid_attached, complete), the injected `neostationProbeNonce`, StikJIT 1.9.0 calls, BRK #0xf00d commands
0 detach, 1 prepare region (x0 address or 0 to allocate, x1 length; no size limit in the script), 2 new
breakpoints, 3 probe (x0 = nonce, answered nonce + 1). The actual script runs under Node against a
deterministic debugserver in the test.

## Host: `build-utils/s2arm/configure_s2arm_ios.py`

The helper part of `configure_rpcs3_ios_v1.py` renamed (helper files, Podfile stanza `target 'S2ArmJITHelper'`
with pod `s2arm_jit_helper`, Xcode target `S2ArmJITHelper.appex`, bundle `com.neogamelab.neostation.s2armjithelper`,
embedded in Runner, StikJIT reference reused). Differences (`test/s2arm_configure_test.py` checks them):
- no host entitlement written: it requires the four that `configure_rpcs3_ios_v2.py` writes
  (`REQUIRED_RUNTIME_ENTITLEMENTS`, imported). S2Arm's own app requests only `increased-memory-limit`
  (`pack/app.entitlements` at the pin); the helper needs `get-task-allow`. None is missing;
- Runner's build settings are required, never written (the original sets its deployment target to 17.4,
  which would undo NeoPlay's 18.0 at this point of the workflow);
- the Podfile stanza is idempotent (the original adds its comment line again on every run);
- `check-pods` checks the CocoaPods integration after the `pod install` the workflow runs next.

## Validators

`build-utils/validate_single_ipa_distribution.py` (diff for main, 16 added lines): on the MeloNX model,
only when the application carries `S2Arm-native-identity.json`, `S2ArmJITHelper.appex` joins the closed
set and `S2ArmEngine.framework` and `NS2Pro.framework` are required. `test/s2arm_validator_test.py` shows
identical report bytes and refusals without the file (common line blob `c7d46cbb` and the syntax tree
without the S2Arm statements), and the helper contract with it.

Four other closed sets would refuse the S2Arm IPA; this line handles them in memory, test line only, and
main may prefer the same conditional in the files: `verify_ipa.validate` (Dolphin packager, seal) and
`validate_rpcs3_ipa.validate_helper_bundles` (structure), extended while they run on an application that
carries the identity (`EXTENSION_SETS`, refused if their shape changes, skipped once they name S2Arm);
the version count `len(bundles) == 8` of the workflow (declared step edit) and of
`build-utils/verify_downloaded_delivery.py` (`VERIFIER_EDITS`).

## Test line wiring (`.github/diagnostics/s2arm/`, generated `s2arm-delivery.yml`)

Producer contract (the upload step of `s2arm-engine.yml`): artifact `s2arm-engine-framework-<head sha>`
of a successful run on this branch, holding exactly `S2ArmEngine.framework.zip`, `NS2Pro.framework.zip`
(members `<Name>.framework/...`, no symbolic link, e.g. `ditto -c -k --norsrc --keepParent`) and
`s2arm-engine-identity.json` `{run, attempt, head_sha, s2arm_commit, patches: [{name, sha256}], files}`:
`files` gives exactly the two archives, `patches` every `build-utils/s2arm/engine/patches/*.patch` at
`head_sha` (basename, sorted), `s2arm_commit` the pin of `tools/s2arm_prototype/pin.json` there. Each
framework: one Mach-O, an arm64 iOS dylib with install name `@rpath/<Name>.framework/<Name>`, linking only
the system and the other engine framework.

Manifest: `s2arm.engine = {workflow, run, zips}` (`make_manifest.py ... --engine-run RUN --engine-zip
S2ArmEngine.framework.zip=SHA --engine-zip NS2Pro.framework.zip=SHA`), plus three added images and the
S2Arm tests. Steps: `engine-download` (API: run, branch, workflow, success, commit in history, one
unexpired artifact, digest; files against manifest and producer commit) after the component runs; the
helper (configure, `pod install`, `check-pods`) after the probe key; `engine-embed` and `engine-check-app`
after the last embed step; `dolphin-package` instead of the packager call; `engine-check-ipa` after the
signed-IPA checks. Every build of this workflow now carries the engine. `RewindBoxS2ArmProbe` is still
set: stopping it is not a one-line change (`set_probe_key.py` checks it at host, app and IPA) and the
MeloNX hook is still in this branch's tree.

Not verified here: Swift compilation, CocoaPods, Xcode, signing and any device run (CI and device only).
