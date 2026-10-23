"""Close private Build 513 around the new Core and the delivered Build 512 app."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

import rpcs3gow3_510_delivery as previous
import rpcs3gow3_core as changed_core

base=previous.base
HOST=previous.HOST
ROOT=Path(__file__).resolve().parents[2]
BASELINE='83efcc4c1e633586b372c11be8fbb6c42f0baa9c'
DELIVERED='02a0273494c50bc849b092c0fff395d9e5fd7ebf'
DELIVERED_RUN=39959490510
CORE_SOURCE='c5e54c5817f848e6f667b757931f91364e9faeda'
CORE_RUN=39968584447
PATCH_SHA256='db839d645eee6dc8dabba55a1580cb41a8314cbac0cb6c5e26f6c8a1be0f4f61'
ASSEMBLY={'.github/workflows/retroarch-delivery.yml','.github/diagnostics/rpcs3restore513_delivery.py',
    'build-utils/delivery-513-chatgpt-recipient.pem','build-utils/validate_rpcs3_gow3_ipa.py'}
INTEGRATION={'.github/diagnostics/rpcs3gow3_core.py','.github/workflows/neoswap-ipa.yml',
    '.github/workflows/retroarch-delivery.yml','.github/workflows/rpcs3-memory-audit.yml',
    'build-utils/rpcs3/canonical-source.json','build-utils/rpcs3/embedded-core.patch',
    'build-utils/rpcs3_core_syntax_gate.py','test/neo_swap_core_pin_test.py',
    'docs/rpcs3-restore-build513.md','test/fixtures/rpcs3_gow3_restore.diff',
    'test/rpcs3_gow3_restore_regression_test.py'}
validate_psp_core_identity=previous.validate_psp_core_identity
core_module=previous.core_module

def validate_rpc_core_identity(identity):
    assert identity['host_commit']==CORE_SOURCE
    assert identity['source_patch_sha256']==PATCH_SHA256
    core_module().validate_core_input_identity(identity)

def validate_rpc_core_pin(pin,paths):
    core=core_module()
    assert pin==CORE_SOURCE
    assert len(paths)==len(core.CORE_INPUTS) and set(paths)==set(core.CORE_INPUTS)
    core.validate_source_contract()
    core.validate_exact_pin(pin)
    print('PASS exact new restore Core inputs and ABI; no provenance rewriting')

def source_closure():
    assert os.environ.get('GITHUB_REF_NAME')=='Claude'
    assert os.environ.get('BUILD_NUMBER','513')=='513'
    integration=set(base.command(['git','diff','--name-only',BASELINE,CORE_SOURCE]).splitlines())
    assert integration==INTEGRATION,sorted(integration^INTEGRATION)
    for revision in (['HEAD'],[]):
        changed=set(base.command(['git','diff','--name-only',CORE_SOURCE,*revision]).splitlines())
        assert not changed-ASSEMBLY,sorted(changed-ASSEMBLY)
        product=base.command(['git','diff','--name-only',DELIVERED,*revision,'--',
            'lib','assets','packages','native','ios','pubspec.yaml','pubspec.lock'])
        assert not product,'Untested change outside RPCS3 Core: '+product
    core=core_module()
    core.validate_source_contract()
    core.validate_exact_pin(CORE_SOURCE)
    assert core.PATCH_SHA256==PATCH_SHA256
    changed_core.verify_source()
    old=base.command(['git','show',DELIVERED+':.github/workflows/retroarch-delivery.yml'])
    current=(ROOT/'.github/workflows/retroarch-delivery.yml').read_text()
    for line in old.splitlines():
        if any(token in line for token in ['DOLPHIN_CORE_HOST_SHA:','ARMSX2_CORE_HOST_SHA:',
            'ARMSX2_CORE_RUN_ID:','LIBRETRO_CORES_HOST_SHA:','LIBRETRO_CORES_RUN_ID:']):assert line in current,line
    for name in ['validate_rpcs3_ipa.py','validate_single_ipa_distribution.py',
        'validate_neoswap_ipa.py','validate_unified_cheats_ipa.py','validate_hd_textures_ipa.py',
        'validate_melonx_ipa.py','validate_motion507_ipa.py','validate_melonx_delete509_ipa.py',
        'validate_rpcs3_gow3_ipa.py','validate_ui_correction511_ipa.py','validate_navigation512_ipa.py',
        'delivery_benchmark.py seal']:assert name in old and name in current,name
    return {'baseline':BASELINE,'delivered512Source':DELIVERED,'delivered512Run':DELIVERED_RUN,
        'auditedCoreSource':CORE_SOURCE,'auditedCoreRun':CORE_RUN,'canonicalPatchSHA256':PATCH_SHA256,
        'rebuiltCores':['RPCS3'],'allAppAndOtherEngineInputsPreserved':True,'physicalDeviceTested':False}

def successful_core(wait):
    if wait:
        deadline=time.monotonic()+10800
        while True:
            state=base.api('actions/runs/'+str(CORE_RUN))
            assert state['head_sha']==CORE_SOURCE
            if state['status']=='completed':break
            assert time.monotonic()<deadline,'Timed out waiting for frozen restore Core'
            print('Waiting for frozen restore Core',CORE_RUN,state['status'],flush=True)
            time.sleep(30)
    return base.successful_run(CORE_RUN,CORE_SOURCE,['RPCS3 GoW3: targeted proofs and iPhone Core'])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--scope',default='full')
    parser.add_argument('--source-only',action='store_true')
    parser.add_argument('--wait-for-components',action='store_true')
    parser.add_argument('--skin-session-evidence',action='store_true')
    parser.add_argument('--output',default='build/delivery/reused-validation.json')
    parser.add_argument('--rpc-core-inputs')
    parser.add_argument('core_paths',nargs='*')
    args=parser.parse_args()
    if args.rpc_core_inputs:
        validate_rpc_core_pin(args.rpc_core_inputs,args.core_paths)
        return
    record={'result':'passed','source':base.command(['git','rev-parse','HEAD']),'sourceClosure':source_closure()}
    if not args.source_only:
        record['reusedEvidence']=[base.successful_run(DELIVERED_RUN,DELIVERED,
            ['checks','native','Release device build • cold']),successful_core(args.wait_for_components)]
    out=ROOT/args.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(record,indent=2)+'\n')
    print('PASS exact restore Core and unchanged delivered 512 frontend/other-engine evidence')

if __name__=='__main__':main()
