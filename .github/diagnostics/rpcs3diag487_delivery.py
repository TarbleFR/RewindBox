"""Compose the delivered Build 486 with the Build 487 RPCS3 Core (audit diagnostics and selectable levers).

Build 487 implements the corrections of docs/rpcs3-bottleneck-audit-2026-10-18.md
(NEOSTATION_BUILD487_DIAGNOSTICS_V1 in the Core, NEOSTATION_BUILD487_HOST_DIAGNOSTICS_V1
in the RPCS3 bridge): emulator state, guest frames and boot progress in the
metrics, COREPROF other/top threads and lines without frames, CONFIG_LAYERS,
NEOSTATION_RESTART, JITPROF_BOOT, SAVESTATE_BOOT, FREEZE_DUMP and
MUTEX_DESTROY_BUSY lines, JITPROF exported by the host, a rotated diagnostic
file, and four Core settings whose defaults keep the Build 483 gameplay
behaviour (SPU Spin Timing, RSX FIFO Idle Wait = Bounded sleep, SPU Object Cache
Retained Keys, SPU Warmup Scope). Every other application, catalogue, skin,
helper and engine input is the delivered Build 486 product. This gate reads CI
evidence; it never reruns suites. The Core run pinned by the delivery workflow
must carry the Build 481, 483 and 487 preflight proofs and its identity must
match the canonical patch of this candidate; the host changes are proven by the
same run (host tests executed on macOS) and compiled by the delivery's own
Release build.
"""
import hashlib,json,subprocess,sys,tempfile
from contextlib import contextmanager
from pathlib import Path
import hdcat486_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Branch head before this cycle: the Build 486 records on Claude (delivery and skin-loading note).
BASE='32523c76616e19a125c64ddea65ed364a4bf379f'
# Build 486 source and its delivery run (checks/native reused, cold Release).
DELIVERED='b18c30cd884f915950ee03cb8d5a182de1cd9028'
DELIVERED_RUN=39195753114
# Build 487 Core: source and rpcs3-core.yml run pinned by the delivery workflow.
CORE_SOURCE=''
CORE_RUN=0
PATCH=''
CORE_JOB='RPCS3 Core arm64 with NeoSwap client'
# Host changes of Build 487 (product): proven by the Core run's host tests,
# compiled for the iPhone by the delivery's Release build.
HOST_PRODUCT={'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreABI.h'}
CORE_PRODUCT={'build-utils/rpcs3/canonical-source.json','build-utils/rpcs3/embedded-core.patch',
    'native/import-memory-candidate.json'}  # candidate record: RPCS3 postimage hashes and the Build 487 note
# Changed inputs proven by the Core run (published Core inputs, host product and tests).
TESTED=HOST_PRODUCT|CORE_PRODUCT|{'build-utils/rpcs3_core_syntax_gate.py','test/neo_swap_core_pin_test.py',
    'test/rpcs3_build258_core_architecture_test.py','test/rpcs3_build487_core_diagnostics_test.py',
    'test/rpcs3_build487_host_diagnostics_test.py','test/native/rpcs3_diagnostics_test.mm',
    'test/native/rpcs3_build487_profiler_helpers_test.cpp','test/native/rpcs3_build487_boot_diagnostics_test.cpp',
    'test/native/rpcs3_build487_lever_helpers_test.cpp','test/native/rpcs3_build487_retention_sequence_test.cpp',
    '.github/workflows/rpcs3-core.yml','build-utils/rpcs3/regenerate_canonical_delta.py'}
# Delivery wiring, records, authoring tool and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','docs/build487-plan.md','docs/evidence/rpcs3diag487-delivery.json',
    'docs/rpcs3-bottleneck-audit-2026-10-18.md',
    '.github/diagnostics/rpcs3diag487_delivery.py','.github/workflows/retroarch-delivery.yml',
    '.github/workflows/neoswap-ipa.yml','build-utils/verify_delivery_reuse.py'}
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS

