#!/usr/bin/env python3
"""The preparation of a Switch 2 game is kept across deliveries that change none of what it depends on (python3).

Journal of an iPhone17,2, 13 Nov, first launch of Mario Kart World after IPA 734 was installed: the preparation ran
again from scratch, 92 s (RomFS view 25.2 s, code 3.1 s, pack walk 19.9 s, pack hashing 43.4 s), and the engine then
wrote its RomFS index again (126.9 s with that IPA) and translated its shaders again. The preparation's fingerprint held
the app's build number, which changes with every delivery, whatever the delivery contains.

The fingerprint now holds what a preparation depends on:
  - the preparation library, by the SHA-256 of its pinned archive (it is linked into the app's binary with the bridge);
  - the bridge's own steps, by a number in S2ArmGamePreparation.m (kPreparedSteps);
  - the S2Arm commit the engine is built from, whose formats the prepared files are in.
The first and the last are read from <app>/S2Arm-native-identity.json, the record the delivery writes once it has proved
the embedded pieces are the pinned bytes. A delivery that only brings engine patches keeps the preparation: what the
engine itself writes into a prepared game carries its own key (the shader library its chain, which is in the
fingerprint; the RomFS index its stamp, engine patch 0014). Without the record the build number is the identity, as
before.

Checked here: the bridge reads the names the delivery writes (the record's fields in standard_delivery.py, the pin's own
values), and its steps are the ones this test knows. The steps' digest is recorded below: a change to runSteps fails
this test until the digest is recorded again, which is when to decide whether games prepared before must be prepared
again (kPreparedSteps). The Objective-C is compiled by the delivery (and by s2arm-bridge-ios.yml when dispatched); what a
phone does is in its journal: `identity` says `pin` or `build`, `engineRun` the engine's CI run, and `prepare reused`
after an update is the gain.

    python3 -B test/s2arm_prepare_identity_test.py
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'packages/s2arm_engine_bridge/ios/Classes'
# SHA-256 of runSteps in S2ArmGamePreparation.m, from its first line to the line before @end. When this test fails on
# it: decide whether a game prepared by the previous steps can still be reused (if not, raise kPreparedSteps), then
# record the new digest and the number it goes with.
RUN_STEPS_SHA256 = '6ed919d8c9f6264efa280a3242eb27e4561a1546ea2298aa327894314ad222c7'
PREPARED_STEPS = '1'
failures, checks = [], 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def ordered(text, *parts):
    at = -1
    for part in parts:
        at = text.find(part, at + 1)
        if at < 0:
            return False
    return True


prep = (PKG / 'S2ArmGamePreparation.m').read_text(encoding='utf-8')
delivery = (ROOT / '.github/diagnostics/standard_delivery.py').read_text(encoding='utf-8')
pin_tool = (ROOT / 'build-utils/s2arm/engine_pin.py').read_text(encoding='utf-8')
pin = json.loads((ROOT / 'build-utils/s2arm/engine-pin.json').read_text(encoding='utf-8'))
LIBRARY = 'prepare/S2ArmPrepare.xcframework.zip'

# ---- the record the delivery writes at the app root ----
check("'identityFile': 'S2Arm-native-identity.json'" in pin_tool, "the S2Arm component's identity file is S2Arm-native-identity.json (engine_pin.py)")
check("(app / spec['identityFile']).write_text(json.dumps(record, indent=2) + '\\n')" in delivery, 'the delivery writes the record at the app root (engine_embed)')
check(ordered(delivery, 'def engine_evidence(', "binaries={label: item['sha256'] for label, item in", 'def engine_identity(',
              "binaries=evidence['binaries']", "record.update(pin.get('identity') or {})", 'return record'),
      "the record holds binaries (label -> SHA-256, from the pin) and the pin's identity facts (sourceIdentity among them)")
check("PREPARE_ZIP = 'S2ArmPrepare.xcframework.zip'" in pin_tool and "f'prepare/{PREPARE_ZIP}'" in pin_tool
      and ordered(pin_tool, "raw = (root / 'dist/s2arm/prepare' / PREPARE_ZIP).read_bytes()",
                  "require(pin['binaries'][f'prepare/{PREPARE_ZIP}']['sha256'] == sha(raw)"),
      'the pin names the preparation archive prepare/S2ArmPrepare.xcframework.zip, and the delivery installs that archive only when it is the pinned one')
binaries, source = pin.get('binaries', {}), pin.get('identity', {}).get('sourceIdentity', {})
check(isinstance(binaries.get(LIBRARY), dict) and re.fullmatch(r'[0-9a-f]{64}', str(binaries[LIBRARY].get('sha256', ''))) is not None,
      f'the pin gives {LIBRARY} a lowercase SHA-256')
check(re.fullmatch(r'[0-9a-f]{40}', str(source.get('s2arm_commit', ''))) is not None and isinstance(source.get('run'), int),
      "the pin's sourceIdentity gives the engine's S2Arm commit (40 lowercase hex) and its run (a number)")

# ---- the bridge reads those names, and only falls back to the build number ----
identity = prep[prep.index('static NSString *preparationCodeIdentity('):prep.index('// What a finished preparation depends on')]
check(ordered(identity, '[NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"S2Arm-native-identity.json"]',
              '[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]', 'record[@"binaries"]', 'record[@"sourceIdentity"]',
              f'binaries[@"{LIBRARY}"]', 'source[@"s2arm_commit"]', 'source[@"run"]'),
      'the identity is read from the record at the app root: binaries, sourceIdentity, the archive, the commit, the run')
check(identity.count('isKindOfClass:NSDictionary.class]') == 5 and '[run isKindOfClass:NSNumber.class]' in identity,
      'each level of the record is checked for its type before it is read')
check(ordered(identity, 'if (isLowerHex(library, 64) && isLowerHex(commit, 40)) {', '*kind = "pin";',
              'return [NSString stringWithFormat:@"prepare %@ steps %@ s2arm %@", library, kPreparedSteps, commit];', '*kind = "build";',
              'return [NSString stringWithFormat:@"build %@", NSBundle.mainBundle.infoDictionary[@"CFBundleVersion"] ?: @"-"];'),
      'both pinned values and the steps number, or the build number as before: never one pinned value alone')
check(ordered(prep, 'static BOOL isLowerHex(id value, NSUInteger length) {', 'if (![value isKindOfClass:NSString.class]) return NO;',
              'characterSetWithCharactersInString:@"0123456789abcdef"].invertedSet;', 'text.length == length &&'),
      'a value of the record counts only as lowercase hex of the expected length')
check('[text appendFormat:@"%@\\nchain %@\\nexport %@\\n", preparationCodeIdentity(identityKind, engineRun), chain, exportDir];' in prep
      and 'NSMutableString *text = [NSMutableString stringWithString:@"s2arm-prepared 1\\n"];' in prep,
      'the fingerprint holds the identity where it held the build number; the chain (the shader library\'s key) stays in it')
check('s2arm_journal("prepare", "reused", "\\"gid\\":\\"%s\\",\\"identity\\":\\"%s\\",\\"engineRun\\":%lld", gid.UTF8String, identityKind, engineRun);' in prep
      and 's2arm_journal("prepare", "begin", "\\"gid\\":\\"%s\\",\\"identity\\":\\"%s\\",\\"engineRun\\":%lld", gid.UTF8String, identityKind, engineRun);' in prep
      and 'long long engineRun = 0;' in prep,
      "the journal says which identity a preparation was judged by (pin or build) and the engine's run")
check(ordered(prep, 'NSData *sums = [NSData dataWithContentsOfFile:[systemData stringByAppendingPathComponent:@"SHA256SUMS"]];', 'if (sums.length == 0) {',
              'sums = [NSData dataWithContentsOfFile:[systemData.stringByDeletingLastPathComponent stringByAppendingPathComponent:@"SHA256SUMS"]];',
              '[text appendFormat:@"systemdata %@\\n", sums.length ? sha256Hex(sums) : @"-"];')
      and "'appResources': [{'path': 'S2ArmSystemData/SHA256SUMS', 'binary': f'sysdata/{SYSDATA_SUMS}'}]" in pin_tool
      and 'stringByAppendingPathComponent:@"S2ArmSystemData/systemdata"]' in prep,
      'the system data list is read where the delivery puts it, beside the systemdata/ folder the preparation is given (it was looked for inside that folder, where there is none: '
      'the fingerprint never saw the system data, and the pack holds a copy of them)')
check('dladdr' not in prep and 'S2ArmCodeIdentity' not in prep and not (PKG / 'S2ArmCodeIdentity.c').exists() and not (PKG / 'S2ArmCodeIdentity.h').exists(),
      "no identity taken from a linked image: the app's binary changes with any native code linked into it")

# ---- the bridge's steps are the ones the number stands for ----
check(f'static NSString *const kPreparedSteps = @"{PREPARED_STEPS}";' in prep, f'kPreparedSteps is {PREPARED_STEPS}, the number this test records the steps for')
start = prep.find('- (NSDictionary *)runSteps {')
end = prep.find('\n@end', start)
check(start > 0 and end > start, 'runSteps is the last method of S2ArmGamePreparation.m')
digest = hashlib.sha256(prep[start:end].encode('utf-8')).hexdigest() if start > 0 and end > start else ''
check(digest == RUN_STEPS_SHA256,
      f'runSteps changed (SHA-256 {digest}). If a game prepared before this change must be prepared again, raise kPreparedSteps in '
      'S2ArmGamePreparation.m (and PREPARED_STEPS here); then record this digest as RUN_STEPS_SHA256')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks, 'runSteps': digest[:16]}))
sys.exit(1 if failures else 0)
