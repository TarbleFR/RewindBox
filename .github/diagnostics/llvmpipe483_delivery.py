"""Compose the delivered Build 482 application with the Build 483 RPCS3 Core (selectable LLVM pipelines).

Build 483 changes only the RPCS3 Core (NEOSTATION_BUILD483_LLVM_PIPELINES_V1:
SPU pipeline with InstCombine as upstream RPCS3 and ARMSX3, convention-matched
m_test_state calls, PPU pipeline levels named by settings bits, pipelines folded
into the SPU object-cache key, JITPROF pipeline fields) and its host tests.
Every application, catalogue, skin, helper and other-engine input, including the
Build 482 ARMSX2 Core (ABI 7), is the delivered Build 482 product. This gate
reads CI evidence; it never reruns suites or rebuilds a core. The Core run is
the one pinned by the delivery workflow; its preflight artifact must carry the
Build 481 object-cache proof and the Build 483 pipeline proof (calling
convention hazard, seven kernels times five pipelines executed bit-exactly on
the host), and its identity must match the canonical patch of this candidate.
"""
import hashlib,json,subprocess,sys,tempfile
from contextlib import contextmanager
from pathlib import Path
import ps2blend482_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Branch head before this cycle: the Build 482 delivery record.
BASE='47c9e9c1e07db306c09edbfc394590428458e874'
# Build 482 source (run 39157242359: checks/native reused, cold Release).
DELIVERED='c676b31710c50cfc60ca3e356aecd49995fe0a76'
# Build 483 Core: source and rpcs3-core.yml run pinned by the delivery workflow.
CORE_SOURCE='1b4f65e2067823a518034ef1ee1ba06a5b5abe09'
CORE_RUN=39163125594
PATCH='0fd83bccbdcfbe079236b47e1e3ebd674c70ecb06a2092f426cc88d0b769d843'
CORE_JOB='RPCS3 Core arm64 with NeoSwap client'
# Changed inputs proven by the Core run (published Core inputs and host tests).
TESTED={'build-utils/rpcs3/canonical-source.json','build-utils/rpcs3/embedded-core.patch',
    'test/neo_swap_core_pin_test.py','test/rpcs3_build444_core_delta_test.py',
    'test/rpcs3_build483_llvm_pipeline_test.py','test/native/rpcs3_llvm_pipeline_harness.cpp',
    '.github/workflows/rpcs3-core.yml'}
# Delivery wiring, records and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','docs/build483-llvm-pipelines.md','docs/evidence/llvmpipe483-delivery.json',
    'docs/evidence/llvm-pipeline-kernels-483.json',
    '.github/diagnostics/llvmpipe483_delivery.py','.github/workflows/retroarch-delivery.yml',
    '.github/workflows/neoswap-ipa.yml','build-utils/verify_delivery_reuse.py',
    'native/import-memory-candidate.json','test/import_memory_candidate_scope_test.py'}
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS

