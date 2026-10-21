#!/usr/bin/env python3
"""Prove the host JIT state machines were not refactored by the legacy patch."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
BASE='beed82be2a851d19c8cdada8d48b04da7f5f106c'

def original(p):
    return subprocess.check_output(['git','show',BASE+':'+p],cwd=ROOT,text=True)

for lower,cls in (('rpcs3','Rpcs3'),('armsx2','Armsx2')):
    p=f'packages/{lower}_internal_bridge/ios/Classes/{cls}JitBridgePlugin.mm'
    old=original(p); new=(ROOT/p).read_text()
    if lower=='armsx2':
        start=new.index('  // Export legacy startup evidence only;')
        end=new.index('\n}\nstatic void ARMSX2Milestone',start)
        log=new[start:end]
        assert 'majorVersion >= 26) return;' in log
        assert 'armsx2_jit_debug.log' in log and '524288' in log
        new=new[:start]+new[end:]
        new=new.replace('message ?: @"");\n\n}', 'message ?: @"");\n}',1)
    new=new.replace('          : [NSString stringWithFormat:@"JIT_PREPARATION_TIMEOUT: StikJIT did not complete preparation. Last stage: %@",\n              session.logs.lastObject ?: @"No helper stage received."];',
                    '          : @"StikJIT did not attach universal.js to NeoStation.";')
    # RewindBox changed only four user-visible diagnostics on each JIT host.
    # Normalize these reviewed labels; continue comparing the full machine.
    assert new.count('RewindBox') == 4, p+' unexpected branding delta'
    new = new.replace('RewindBox', 'NeoStation')
    assert old==new,p+' changed outside diagnostics'
p='packages/dolphin_internal_bridge/ci/verify_ipa.py'
new=(ROOT/p).read_text()
# The shared IPA contains the NeoSwap donor and separate guest-page relay.
# Normalize only these reviewed packaging additions; every original
# Dolphin/JIT check must remain byte-exact. Each addition occurs exactly once.
replacements = (
    ('import sys\n', ''),
    ("sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'build-utils'))\n"
     'from validate_single_ipa_distribution import (\n'
     '    DONOR_CONTRACTS, RELAY_CONTRACTS, DONOR_EXTENSION_POINT, validate as validate_distribution,\n'
     ')\n\n', ''),
    ('    **DONOR_CONTRACTS,\n', ''),
    ('    **RELAY_CONTRACTS,\n', ''),
    ('    validate_distribution(ipa)\n', ''),
    ('(DONOR_EXTENSION_POINT if bundle_name in DONOR_CONTRACTS or bundle_name in RELAY_CONTRACTS else SHARE_EXTENSION_POINT)',
     'SHARE_EXTENSION_POINT'),
)
for added, previous in replacements:
    assert new.count(added)==1, 'Unexpected NeoSwap packaging delta: '+added
    new=new.replace(added, previous)
# The retired external MeloNX/Atari URL routes were removed after Build 497.
# Normalize precisely the two reviewed policy declarations, not the validator.
retired_new = "{'retroarch', 'shortcuts'} <= schemes"
retired_old = "{'retroarch', 'shortcuts', 'melonx'} <= schemes"
forbidden_new = "not schemes & {'dolphin', 'dolphinios', 'dolphin-emu', 'melonx', 'atariemulator'}, 'Retired external emulator query scheme found'"
forbidden_old = "not schemes & {'dolphin', 'dolphinios', 'dolphin-emu'}, 'External Dolphin query scheme found'"
assert new.count(retired_new)==1 and new.count(forbidden_new)==1
new=new.replace(retired_new,retired_old).replace(forbidden_new,forbidden_old)
assert new.replace("== '1.9.0', 'Wrong StikJIT version'", "== '1.5.0', 'Wrong StikJIT version'")==original(p)
p='packages/dolphin_jit_helper/ios/Classes/DolphinJITRequestHandlerBase.swift'
swift=(ROOT/p).read_text()
assert swift.count('RewindBox')==7, 'Unreviewed Dolphin JIT branding delta'
assert swift.replace('StikJIT 1.9.0','StikJIT 1.5.0').replace(
    'RewindBox','NeoStation')==original(p)
print('PASS: exact retained JIT host state machines; only timeout text/legacy log; Dolphin algorithm unchanged')