def source_closure():
    for name,value in (('CORE_SOURCE',CORE_SOURCE),('PATCH',PATCH)):
        if len(value) not in (40,64):raise ValueError(f'{name} is not pinned yet')
    if not CORE_RUN:raise ValueError('CORE_RUN is not pinned yet')
    for end in (['HEAD'],[]):
        paths=set(base.command(['git','diff','--name-only',BASE,*end]).splitlines())
        extra=paths-TESTED-DELIVERY_ONLY
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        # Every tested input is byte-identical to the Core run source.
        base.command(['git','diff','--exit-code',CORE_SOURCE,*end,'--',*sorted(TESTED)])
        # The product differs from delivered 486 exactly by the RPCS3 bridge and the canonical delta.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        if changed!=HOST_PRODUCT|CORE_PRODUCT:
            raise ValueError('Unexpected product change since Build 486: '+', '.join(sorted(changed^(HOST_PRODUCT|CORE_PRODUCT))))
        # The ARMSX2 Core (ABI 8, Build 485) is unchanged.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS])
    manifest=json.loads((base.ROOT/'build-utils/rpcs3/canonical-source.json').read_text())
    patch=hashlib.sha256((base.ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes()).hexdigest()
    if manifest['patch_sha256']!=PATCH or patch!=PATCH:raise ValueError('Canonical Core delta differs from the Build 487 pin')
    record=manifest.get('diagnostics_487')
    if not record or record['device_runtime_tested'] is not False or record['gameplay_validated'] is not False:
        raise ValueError('Build 487 manifest record missing or claiming device validation')
    if manifest['llvm_pipelines']['device_runtime_tested'] is not False:raise ValueError('Build 483 record changed')
    hosted=(base.ROOT/'native/textures/catalogue/manifest.json.gz').read_bytes()
    bundled=(base.ROOT/'packages/neo_texture_catalog/ios/Resources/manifest.json.gz').read_bytes()
    if hosted!=bundled:raise ValueError('Bundled and hosted HD texture catalogues differ')
    return {'deliveredBaseline':DELIVERED,'baselineRecord':BASE,'coreSource':CORE_SOURCE,'coreRun':CORE_RUN,
        'canonicalPatchSHA256':PATCH,'changedProductPaths':sorted(HOST_PRODUCT|CORE_PRODUCT),'rpcs3CoreChanged':True,
        'armsx2CoreChanged':False,'precompiledEnginesHelpersCatalogueSkinsUnchanged':True}

@contextmanager
def rpc_core_input_view(pin):
    """Build 487 Core inputs were published with the current host header: no isolation view."""
    if pin!=CORE_SOURCE:raise ValueError('Unexpected RPCS3 Core pin: '+str(pin))
    sys.path.insert(0,str(base.ROOT/'test'))
    import neo_swap_core_pin_test as core
    yield core,base.ROOT

def validate_rpc_core_identity(identity):
    with rpc_core_input_view(identity['host_commit']) as (core,root):
        core.validate_core_input_identity(identity,root=root)

def validate_rpc_core_pin(pin,paths):
    with rpc_core_input_view(pin) as (core,root):
        if len(paths)!=len(core.CORE_INPUTS) or set(paths)!=set(core.CORE_INPUTS):
            raise ValueError('Delivery omitted or duplicated a published Core input')
        core.validate_source_contract()
        core.validate_exact_pin(pin,root=root)
    print('PASS all authentic RPCS3 Core inputs of the Build 487 pin')

def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold']),
        base.successful_run(CORE_RUN,CORE_SOURCE,[CORE_JOB])]
    with tempfile.TemporaryDirectory(prefix='rpcs3diag487-proof-') as tmp:
        subprocess.run(['gh','run','download',str(CORE_RUN),'--repo','TarbleFR/neostation-ios',
            '--name','RPCS3Core-diagnostics-'+CORE_SOURCE,'--dir',tmp],check=True)
        proofs={name:(Path(tmp)/name).read_text() for name in
            ('spu-object-cache-proof.txt','llvm-pipeline-proof.txt','build487-core-proof.txt','build487-host-proof.txt')}
        identity=json.loads((Path(tmp)/'identity.json').read_text())
    needles={'spu-object-cache-proof.txt':('PASS: relocated external data, external call, rodata and pointer table across processes',
                                         'PASS: truncated and foreign objects are rejected before MCJIT'),
             'llvm-pipeline-proof.txt':('PASS: 7 kernels x 5 pipelines verified','PASS: Build 483 LLVM pipelines (harness executed with 22.'),
             'build487-core-proof.txt':('PASS: Build 487 Core diagnostics and levers',),
             'build487-host-proof.txt':('PASS: host mirror equals the Core metrics struct and validity bits',
                                        'PASS: Build 487 host diagnostics','RPCS3 native diagnostics concurrency/rotation/reopen tests: OK',
                                        'PASS: bounded centralized diagnostics')}
    for name,items in needles.items():
        for needle in items:
            if needle not in proofs[name]:raise ValueError(f'Preflight proof missing in {name}: {needle}')
    if identity['host_commit']!=CORE_SOURCE or identity['source_patch_sha256']!=PATCH or identity['device_runtime_tested'] is not False:
        raise ValueError('Core identity differs from the pinned run')
    records[-1].update(coreSHA256=identity['sha256'],coreInputs=len(identity['core_input_sha256']),
        proofSHA256={name:hashlib.sha256(text.encode()).hexdigest() for name,text in proofs.items()})
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/hdcat486-delivery.json','docs/evidence/llvmpipe483-delivery.json') if (base.ROOT/p).is_file()}
    return records,receipts