def source_closure():
    for end in (['HEAD'],[]):
        paths=set(base.command(['git','diff','--name-only',BASE,*end]).splitlines())
        extra=paths-TESTED-DELIVERY_ONLY
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        # Every tested input is byte-identical to the Core run source.
        base.command(['git','diff','--exit-code',CORE_SOURCE,*end,'--',*sorted(TESTED)])
        # The application product and the ARMSX2 Core inputs are the delivered Build 482;
        # only the candidate manifest changed under native/ and the RPCS3 canonical delta under build-utils/rpcs3.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        allowed={'native/import-memory-candidate.json','build-utils/rpcs3/canonical-source.json','build-utils/rpcs3/embedded-core.patch'}
        if changed-allowed:raise ValueError('Unexpected product change since Build 482: '+', '.join(sorted(changed-allowed)))
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS])
    manifest=json.loads((base.ROOT/'build-utils/rpcs3/canonical-source.json').read_text())
    patch=hashlib.sha256((base.ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes()).hexdigest()
    if manifest['patch_sha256']!=PATCH or patch!=PATCH:raise ValueError('Canonical Core delta differs from the Build 483 pin')
    record=manifest.get('llvm_pipelines')
    if not record or record['device_runtime_tested'] is not False or record['gameplay_validated'] is not False:
        raise ValueError('Build 483 manifest record missing or claiming device validation')
    if manifest['spu_object_cache']['device_runtime_tested'] is not False:raise ValueError('Build 481 record changed')
    return {'deliveredBaseline':DELIVERED,'baselineRecord':BASE,'coreSource':CORE_SOURCE,'coreRun':CORE_RUN,
        'canonicalPatchSHA256':PATCH,'changedProductPaths':[],'rpcs3CoreChanged':True,'armsx2CoreChanged':False,
        'precompiledEnginesHelpersCatalogueSkinsUnchanged':True}

@contextmanager
def rpc_core_input_view(pin):
    """Build 483 Core inputs were published with the current host header: no isolation view."""
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
    print('PASS all authentic RPCS3 Core inputs of the Build 483 pin')

def evidence():
    records=[base.successful_run(39157242359,DELIVERED,['checks','native','Release device build • cold']),
        base.successful_run(CORE_RUN,CORE_SOURCE,[CORE_JOB])]
    with tempfile.TemporaryDirectory(prefix='llvmpipe483-proof-') as tmp:
        subprocess.run(['gh','run','download',str(CORE_RUN),'--repo','TarbleFR/neostation-ios',
            '--name','RPCS3Core-diagnostics-'+CORE_SOURCE,'--dir',tmp],check=True)
        cache_proof=(Path(tmp)/'spu-object-cache-proof.txt').read_text()
        pipeline_proof=(Path(tmp)/'llvm-pipeline-proof.txt').read_text()
        kernels=json.loads((Path(tmp)/'llvm-pipeline-kernels.json').read_text())
        identity=json.loads((Path(tmp)/'identity.json').read_text())
    for needle in ('PASS: relocated external data, external call, rodata and pointer table across processes',
                   'PASS: truncated and foreign objects are rejected before MCJIT'):
        if needle not in cache_proof:raise ValueError('Build 481 preflight proof missing: '+needle)
    for needle in ('PASS: InstCombine erases a direct call with a mismatched convention (non-terminator unreachable)',
                   'PASS: 7 kernels x 5 pipelines verified','PASS: Build 483 LLVM pipelines (harness executed with 22.'):
        if needle not in pipeline_proof:raise ValueError('Build 483 preflight proof missing: '+needle)
    if kernels['all_variants_bit_exact'] is not True or len(kernels['kernels'])!=7:raise ValueError('Kernel report incomplete')
    if identity['host_commit']!=CORE_SOURCE or identity['source_patch_sha256']!=PATCH or identity['device_runtime_tested'] is not False:
        raise ValueError('Core identity differs from the pinned run')
    records[-1].update(cacheProofSHA256=hashlib.sha256(cache_proof.encode()).hexdigest(),
        pipelineProofSHA256=hashlib.sha256(pipeline_proof.encode()).hexdigest(),kernelsBitExact=True,
        coreSHA256=identity['sha256'],coreInputs=len(identity['core_input_sha256']))
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/ps2blend482-delivery.json','docs/evidence/spucache481-delivery.json')}
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
        print('PASS Build 483 source closure: application is the delivered Build 482, Core inputs match the pinned Core source')
        return
    records,receipts=evidence()
    record={'result':'passed','testedSHA':CORE_SOURCE,'candidateSHA':base.command(['git','rev-parse','HEAD']),
        'validationWasReused':True,'sourceClosure':closure,'reusedEvidence':records,'receiptSHA256':receipts,
        'deviceGameplayValidated':False,'coreRebuilt':True,'coreRun':CORE_RUN,'rebuiltCore':'RPCS3 (Build 483 LLVM pipelines)'}
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
    print('PASS delivered Build 482 application + Build 483 Core evidence; no suites rerun, one Core rebuilt')

if __name__=='__main__':
    main()
