"""Compose the delivered Build 489 with the Build 490 3D game box (Jaquette view).

Build 490 shows the games of the carousel's Box card style as boxes of their
console's family, adds the full-screen box viewer (360° turn, tilt, zoom,
Front/Back/Reset, reading pose), the box opening before the usual launch, the
box faces and editions fetched from ScreenScraper through the scraper's own
client, and the multilingual back reader (neo_box_reader: Vision,
NaturalLanguage and Apple Translation on the device). See
docs/game-box-3d.md. No emulator Core is rebuilt and no engine, helper, skin,
cheat or texture input changes: they are the delivered Build 489 product.
This gate reads CI evidence; it never reruns suites. Each part (host, native)
of .github/workflows/game-box-checks.yml must have passed on the tested
source, every tested input must be byte-identical to that source, and the
verdicts (BUILD 490) must cover every changed input.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import hdtex489_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Build 489 source and its delivery run (checks/native reused, cold Release). The
# Build 490 delivery ref (tag build-490) is this exact source plus the 490 commits
# only: the later commits of other sessions on Claude are not part of Build 490.
DELIVERED='a8065a993c0a9f791c40bad75c44726fa63e161d'
DELIVERED_RUN=39340720047
# Every change of this cycle is counted from the delivered 489 source.
BASE=DELIVERED
# The tested source is the delivery commit itself: game-box-checks.yml is dispatched
# on the build-490 tag, so its parts ran on exactly the tree packaged here. Each part:
# the job that must have passed in a successful run of that workflow on HEAD.
WORKFLOW='game-box-checks.yml'
JOBS={
    'host':'Texts, geometry, media, reader and inspector on Flutter',
    'native':'Vision, NaturalLanguage and Translation on macOS and the iOS Simulator; iPhone SDK type check',
}
PARTS=('host','native')

sys.path.insert(0,str(base.ROOT/'test'))
import game_box_targeted_test as targeted  # noqa: E402
# The product files Build 490 changes: the runner's product list, every one of them.
PRODUCT=set(targeted.PRODUCT)
TESTED=(set(targeted.PRODUCT)|set(targeted.SUPPORT)|set(targeted.HOST_PYTHON)|set(targeted.DART_TESTS)
        |{targeted.NATIVE_MAIN})
# Delivery wiring, records and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','.github/diagnostics/gamebox490_delivery.py',
    '.github/workflows/retroarch-delivery.yml','.github/workflows/neoswap-ipa.yml','build-utils/verify_delivery_reuse.py',
    # Render previews written only when GAME_BOX_RENDER_DIR is set (manual inspection).
    'test/game_box_render_preview_test.dart','test/game_box_render_inspector_preview_test.dart'}
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS
RPCS3_CORE_PATHS=previous.RPCS3_CORE_PATHS

def part_inputs(part):
    tested={'host':targeted.HOST_PYTHON+targeted.DART_TESTS,'native':[targeted.NATIVE_MAIN]}[part]
    return set(targeted.PRODUCT)|set(targeted.SUPPORT)|set(tested)

def tested_source():
    return base.command(['git','rev-parse','HEAD'])

def proofs(source):
    # The latest completed, successful run of the targeted workflow on this exact commit.
    runs=base.api(f'actions/workflows/{WORKFLOW}/runs?head_sha={source}&status=success&per_page=20')['workflow_runs']
    runs=[r for r in runs if r['head_sha']==source and r['conclusion']=='success']
    if not runs:raise ValueError('No successful '+WORKFLOW+' run on '+source)
    run=max(runs,key=lambda r:r['run_number']*100+r['run_attempt'])['id']
    return {part:(run,source,job) for part,job in JOBS.items()}

def source_closure():
    source=tested_source()
    for name,value in (('BASE',BASE),('DELIVERED',DELIVERED)):
        if len(value)!=40:raise ValueError(f'{name} is not pinned')
    for end in (['HEAD'],[]):
        paths=set(base.command(['git','diff','--name-only',BASE,*end]).splitlines())
        # Documentation and records (docs/, AGENTS.md) are never packaged nor tested inputs.
        extra={path for path in paths-TESTED-DELIVERY_ONLY if not path.startswith('docs/')}
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
    # The working tree is the tested commit (nothing edited after checkout).
    base.command(['git','diff','--exit-code','HEAD','--',*sorted(TESTED)])
    for end in (['HEAD'],[]):
        # The product differs from delivered 489 exactly by the Build 490 files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        # The strings generator is never packaged; it is a tested input above.
        changed-={path for path in changed if path.startswith('tools/game_box/')}
        expected={path for path in PRODUCT if not path.startswith('tools/game_box/')}
        if changed!=expected:raise ValueError('Unexpected product change since Build 489: '+', '.join(sorted(changed^expected)))
        # No Core input changed: the RPCS3 and ARMSX2 Cores, the libretro cores package.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*RPCS3_CORE_PATHS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--','build-utils/libretro'])
        # The HD texture catalogue, its engines and the bridges are the delivered 489 ones.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--','packages/neo_texture_catalog','native/textures',
            'packages/libretro_internal_bridge','packages/dolphin_internal_bridge','packages/armsx2_internal_bridge',
            'packages/rpcs3_internal_bridge'])
    return {'deliveredBaseline':DELIVERED,'deliveredRun':DELIVERED_RUN,'baselineRecord':BASE,'testedSource':source,
        'changedProductPaths':sorted(PRODUCT),'coreRebuilt':False,
        'otherEnginesCataloguesSkinsHelpersUnchanged':True}

rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin
part_run=previous.part_run

def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold'])]
    PROOFS=proofs(tested_source())
    verdicts={}
    with tempfile.TemporaryDirectory(prefix='gamebox490-proof-') as tmp:
        for part in PARTS:
            run,source,job=PROOFS[part]
            records.append(part_run(run,source,job))
            folder=Path(tmp)/part
            subprocess.run(['gh','run','download',str(run),'--repo','TarbleFR/RewindBox',
                '--name',f'gamebox-{part}-'+source,'--dir',str(folder)],check=True)
            files=list(folder.rglob(f'{part}-verdict.json'))
            if len(files)!=1:raise ValueError('Ambiguous or missing verdict: '+part)
            raw=files[0].read_bytes();verdicts[part]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
    covered=set()
    for part,(verdict,digest) in verdicts.items():
        if verdict['result']!='passed' or verdict['source']!=PROOFS[part][1] or verdict['build']!=490 or verdict['part']!=part:
            raise ValueError('Wrong targeted proof identity/result: '+part)
        if verdict['coreRebuilt'] is not False or verdict['deviceValidated'] is not False:
            raise ValueError('Targeted verdict claims more than it ran: '+part)
        for path,sha in verdict['inputsSHA256'].items():
            if hashlib.sha256((base.ROOT/path).read_bytes()).hexdigest()!=sha:
                raise ValueError('Changed tested input '+path)
        covered|=set(verdict['inputsSHA256'])
        records.append({'part':part,'run':PROOFS[part][0],'job':PROOFS[part][2],'source':PROOFS[part][1],'verdictSHA256':digest,
            'checks':verdict['checks'],'timingsSeconds':verdict['timingsSeconds']})
    missing={p for p in TESTED if (base.ROOT/p).is_file()}-covered
    # Verdicts list what each part read; every tested input must be covered by one.
    if missing:raise ValueError('Targeted proof did not close: '+', '.join(sorted(missing)))
    native=verdicts['native'][0]
    if native['xcode']!='Xcode 26.3\nBuild version 17C529' or native['iphoneSDK']!='26.2':
        raise ValueError('Targeted native checks ran on another toolchain')
    reports=native.get('reports') or {}
    for name in ('macos','iosSimulator'):
        report=reports.get(name) or {}
        if report.get('passed') is not True or len(report.get('samples') or [])!=12:
            raise ValueError('Native recognition report incomplete: '+name)
    records.append({'part':'recognition','macosTranslation':reports['macos'].get('translation'),
        'iosSimulatorRuntime':reports['iosSimulator'].get('runtime'),
        'similarities':{name:{s['code']:s.get('similarity') for s in reports[name]['samples']} for name in ('macos','iosSimulator')}})
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/hdtex489-delivery.json','docs/evidence/hdtex488-delivery.json') if (base.ROOT/p).is_file()}
    return records,receipts,PROOFS

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
        print('PASS Build 490 source closure: delivered 489 product + tested 3D game box changes, no Core input changed')
        return
    records,receipts,PROOFS=evidence()
    closure['targetedRuns']={part:{'run':run,'source':source,'job':job} for part,(run,source,job) in PROOFS.items()}
    record={'result':'passed','testedSHA':closure['testedSource'],'candidateSHA':base.command(['git','rev-parse','HEAD']),
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
    print('PASS delivered 489 product + Build 490 3D game box targeted evidence; no suites rerun, no Core rebuilt')

if __name__=='__main__':
    main()
