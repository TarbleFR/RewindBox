#!/usr/bin/env python3
"""Binding-sized descriptor scratch for every title (adapt_descriptor_scratch_all_titles) on the real prepared engine.

Usage: melonx_descriptor_scratch_all_titles_test.py <Core 639 prepared MeloNX tree>

Applies the adapter to a copy of the prepared Library.cs and checks that only the BindingSizedDescriptorScratch
assignment changed (every other per-title policy keeps `hogwarts`), and that the Core 631 gate receipt
(docs/evidence/melonx-631-gates/fallback-descriptor-scratch-checks.json), which ran the production DescriptorSetUpdater
with the policy off and on, recorded the same semantic digest in both. The policy-on behaviour is that proof; this test
binds the scope change to it. No device; no FPS claim. Writes dist/melonx/descriptor-scratch-all-titles-checks.json.
"""
from pathlib import Path
import difflib, hashlib, json, shutil, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
# Core gate form: <control> --candidate-source <final preparation>; the control tree is not read (the exact Core 639
# control is rebuilt from the final preparation). Standalone form: <Core 639 prepared tree>.
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
# The Core 639 preparation, or the final preparation (prepare_embedded.py runs this adapter): its exact control.
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_descriptor_scratch_all_titles', _HOLD)
from adapt_descriptor_scratch_all_titles import apply, BASELINE

checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 639 preparation: ' + name)
with tempfile.TemporaryDirectory(prefix='melonx-descriptor-scope-') as temporary:
    work = Path(temporary)
    target = work / 'src/Ryujinx.Library/Library.cs'
    target.parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / 'src/Ryujinx.Library/Library.cs', target)
    before = target.read_text().splitlines()
    apply(work)
    after = target.read_text().splitlines()
diff = list(difflib.ndiff(before, after))
removed = [line[2:].strip() for line in diff if line.startswith('- ')]
added = [line[2:].strip() for line in diff if line.startswith('+ ')]
code = lambda lines: [line for line in lines if not line.startswith('//')]
check(code(removed) == ['Ryujinx.Graphics.Vulkan.EncodingPolicy.BindingSizedDescriptorScratch = hogwarts;'] and
      code(added) == ['Ryujinx.Graphics.Vulkan.EncodingPolicy.BindingSizedDescriptorScratch = true;'],
      'only the scratch flag changes, to every title')
text = '\n'.join(after)
for policy in ('EncodingPolicy.IncrementalArrayDescriptors = hogwarts;', 'MoltenVkPolicy.DeferInPassReadBarriers = hogwarts;',
               'GpuContext.QueueSyncpointsBehindReports = hogwarts;', 'GraphicsConfig.HogwartsFloatDmaGpuCopy = hogwarts;'):
    check(text.count(policy) == 1, 'Hogwarts scope kept: ' + policy)
check(text.count('BindingSizedDescriptorScratch') == 1, 'one assignment only')
gate = json.loads((ROOT / 'docs/evidence/melonx-631-gates/fallback-descriptor-scratch-checks.json').read_text())
reports = gate['reports']
check(gate['result'] == 'passed' and gate['encodingPolicyRuns'] == ['off', 'on'], 'policy-on gate ran')
check(reports['candidateOn']['semanticDigest'] == reports['candidateOff']['semanticDigest'] == reports['control']['semanticDigest'] and
      reports['candidateOn']['resourceTrace'] == reports['candidateOff']['resourceTrace'], 'policy on and off are semantically equal')
inputs = ['build-utils/melonx/adapt_descriptor_scratch_all_titles.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_descriptor_scratch_all_titles_test.py', 'docs/evidence/melonx-631-gates/fallback-descriptor-scratch-checks.json']
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core639Preparation', postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {}, physicalDeviceTested=False, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Scope change bound to the Core 631 on/off equivalence proof; SSBU frame time not measured.')
out = ROOT / 'dist/melonx/descriptor-scratch-all-titles-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks)))
