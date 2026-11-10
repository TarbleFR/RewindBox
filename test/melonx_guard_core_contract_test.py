#!/usr/bin/env python3
"""Validate the exact reviewed change against the delivered Core1630 contract."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
c = json.loads((ROOT / 'build-utils/melonx/guard-core-contract.json').read_bytes())
prior = json.loads((ROOT / 'build-utils/melonx/hogwarts-launch-core-contract.json').read_bytes())
checks = 0


def check(value, message):
    global checks
    checks += 1
    assert value, message


check(c['schemaVersion'] == 1, 'Contract version')
check(c['baseline']['source'] == '1630bd0230c9431de92faec9c5e2662262b1ede6', 'Immediate successful baseline')
check(c['baselinePreparationInputs'] == prior['preparationInputs'], 'Keep exact117 baseline preparation inputs')
check(c['baselinePreparedMembers'] == prior['preparedMembers'], 'Keep exact154 baseline source members')
a, b = c['baselinePreparationInputs'], c['preparationInputs']
check(len(a) == 117 and len(b) == 120, 'Three new adapter inputs only')
check(set(a) <= set(b), 'No removed preparation input')
check({p for p in a if a[p] != b[p]} == {'build-utils/melonx/prepare_embedded.py'}, 'Only the existing recipe changes')
check(set(b) - set(a) == set(c['addedPreparationInputs']), 'Added adapter inventory')
check(c['adapters'] == ['adapt_vector_register_masks', 'adapt_guard_context', 'adapt_occlusion_completion'], 'Only reviewed new adapters')
check(set(c['addedPreparationInputs']) == {'build-utils/melonx/' + n + '.py' for n in c['adapters']}, 'Adapter/input mapping')
old, new = c['baselinePreparedMembers'], c['preparedMembers']
check(set(old) <= set(new) and len(new) == 160, 'No removed adapted source')
check(set(new) - set(old) == set(c['baselineUnadaptedMembers']), 'Authenticate newly adapted upstream paths')
combined = {**old, **c['baselineUnadaptedMembers']}
check({p for p in combined if combined[p] != new[p]} == set(c['productionChanges']), 'Only reviewed production paths change')
check(set(c['productionChanges']) == {'src/Ryujinx.Cpu/LightningJit/Arm64/RegisterUtils.cs', 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstTable.cs', 'src/Ryujinx.Cpu/LightningJit/NativeInterface.cs', 'src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs', 'src/Ryujinx.Graphics.Gpu/Engine/Threed/ThreedClass.cs', 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedPipeline.cs', 'src/Ryujinx.Graphics.GAL/Multithreading/Commands/TryHostConditionalRenderingCommand.cs'}, 'Production scope')
check(c['freshAppleGates'] == 3 and c['reusedAppleGates'] == 36 and c['historicalAppleReceipts'] == 37, 'Honest execution/reuse counts')
check(len(c['baselineReceipts']) == 37 and c['supersededReceipts'] == ['startup-trace-checks.json'], 'Historical guard proof stays scoped')
check([g['sourceKind'] for g in c['gates']] == ['pristine', 'baselinePrepared', 'baselinePrepared'], 'Correct fixture source stages')
check([g['report'] for g in c['gates']] == ['vector-register-mask-checks.json', 'guard-context-checks.json', 'occlusion-completion-checks.json'], 'Only affected fixtures run')
check(set(c['auxiliaryHistoricalReceipts']) == {'baseline-engine82/threaded-renderer-failures-checks.json'}, 'Preserve separate historical GAL evidence')
scope = c['auxiliaryHistoricalReceipts']['baseline-engine82/threaded-renderer-failures-checks.json']
check(scope['sha256'] == 'd1257f6ff48564462d0c1ce6906a4868f1d10a6cba28c361ebce99c694a26b7b', 'Actual archived GAL receipt')
check(scope['currentFullFixtureProof'] is False and scope['supersededBy'] == 'occlusion-completion-checks.json', 'Do not claim old full GAL execution for changed assembly')
check(set(scope['supersededProductionInputs']) == {'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedPipeline.cs', 'src/Ryujinx.Graphics.GAL/Multithreading/Commands/TryHostConditionalRenderingCommand.cs'}, 'Exact historical GAL dependency overlap')
check(all(combined[p] == h and new[p] != h for p, h in scope['supersededProductionInputs'].items()), 'Historical GAL input hashes are explicitly superseded')
for p, h in {**b, **c['inputs']}.items():
    check(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h, 'Changed reviewed input: ' + p)
print(json.dumps(dict(result='passed', checks=checks, preparationInputs=len(b), preparedMembers=len(new), nativeTestsExecuted=0)))
