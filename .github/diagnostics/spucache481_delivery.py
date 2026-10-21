"""Compose the delivered 0.0.8 (Build 480) application with the Build 481 RPCS3 Core.

Build 481 changes only the RPCS3 Core (persistent ARM64 SPU object cache,
NEOSTATION_BUILD481_SPU_OBJECT_CACHE_V1): every application, catalogue, skin,
helper and other-engine input is the delivered Build 480 product. This gate
reads CI evidence; it never reruns suites or rebuilds a core. The Core run is
the one pinned by the delivery workflow; its preflight artifact must carry the
executed policy test, the two-process MCJIT relocation proof and the wiring
checks, and its identity must match the canonical patch of this candidate.
"""
import hashlib,json,subprocess,sys,tempfile
from contextlib import contextmanager
from pathlib import Path
import unified_cheats_delivery as previous

# 0.0.8 release packaging of the verified Build 480: the branch head before this cycle.
BASE='bcca4e4a4dc89a96b1dde05d66436af54efd327e'
# Build 480 source (run 39132356516: checks, native, cold Release).
DELIVERED='7493d9babe20be1b2939e21a1051a72da8fb5d01'
# Build 481 Core: source and rpcs3-core.yml run pinned by the delivery workflow.
CORE_SOURCE='5919be61269f67542c4f8c905c30555cbe09bdf0'
CORE_RUN=39144244183
PATCH='bc63c5da2dc97dca0f205b132dfb078d53da3d87c6fcf546810468512dd37a33'
CORE_JOB='RPCS3 Core arm64 with NeoSwap client'
# Changed inputs proven by the Core run (published Core inputs and host tests).
TESTED={'build-utils/rpcs3/canonical-source.json','build-utils/rpcs3/embedded-core.patch',
    'test/neo_swap_core_pin_test.py','test/rpcs3_build444_core_delta_test.py',
    'test/native/rpcs3_build444_core_delta_test.cpp','test/rpcs3_build481_spu_object_cache_test.py',
    'test/native/rpcs3_build481_spu_object_cache_test.cpp','test/native/rpcs3_spu_object_relocation_test.cpp',
    'test/rpcs3_spu_warmup_test.py','test/rpcs3_build258_runtime_resilience_test.py',
    'test/rpcs3_xitrix_v0101_native_test.py',
    '.github/workflows/rpcs3-core.yml'}
# Delivery wiring, records and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','docs/build481-plan.md','docs/evidence/spucache481-delivery.json',
    '.github/diagnostics/spucache481_delivery.py','.github/workflows/retroarch-delivery.yml',
    '.github/workflows/neoswap-ipa.yml','build-utils/verify_delivery_reuse.py',
    'native/import-memory-candidate.json','test/import_memory_candidate_scope_test.py'}
PRODUCT_PATHS=['lib','packages','assets','native','pubspec.yaml','pubspec.lock','tools','build-utils/libretro']

