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

The four other closed sets the S2Arm IPA meets carry the same identity-gated conditional in the files
(main's decision, 11 Nov; each diff its own commit "handoff to main"), so nothing is extended in memory
any more and their steps run unchanged:

| Closed set | Where it runs | With `S2Arm-native-identity.json` | Proof |
| --- | --- | --- | --- |
| `packages/dolphin_internal_bridge/ci/verify_ipa.py` `validate` | Dolphin packager, seal | helper joins the set (contract of the single-IPA validator), both frameworks required | `test/s2arm_dolphin_verify_ipa_test.py` |
| `build-utils/validate_rpcs3_ipa.py` `validate_helper_bundles` | structure | the same; every per-extension check applies to the helper | `test/s2arm_rpcs3_helpers_test.py` |
| `standard-delivery.yml` version check (`len(bundles) == 8`) | signed IPA | nine bundles, `S2ArmJITHelper.appex` among them; else the original assert | `test/s2arm_version_check_test.py` (the step's here-document executed) |
| `build-utils/verify_downloaded_delivery.py` bundle count | offline verification | nine bundles with the S2Arm extensions; else the original check | `test/s2arm_downloaded_delivery_test.py` (`verify()` run end to end) |

Each test shows, on a matrix of common cases, the same result as the common line's file (its git blob) and
as the current file with its S2Arm statements removed from the syntax tree (which is that blob); with the
identity, the S2Arm case accepted and its incomplete variants refused. The launcher lists them in
`NATIVE_CONDITIONALS` (inventory) and its tests check that none is patched in memory.

## Test line wiring (`.github/diagnostics/s2arm/`, generated `s2arm-delivery.yml`)

Producer contract (the upload step of `s2arm-engine.yml`): artifact `s2arm-engine-framework-<head sha>`
of a successful run on this branch, holding exactly `S2ArmEngine.framework.zip`, `NS2Pro.framework.zip`
(members `<Name>.framework/...`, no symbolic link, e.g. `ditto -c -k --norsrc --keepParent`), `licenses/`
(`license-sources.json` and the engine's licence and notice texts it lists, `docs/s2arm-legal-notices.md`) and
`s2arm-engine-identity.json` `{run, attempt, head_sha, s2arm_commit, patches: [{name, sha256}], files, licenses}`:
`files` gives exactly the two archives, `patches` every `build-utils/s2arm/engine/patches/*.patch` at
`head_sha` (basename, sorted), `s2arm_commit` the pin of `tools/s2arm_prototype/pin.json` there, `licenses`
the manifest's path, SHA-256 and the number of files of `licenses/`. Each framework: one Mach-O, an arm64 iOS
dylib with install name `@rpath/<Name>.framework/<Name>`, linking only the system and the other engine framework.

Manifest: `s2arm.engine = {workflow, run, zips}` (`make_manifest.py ... --engine-run RUN --engine-zip
S2ArmEngine.framework.zip=SHA --engine-zip NS2Pro.framework.zip=SHA`), plus three added images and the
S2Arm tests. Steps: `engine-download` (API: run, branch, workflow, success, commit in history, one
unexpired artifact, digest; files against manifest and producer commit) after the component runs; the
helper (configure, `pod install`, `check-pods`) after the probe key; `engine-embed` and `engine-check-app`
after the last embed step (`engine-embed` also places the engine's notices in `Legal/S2Arm`), then the legal
gate on the built application; `engine-check-ipa` after the signed-IPA checks; the Dolphin packager and the
version check are the common steps, unchanged. Every build of this workflow now carries the engine, and its host bridge with the
preparation library and the system data (`docs/s2arm-engine-bridge.md`, Delivery). `RewindBoxS2ArmProbe` is still
set: stopping it is not a one-line change (`set_probe_key.py` checks it at host, app and IPA) and the
MeloNX hook is still in this branch's tree.

Not verified here: Swift compilation, CocoaPods, Xcode, signing and any device run (CI and device only).
