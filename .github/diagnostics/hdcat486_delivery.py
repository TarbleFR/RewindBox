"""Compose the delivered Build 485 with the Build 486 unified HD texture catalogue and its targeted proofs.

Build 486 adds the neo_texture_catalog pod (catalogue, pack store, engine
adapters for ARMSX2, Dolphin, PPSSPP and Azahar, the shared HD textures page),
opens it from the in-game menus, the console import menus and a game's
settings, and ships the first catalogue (native/textures/catalogue, verified
against the authors' real files). No emulator Core is rebuilt: the ARMSX2 Core
(ABI 8) of Build 485, the RPCS3 Core of Build 483 and every other engine,
helper, catalogue and skin input are the delivered Build 485 product. This gate
reads CI evidence; it never reruns suites. Each of the three parts (host,
native, uikit) of .github/workflows/hd-textures.yml must have passed on the
tested source (or on a source whose part inputs are byte-identical), every
tested input must be byte-identical to the tested source, and the verdicts
must cover every changed input.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import hdtex485_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Branch head before this cycle: the Build 485 delivery record on Claude.
BASE='dc653f12eb5d09ea15d7a618576eecc4e1674c04'
# Build 485 source and its delivery run (checks/native reused, cold Release).
DELIVERED='85a28e9013eaf7613da0338b4bc44f5ab7268f10'
DELIVERED_RUN=39182252832
# Build 486 source tested by hd-textures.yml. Each part: (run, source, job).
TESTED_SOURCE=''
PROOFS={
    'host':(0,TESTED_SOURCE,'Readers, identities, installer, labels, catalogue, contracts and Flutter'),
    'native':(0,TESTED_SOURCE,'Store and adapters on Foundation, iPhone SDK build of every changed source'),
    'uikit':(0,TESTED_SOURCE,'The HD textures page on UIKit with the bundled catalogue'),
}
PARTS=('host','native','uikit')

sys.path.insert(0,str(base.ROOT/'test'))
import build486_targeted_test as targeted  # noqa: E402
PRODUCT=set(targeted.PRODUCT)
TESTED=(PRODUCT|set(targeted.SUPPORT)|set(targeted.HOST_PYTHON)|set(targeted.DART_TESTS)|set(targeted.PRE_EXISTING)
        |{command[0] for command in targeted.CATALOGUE+targeted.NATIVE+targeted.UIKIT})
# Delivery wiring, records, credits and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','docs/build486-hd-textures-catalogue.md','docs/evidence/hdcat486-delivery.json',
    'docs/HD_TEXTURE_CATALOG_SOURCES.md','docs/LEGAL_AND_CREDITS.md','.github/diagnostics/hdcat486_delivery.py',
    '.github/workflows/retroarch-delivery.yml','.github/workflows/neoswap-ipa.yml','build-utils/verify_delivery_reuse.py'}
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS

def part_inputs(part):
    # The files a part's verdict digests (build486_targeted_test.py: product, support, its checks).
    tested={'host':targeted.HOST_PYTHON+targeted.DART_TESTS+targeted.PRE_EXISTING+[c[0] for c in targeted.CATALOGUE],
            'native':[command[0] for command in targeted.NATIVE],
            'uikit':[command[0] for command in targeted.UIKIT]}[part]
    return PRODUCT|set(targeted.SUPPORT)|set(tested)

def source_closure():
    for name,value in (('BASE',BASE),('DELIVERED',DELIVERED),('TESTED_SOURCE',TESTED_SOURCE)):
        if len(value)!=40:raise ValueError(f'{name} is not pinned yet')
    for part,(run,source,job) in PROOFS.items():
        if not run or len(source)!=40:raise ValueError(f'{part} proof is not pinned yet')
    for end in (['HEAD'],[]):
        paths=set(base.command(['git','diff','--name-only',BASE,*end]).splitlines())
        extra=paths-TESTED-DELIVERY_ONLY
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        # Every tested input is byte-identical to the tested source.
        base.command(['git','diff','--exit-code',TESTED_SOURCE,*end,'--',*sorted(TESTED)])
    # A part proven on another source is reused only if none of its inputs changed.
    for part,(run,source,job) in PROOFS.items():
        if source!=TESTED_SOURCE:
            base.command(['git','diff','--exit-code',source,TESTED_SOURCE,'--',*sorted(part_inputs(part))])
    for end in (['HEAD'],[]):
        # The product differs from delivered 485 exactly by the Build 486 product files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        if changed!=PRODUCT:raise ValueError('Unexpected product change since Build 485: '+', '.join(sorted(changed^PRODUCT)))
        # No Core input changed: the ARMSX2 Core of Build 485 (ABI 8) and the RPCS3 delta of Build 483.
        base.command(['git','diff','--exit-code',previous.CORE_SOURCE,*end,'--',*ARMSX2_CORE_INPUTS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',
                      'build-utils/rpcs3','packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreABI.h'])
    pin=previous.previous.previous  # llvmpipe483_delivery: the RPCS3 Core pin
    manifest=json.loads((base.ROOT/'build-utils/rpcs3/canonical-source.json').read_text())
    patch=hashlib.sha256((base.ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes()).hexdigest()
    if manifest['patch_sha256']!=pin.PATCH or patch!=pin.PATCH:raise ValueError('RPCS3 Core delta differs from the Build 483 pin')
    source=json.loads((base.ROOT/'build-utils/armsx2/source.json').read_text())
    if source['revision']!=previous.ARMSX2_REVISION or source['abi_version']!=8:raise ValueError('ARMSX2 2.6 pin or ABI 8 changed')
    # The hosted and bundled catalogues are the same bytes.
    hosted=(base.ROOT/'native/textures/catalogue/manifest.json.gz').read_bytes()
    bundled=(base.ROOT/'packages/neo_texture_catalog/ios/Resources/manifest.json.gz').read_bytes()
    if hosted!=bundled:raise ValueError('Bundled and hosted HD texture catalogues differ')
    return {'deliveredBaseline':DELIVERED,'baselineRecord':BASE,'testedSource':TESTED_SOURCE,
        'targetedRuns':{part:{'run':run,'source':source} for part,(run,source,job) in PROOFS.items()},
        'armsx2CorePin':previous.CORE_SOURCE,'armsx2CoreRun':previous.CORE_RUN,'rpcs3CorePin':pin.CORE_SOURCE,
        'rpcs3CanonicalPatchSHA256':pin.PATCH,'catalogueSHA256':hashlib.sha256(hosted).hexdigest(),
        'changedProductPaths':sorted(PRODUCT),'coreRebuilt':False,'otherEnginesCataloguesSkinsHelpersUnchanged':True}

# The Core pins are Build 485's: reuse its exact input view and identity checks.
rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin

def part_run(run_id,ref,name):
    # One part of hd-textures.yml: its own job must have passed on that source
    # (another part of the same run may have been proven by a later run).
    run=base.api(f'actions/runs/{run_id}')
    if run['head_sha']!=ref or run['status']!='completed':
        raise ValueError('Wrong targeted run identity/status: '+str(run_id))
    jobs=[j for j in base.api(f'actions/runs/{run_id}/jobs?per_page=100')['jobs'] if j['name']==name]
    if len(jobs)!=1 or jobs[0]['conclusion']!='success':
        raise ValueError('Unsuccessful targeted part: '+name)
    return {'run':run_id,'source':ref,'jobs':[name],'overallConclusion':run['conclusion']}

def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold'])]
    verdicts={}
    with tempfile.TemporaryDirectory(prefix='hdcat486-proof-') as tmp:
        for part in PARTS:
            run,source,job=PROOFS[part]
            records.append(part_run(run,source,job))
            folder=Path(tmp)/part
            subprocess.run(['gh','run','download',str(run),'--repo','TarbleFR/neostation-ios',
                '--name',f'build486-{part}-'+source,'--dir',str(folder)],check=True)
            files=list(folder.rglob(f'{part}-verdict.json'))
            if len(files)!=1:raise ValueError('Ambiguous or missing verdict: '+part)
            raw=files[0].read_bytes();verdicts[part]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
    covered=set()
    for part,(verdict,digest) in verdicts.items():
        if verdict['result']!='passed' or verdict['source']!=PROOFS[part][1] or verdict['build']!=486 or verdict['part']!=part:
            raise ValueError('Wrong targeted proof identity/result: '+part)
        if verdict['coreRebuilt'] is not False or verdict['deviceValidated'] is not False:
            raise ValueError('Targeted verdict claims more than it ran: '+part)
        for path,sha in verdict['inputsSHA256'].items():
            if hashlib.sha256((base.ROOT/path).read_bytes()).hexdigest()!=sha:
                raise ValueError('Changed tested input '+path)
        covered|=set(verdict['inputsSHA256'])
        records.append({'part':part,'run':PROOFS[part][0],'source':PROOFS[part][1],'verdictSHA256':digest,'checks':verdict['checks'],
            'timingsSeconds':verdict['timingsSeconds'],
            **({'preExistingComparison':verdict['preExistingComparison']} if 'preExistingComparison' in verdict else {})})
    missing=TESTED-covered
    if missing:raise ValueError('Targeted proof did not close: '+', '.join(sorted(missing)))
    native=verdicts['native'][0]
    if native['xcode']!='Xcode 26.3\nBuild version 17C529' or native['iphoneSDK']!='26.2':
        raise ValueError('Targeted native checks ran on another toolchain')
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/hdtex485-delivery.json','docs/evidence/touch484-delivery.json','docs/evidence/llvmpipe483-delivery.json')
        if (base.ROOT/p).is_file()}
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
        print('PASS Build 486 source closure: delivered 485 product + tested HD texture catalogue changes, no Core input changed')
        return
    records,receipts=evidence()
    record={'result':'passed','testedSHA':TESTED_SOURCE,'candidateSHA':base.command(['git','rev-parse','HEAD']),
        'validationWasReused':True,'sourceClosure':closure,'reusedEvidence':records,'receiptSHA256':receipts,
        'deviceGameplayValidated':False,'coreRebuilt':False}
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
    print('PASS delivered 485 product + Build 486 HD texture catalogue targeted evidence; no suites rerun, no Core rebuilt')

if __name__=='__main__':
    main()