def main():
    import argparse,os
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-only',action='store_true')
    p.add_argument('--dart-evidence',action='store_true')
    p.add_argument('--libretro-evidence',action='store_true')
    p.add_argument('--skin-session-evidence',action='store_true')
    p.add_argument('--scope',default='full',choices=['full'])
    p.add_argument('--output',default='build/delivery/reused-validation.json')
    p.add_argument('--rpc-core-inputs')
    p.add_argument('core_paths',nargs='*')
    a=p.parse_args()
    closure=source_closure()
    if a.rpc_core_inputs:
        validate_rpc_core_pin(a.rpc_core_inputs,a.core_paths)
        return
    if a.source_only:
        print('PASS Build 487 source closure: delivered 486 product + RPCS3 bridge diagnostics, Core inputs match the pinned Core source')
        return
    records,receipts=evidence()
    record={'result':'passed','testedSHA':CORE_SOURCE,'candidateSHA':base.command(['git','rev-parse','HEAD']),
        'validationWasReused':True,'sourceClosure':closure,'reusedEvidence':records,'receiptSHA256':receipts,
        'deviceGameplayValidated':False,'coreRebuilt':True,'coreRun':CORE_RUN,'rebuiltCore':'RPCS3 (Build 487 diagnostics and levers)'}
    if a.dart_evidence:
        record.update(key=os.environ['DART_VALIDATION_KEY'],tool='Flutter 3.47.2, Ubuntu 24.04')
    if a.libretro_evidence:
        xcode=base.command(['xcodebuild','-version'])
        sdk=base.command(['xcrun','--sdk','iphoneos','--show-sdk-version'])
        if xcode!='Xcode 26.3\nBuild version 17C529' or sdk!='26.2':raise ValueError('Changed native toolchain')
        record.update(xcode=xcode,iphoneSDK=sdk)
    out=base.ROOT/a.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(record,indent=2)+'\n')
    print('PASS delivered 486 product + Build 487 RPCS3 Core and bridge evidence; no suites rerun, one Core rebuilt')

if __name__=='__main__':
    main()
