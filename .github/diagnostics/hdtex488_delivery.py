"""Compose the delivered Build 487 with the Build 488 HD texture catalogue expansion and Nintendo 64 adapter.

Build 488 extends the unified HD texture catalogue of Build 486 (expanded
index, ps2ktxpak MIT notice) and adds the Mupen64Plus-Next (GLideN64) adapter
to the neo_texture_catalog pod: N64 ROM header identity, GLideN64 hi-res file
filters and folder detection, the per-game core options, the libretro in-game
"HD textures" row for Mupen64Plus-Next and the library row (see
docs/hd-textures-expansion-2026-10-19.md). No emulator Core is rebuilt: the
RPCS3 Core of Build 487, the ARMSX2 Core (ABI 8) of Build 485 and every other
engine, helper, skin and cheat input are the delivered Build 487 product. This
gate reads CI evidence; it never reruns suites. Each part (host, native, uikit)
of .github/workflows/hd-textures.yml must have passed on the tested source,
every tested input must be byte-identical to that source, and the verdicts
(BUILD 488) must cover every changed input.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import rpcs3diag487_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Branch head before this cycle's product push: the Build 487 delivery record on Claude.
BASE='b6c39807195efdb6ecb08b71f4e5b3f42d0a4e0e'
# Build 487 source and its delivery run (checks/native reused, cold Release).
DELIVERED='fad5eac6f793672240d2cb5f3559da73a40226f8'
DELIVERED_RUN=39262042654
# Build 488 source tested by hd-textures.yml. Each part: (run, source, job).
TESTED_SOURCE=''
PROOFS={
    'host':(0,TESTED_SOURCE,'Readers, identities, installer, labels, catalogue, contracts and Flutter'),
    'native':(0,TESTED_SOURCE,'Store and adapters on Foundation, iPhone SDK build of every changed source'),
    'uikit':(0,TESTED_SOURCE,'The HD textures page on UIKit with the bundled catalogue'),
}
PARTS=('host','native','uikit')

sys.path.insert(0,str(base.ROOT/'test'))
import build486_targeted_test as targeted  # noqa: E402
# The product files Build 488 changes (every one is in the runner's product list).
PRODUCT={
    'lib/services/texture_catalog_service.dart',
    'lib/widgets/libretro_internal_playlist_actions.dart',
    'native/textures/catalogue/manifest.json.gz',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureCatalogPlugin.m',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureEngines.mm',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureHDPage.m',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureIdentity.h',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureIdentityReader.mm',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureInstall.h',
    'packages/neo_texture_catalog/ios/Classes/NeoTexturePackStore.mm',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureSupport.h',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureSupport.m',
    'packages/neo_texture_catalog/ios/Classes/Public/NeoTextureEngine.h',
    'packages/neo_texture_catalog/ios/Classes/Public/NeoTextureHDPage.h',
    'packages/neo_texture_catalog/ios/Resources/labels.json',
    'packages/neo_texture_catalog/ios/Resources/manifest.json.gz',
    'packages/neo_texture_catalog/ios/Resources/ps2ktxpak-LICENSE.txt',
    'packages/neo_texture_catalog/ios/neo_texture_catalog.podspec',
}
TESTED=(set(targeted.PRODUCT)|set(targeted.SUPPORT)|set(targeted.HOST_PYTHON)|set(targeted.DART_TESTS)|set(targeted.PRE_EXISTING)
        |{command[0] for command in targeted.CATALOGUE+targeted.NATIVE+targeted.UIKIT})
# Delivery wiring, records, credits and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','docs/hd-textures-expansion-2026-10-19.md','docs/evidence/hdtex488-delivery.json',
    'docs/HD_TEXTURE_CATALOG_SOURCES.md','.github/diagnostics/hdtex488_delivery.py',
    # Records of the Build 487 delivery, written by its session after this cycle began.
    'docs/build487-plan.md','docs/evidence/rpcs3diag487-delivery.json','docs/rpcs3-bottleneck-audit-2026-10-18.md',
    '.github/workflows/retroarch-delivery.yml','.github/workflows/neoswap-ipa.yml','build-utils/verify_delivery_reuse.py'}
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS
RPCS3_CORE_PATHS=['build-utils/rpcs3','packages/rpcs3_internal_bridge']

def part_inputs(part):
    # The files a part's verdict digests (build486_targeted_test.py: product, support, its checks).
    tested={'host':targeted.HOST_PYTHON+targeted.DART_TESTS+targeted.PRE_EXISTING+[c[0] for c in targeted.CATALOGUE],
            'native':[command[0] for command in targeted.NATIVE],
            'uikit':[command[0] for command in targeted.UIKIT]}[part]
    return set(targeted.PRODUCT)|set(targeted.SUPPORT)|set(tested)

def source_closure():
    for name,value in (('BASE',BASE),('DELIVERED',DELIVERED),('TESTED_SOURCE',TESTED_SOURCE)):
        if len(value)!=40:raise ValueError(f'{name} is not pinned yet')
    if not DELIVERED_RUN:raise ValueError('DELIVERED_RUN is not pinned yet')
    for part,(run,source,job) in PROOFS.items():
        if not run or len(source)!=40:raise ValueError(f'{part} proof is not pinned yet')
    if not PRODUCT<=set(targeted.PRODUCT):raise ValueError('A Build 488 product file is outside the targeted runner')
    for end in (['HEAD'],[]):
        paths=set(base.command(['git','diff','--name-only',BASE,*end]).splitlines())
        extra=paths-TESTED-DELIVERY_ONLY
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        # Every tested input is byte-identical to the tested source.
        base.command(['git','diff','--exit-code',TESTED_SOURCE,*end,'--',*sorted(TESTED)])
    for part,(run,source,job) in PROOFS.items():
        if source!=TESTED_SOURCE:
            base.command(['git','diff','--exit-code',source,TESTED_SOURCE,'--',*sorted(part_inputs(part))])
    for end in (['HEAD'],[]):
        # The product differs from delivered 487 exactly by the Build 488 texture files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        # Catalogue tooling (sources, verification records, research) is never packaged;
        # it is part of the tested inputs above.
        changed-={path for path in changed if path.startswith('tools/textures/')}
        if changed!=PRODUCT:raise ValueError('Unexpected product change since Build 487: '+', '.join(sorted(changed^PRODUCT)))
        # No Core input changed: the RPCS3 Core and bridge of Build 487, the ARMSX2 Core of Build 485.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*RPCS3_CORE_PATHS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS])
    manifest=json.loads((base.ROOT/'build-utils/rpcs3/canonical-source.json').read_text())
    patch=hashlib.sha256((base.ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes()).hexdigest()
    if manifest['patch_sha256']!=previous.PATCH or patch!=previous.PATCH:raise ValueError('RPCS3 Core delta differs from the Build 487 pin')
    hosted=(base.ROOT/'native/textures/catalogue/manifest.json.gz').read_bytes()
    bundled=(base.ROOT/'packages/neo_texture_catalog/ios/Resources/manifest.json.gz').read_bytes()
    if hosted!=bundled:raise ValueError('Bundled and hosted HD texture catalogues differ')
    return {'deliveredBaseline':DELIVERED,'baselineRecord':BASE,'testedSource':TESTED_SOURCE,
        'targetedRuns':{part:{'run':run,'source':source} for part,(run,source,job) in PROOFS.items()},
        'rpcs3CorePin':previous.CORE_SOURCE,'rpcs3CoreRun':previous.CORE_RUN,'rpcs3CanonicalPatchSHA256':previous.PATCH,
        'catalogueSHA256':hashlib.sha256(hosted).hexdigest(),'changedProductPaths':sorted(PRODUCT),'coreRebuilt':False,
        'otherEnginesCataloguesSkinsHelpersUnchanged':True}

# The Core pins are Build 487's: reuse its exact input view and identity checks.
rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin

def part_run(run_id,ref,name):
    # One part of hd-textures.yml: its own job must have passed on that source.
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
    with tempfile.TemporaryDirectory(prefix='hdtex488-proof-') as tmp:
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
        if verdict['result']!='passed' or verdict['source']!=PROOFS[part][1] or verdict['build']!=488 or verdict['part']!=part:
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
    missing={p for p in TESTED if (base.ROOT/p).is_file()}-covered
    if missing:raise ValueError('Targeted proof did not close: '+', '.join(sorted(missing)))
    native=verdicts['native'][0]
    if native['xcode']!='Xcode 26.3\nBuild version 17C529' or native['iphoneSDK']!='26.2':
        raise ValueError('Targeted native checks ran on another toolchain')
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/rpcs3diag487-delivery.json','docs/evidence/hdcat486-delivery.json') if (base.ROOT/p).is_file()}
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
        print('PASS Build 488 source closure: delivered 487 product + tested HD texture catalogue changes, no Core input changed')
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
    print('PASS delivered 487 product + Build 488 HD texture catalogue targeted evidence; no suites rerun, no Core rebuilt')

if __name__=='__main__':
    main()
