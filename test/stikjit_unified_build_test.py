#!/usr/bin/env python3
"""One pinned source/runtime/interface set; exact retained iOS 18/26/27 JIT code."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'build-utils'))
from build_patched_stikjit import input_fingerprint
BASE='238255370f4dc7ef1e7c9a0ff0257d9a884f39d4'
paths=['build-utils/patch_stikjit_compat.py','build-utils/patch_stikjit_rpcs3.py',
       'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3JitBridgePlugin.mm',
       'packages/armsx2_internal_bridge/ios/Classes/Armsx2JitBridgePlugin.mm',
       'packages/stikjit_bridge/ios/Classes/StikjitBridgePlugin.swift',
       'packages/stikjit_bridge/ios/Classes/StikjitBridgePluginV2.swift']
for lower,cls in [('rpcs3','Rpcs3'),('armsx2','Armsx2'),('dolphin','Dolphin')]:
    paths.append(f'packages/{lower}_jit_helper/ios/Classes/{cls}JITRequestHandlerBase.swift')
for lower in ('rpcs3','armsx2'):
    paths.append(f'packages/{lower}_jit_helper/ios/Resources/{lower}-universal.js')
for path in paths:
    old=subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT).replace(b'\r\n',b'\n')
    current=(ROOT/path).read_bytes().replace(b'\r\n',b'\n')
    # RewindBox is the independent fork's display name; the frozen Build363
    # JIT baseline predates that rebrand. Normalize only the visible brand
    # token before proving all runtime/patch bytes remain unchanged.
    current=current.replace(b'RewindBox',b'NeoStation')
    if path=='packages/rpcs3_internal_bridge/ios/Classes/Rpcs3JitBridgePlugin.mm':
        # Build 526 added the pre-existing armv8.4 CPU eligibility gate.
        # Remove only its exact reviewed import/early return when comparing
        # the retained JIT state machine against the older legacy baseline.
        cpu_import=b'#import "RPCS3CPUCompatibility.h"\n'
        cpu_gate=(b'  if (NSString* cpuError = RPCS3CPUCompatibilityError()) {\n'
                  b'    result(@{@"success": @NO, @"code": @"RPCS3_CPU_INCOMPATIBLE", @"message": cpuError});\n'
                  b'    return;\n'
                  b'  }\n\n')
        assert current.count(cpu_import)==1 and current.count(cpu_gate)==1
        current=current.replace(cpu_import,b'').replace(cpu_gate,b'')
    assert current==old,'Runtime JIT changed: '+path
for path in ('.github/workflows/ios-ci.yml','build-utils/prepare_fast_native_runtime.py',
             'packages/dolphin_internal_bridge/ci/build_support.py'):
    text=(ROOT/path).read_text()
    # A historical version in release prose is not an executable dependency.
    # Remove ONLY the reviewed sentence; every other obsolete version, artifact
    # ID and donor option remains forbidden, including commands in this workflow.
    history='NeoStation now integrates **StikJIT 1.9.0**, replacing the previous 1.5.0 integration.'
    assert text.count(history) <= 1, 'Unexpected repeated historical version: '+path
    executable=text.replace(history, '')
    assert '1.5.0' not in executable and '11039092572' not in text,path
    assert '--stik-xcframework-zip' not in text,path
pin=json.loads((ROOT/'build-utils/stikjit/source.json').read_text())
identity_path=ROOT/'build/stikjit-current/identity.json'
if identity_path.is_file():
    identity=json.loads(identity_path.read_text())
    assert identity['release']==pin['version']
    assert identity['sourceRevision']==pin['revision']
    assert identity['sourceInputsSha256']==input_fingerprint()
    assert identity['builtFromSource'] is True
    modules=[]
    for package in ('stikjit_bridge','dolphin_jit_helper'):
        fw=ROOT/f'packages/{package}/ios/Frameworks/StikJIT.xcframework/ios-arm64/StikJIT.framework'
        assert hashlib.sha256((fw/'StikJIT').read_bytes()).hexdigest()==identity['binarySha256']
        interfaces=sorted(fw.rglob('*.swiftinterface'))
        assert interfaces and all('neoStationClassicAttach' in x.read_text() for x in interfaces)
        assert json.loads((fw/'NeoStation-StikJIT-source.json').read_text())['revision']==pin['revision']
        modules.append([x.read_bytes() for x in interfaces])
    assert modules[0]==modules[1],'Shared helper Swift ABI differs'
    bridge=''.join((ROOT/f'packages/stikjit_bridge/ios/Classes/{file}.swift').read_text()
                  for file in ('StikjitBridgePlugin','StikjitBridgePluginV2'))
    exports=set(re.findall(r'Self.resolve\(\s*"([a-z][a-z0-9_]+)"',bridge))
    assert set(identity['dynamicFFIExports'])==exports
print('PASS: canonical source build; no obsolete donor JIT; 11 JIT runtime/patch files retain Build363 behavior plus the reviewed CPU eligibility gate')