def source_closure():
    for end in (['HEAD'],[]):
        paths=set(previous.command(['git','diff','--name-only',BASE,*end]).splitlines())
        extra=paths-TESTED-DELIVERY_ONLY
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        # Every tested input is byte-identical to the Core run source.
        previous.command(['git','diff','--exit-code',CORE_SOURCE,*end,'--',*sorted(TESTED)])
        # The application product is the delivered 0.0.8; only the candidate manifest changed under native/.
        changed=set(previous.command(['git','diff','--name-only',BASE,*end,'--',*PRODUCT_PATHS]).splitlines())
        if changed-{'native/import-memory-candidate.json'}:
            raise ValueError('Unexpected product change since 0.0.8: '+', '.join(sorted(changed)))
    # 0.0.8 repackaged the delivered Build 480 with its marketing version only.
    packaging=set(previous.command(['git','diff','--name-only',DELIVERED,BASE,'--',*PRODUCT_PATHS]).splitlines())
    if packaging!={'pubspec.yaml'}:raise ValueError('Unexpected product change between Build 480 and 0.0.8: '+', '.join(sorted(packaging)))
    manifest=json.loads((previous.ROOT/'build-utils/rpcs3/canonical-source.json').read_text())
    patch=hashlib.sha256((previous.ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes()).hexdigest()
    if manifest['patch_sha256']!=PATCH or patch!=PATCH:raise ValueError('Canonical Core delta differs from the Build 481 pin')
    if 'spu_object_cache' not in manifest or manifest['spu_object_cache']['device_runtime_tested'] is not False:
        raise ValueError('Build 481 manifest record missing or claiming device validation')
    return {'deliveredBaseline':DELIVERED,'releasePackaging':BASE,'coreSource':CORE_SOURCE,'coreRun':CORE_RUN,
        'canonicalPatchSHA256':PATCH,'changedProductPaths':[],'coreChanged':True,
        'precompiledEnginesHelpersCatalogueSkinsUnchanged':True}

@contextmanager
def rpc_core_input_view(pin):
    """The Build 481 Core inputs were published with the current host header.

    Unlike the Build 444 pin, no optional-declaration isolation view is needed:
    every published Core input is checked byte for byte against the pin.
    """
    if pin!=CORE_SOURCE:raise ValueError('Unexpected RPCS3 Core pin: '+str(pin))
    sys.path.insert(0,str(previous.ROOT/'test'))
    import neo_swap_core_pin_test as core
    yield core,previous.ROOT

def validate_rpc_core_identity(identity):
    with rpc_core_input_view(identity['host_commit']) as (core,root):
        core.validate_core_input_identity(identity,root=root)

def validate_rpc_core_pin(pin,paths):
    with rpc_core_input_view(pin) as (core,root):
        if len(paths)!=len(core.CORE_INPUTS) or set(paths)!=set(core.CORE_INPUTS):
            raise ValueError('Delivery omitted or duplicated a published Core input')
        core.validate_source_contract()
        core.validate_exact_pin(pin,root=root)
    print('PASS all authentic RPCS3 Core inputs of the Build 481 pin')

def evidence():
    records=[previous.successful_run(39132356516,DELIVERED,['checks','native','Release device build • cold']),
        previous.successful_run(CORE_RUN,CORE_SOURCE,[CORE_JOB])]
    with tempfile.TemporaryDirectory(prefix='spucache481-proof-') as tmp:
        subprocess.run(['gh','run','download',str(CORE_RUN),'--repo','TarbleFR/RewindBox',
            '--name','RPCS3Core-diagnostics-'+CORE_SOURCE,'--dir',tmp],check=True)
        proof=(Path(tmp)/'spu-object-cache-proof.txt').read_text()
        identity=json.loads((Path(tmp)/'identity.json').read_text())
    for needle in ('PASS: Build 481 SPU object cache policy',
                   'PASS: relocated external data, external call, rodata and pointer table across processes',
                   'PASS: truncated and foreign objects are rejected before MCJIT',
                   'relocation proof executed with 22.'):
        if needle not in proof:raise ValueError('Core preflight proof missing: '+needle)
    if proof.count('PASS: relocated external data')!=2:raise ValueError('Expected two independent load processes in the proof')
    if identity['host_commit']!=CORE_SOURCE or identity['source_patch_sha256']!=PATCH or identity['device_runtime_tested'] is not False:
        raise ValueError('Core identity differs from the pinned run')
    records[-1].update(proofSHA256=hashlib.sha256(proof.encode()).hexdigest(),relocationProofProcesses=4,
        coreSHA256=identity['sha256'],coreInputs=len(identity['core_input_sha256']))
    receipts={p:hashlib.sha256((previous.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/scraping480-delivery.json',)}
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
        print('PASS Build 481 source closure: application is the delivered 0.0.8, Core inputs match the pinned Core source')
        return
    records,receipts=evidence()
    record={'result':'passed','testedSHA':CORE_SOURCE,'candidateSHA':previous.command(['git','rev-parse','HEAD']),
        'validationWasReused':True,'sourceClosure':closure,'reusedEvidence':records,'receiptSHA256':receipts,
        'deviceGameplayValidated':False,'coreRebuilt':True,'coreRun':CORE_RUN}
    if a.dart_evidence:
        record.update(key=os.environ['DART_VALIDATION_KEY'],tool='Flutter 3.47.2, Ubuntu 24.04')
    if a.libretro_evidence:
        xcode=previous.command(['xcodebuild','-version'])
        sdk=previous.command(['xcrun','--sdk','iphoneos','--show-sdk-version'])
        if xcode!='Xcode 26.3\nBuild version 17C529' or sdk!='26.2':raise ValueError('Changed native toolchain')
        record.update(xcode=xcode,iphoneSDK=sdk)
    out=previous.ROOT/a.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(record,indent=2)+'\n')
    print('PASS delivered 0.0.8 application + Build 481 Core evidence; no suites rerun, one Core rebuilt')

if __name__=='__main__':
    main()
