"""Compose the delivered Build 492 with the Build 493 3D boxes of the library.

Build 493 is the delivered Build 492 (Dusklight and Ports removal) plus, at the maintainer's request of
20 October 2026 (docs/build493-plan.md, docs/game-box-3d.md § 3 and § 11):
- the 3D boxes in the three library views (carousel, grid, list), sharing
  one card, one viewer and one opening before the usual launch;
- the glowing halo kept only on the List view's selected title;
- the viewer's Back button (manual → open box → box → library), its flat
  view of the back and "Recenter";
- "Open the box" (the inside without a launch) and the game's local PDF
  manual lying in it, taken out and read in NeoStation's manual reader, or
  downloaded on request through the same path as Game Settings › Manual.
No emulator Core is rebuilt and no native input changes (engines, bridges,
the neo_box_reader plugin, helpers, catalogues): they are the delivered
Build 492 product. This gate reads CI evidence; it never reruns suites. The
host part of .github/workflows/build493-checks.yml must have passed on the
delivery commit or on an ancestor differing only by records, every tested
input must be byte-identical to the delivered tree, and the verdict (BUILD 493)
must cover every changed input.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import portsremoval492_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Build 492 source (Dusklight and Ports removal, another session) and its delivery
# run (checks/native, cold Release): pinned once that delivery is recorded.
DELIVERED='b1ca2a97bd212594d9602929b725742c42891787'
DELIVERED_RUN=None
# Every change of this cycle is counted from the delivered 492 source.
BASE=DELIVERED
WORKFLOW='build493-checks.yml'
JOBS={'host':'Analysis, delivery Dart suite, game box and library view checks'}
PARTS=('host',)
# Delivery wiring, records, workflows and pins: no product or tested input.
DELIVERY_ONLY={'AGENTS.md','README.md','.github/diagnostics/gamebox493_delivery.py',
    'build-utils/delivery-493-recipient.pem'}
WORKFLOWS_PREFIX='.github/workflows/'
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS
RPCS3_CORE_PATHS=previous.RPCS3_CORE_PATHS

sys.path.insert(0,str(base.ROOT/'test'))
import build493_targeted_test as targeted  # noqa: E402
# The product files Build 493 changes: the runner's product list, every one of them.
PRODUCT=set(targeted.PRODUCT)


def tested_paths():
    """Every non-documentation path changed since Build 492 that is not delivery wiring."""
    paths=set(base.command(['git','diff','--name-only',BASE,'HEAD']).splitlines())
    return {path for path in paths if not path.startswith('docs/') and path not in DELIVERY_ONLY
            and not path.startswith(WORKFLOWS_PREFIX)}


def records_only(path):
    # Documentation and delivery records: never packaged, never a tested input.
    return path.startswith('docs/') or path in DELIVERY_ONLY


def proofs(head):
    """The latest successful build493-checks.yml run on HEAD, or on an ancestor of
    HEAD when every commit since only touched documentation or delivery wiring.
    evidence() still compares every verdict input with the files of HEAD."""
    runs=base.api(f'actions/workflows/{WORKFLOW}/runs?status=success&per_page=50')['workflow_runs']
    for run in sorted(runs,key=lambda r:r['run_number']*100+r['run_attempt'],reverse=True):
        source=run['head_sha']
        if run['conclusion']!='success':continue
        if subprocess.run(['git','merge-base','--is-ancestor',source,head],cwd=base.ROOT).returncode!=0:continue
        since=set(base.command(['git','diff','--name-only',source,head]).splitlines())
        if all(records_only(path) for path in since):
            return {part:(run['id'],source,job) for part,job in JOBS.items()}
    raise ValueError('No successful '+WORKFLOW+' run on '+head+' or on an ancestor differing only by records')


def source_closure():
    source=base.command(['git','rev-parse','HEAD'])
    if len(DELIVERED)!=40 or DELIVERED_RUN is None:raise ValueError('The delivered Build 492 is not pinned')
    tested=tested_paths()
    # The working tree is the tested commit (nothing edited after checkout).
    base.command(['git','diff','--exit-code','HEAD','--',*sorted(tested)])
    for end in (['HEAD'],[]):
        # The product differs from delivered 492 exactly by the Build 493 files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        if changed!=PRODUCT:raise ValueError('Unexpected product change since Build 492: '+', '.join(sorted(changed^PRODUCT)))
        # No Core input changed: the RPCS3 and ARMSX2 Cores, the libretro cores package.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*RPCS3_CORE_PATHS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--','build-utils/libretro'])
        # No native input at all: every package, native source and the iOS project
        # are the delivered 492 ones (the box reader plugin included).
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--','packages','native','ios'])
    # KartPad and Dusklight stay removed.
    for gone in ('packages/kartpad_internal_bridge','native/kartpad','build-utils/kartpad',
                 'lib/services/kartpad_internal_service.dart','packages/dusklight_internal_bridge','native/dusklight',
                 'build-utils/dusklight','lib/services/dusklight_internal_service.dart'):
        if base.command(['git','ls-files','--',gone]):raise ValueError('A removed port came back: '+gone)
    return {'deliveredBaseline':DELIVERED,'deliveredRun':DELIVERED_RUN,'baselineRecord':BASE,'testedSource':source,
        'changedProductPaths':sorted(PRODUCT),'coreRebuilt':False,'nativeInputsUnchanged':True,
        'otherEnginesCataloguesSkinsHelpersUnchanged':True}

rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin
part_run=previous.part_run


def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold'])]
    PROOFS=proofs(base.command(['git','rev-parse','HEAD']))
    verdicts={}
    with tempfile.TemporaryDirectory(prefix='gamebox493-proof-') as tmp:
        for part in PARTS:
            run,source,job=PROOFS[part]
            records.append(part_run(run,source,job))
            folder=Path(tmp)/part
            subprocess.run(['gh','run','download',str(run),'--repo','TarbleFR/neostation-ios',
                '--name',f'build493-{part}-'+source,'--dir',str(folder)],check=True)
            files=list(folder.rglob(f'{part}-verdict.json'))
            if len(files)!=1:raise ValueError('Ambiguous or missing verdict: '+part)
            raw=files[0].read_bytes();verdicts[part]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
    covered=set()
    for part,(verdict,digest) in verdicts.items():
        if verdict['result']!='passed' or verdict['source']!=PROOFS[part][1] or verdict['build']!=493 or verdict['part']!=part:
            raise ValueError('Wrong targeted proof identity/result: '+part)
        if verdict['coreRebuilt'] is not False or verdict['deviceValidated'] is not False:
            raise ValueError('Targeted verdict claims more than it ran: '+part)
        for path,sha in verdict['inputsSHA256'].items():
            if hashlib.sha256((base.ROOT/path).read_bytes()).hexdigest()!=sha:
                raise ValueError('Changed tested input '+path)
        covered|=set(verdict['inputsSHA256'])
        records.append({'part':part,'run':PROOFS[part][0],'job':PROOFS[part][2],'source':PROOFS[part][1],'verdictSHA256':digest,
            'checks':verdict['checks'],'timingsSeconds':verdict['timingsSeconds']})
    missing={p for p in tested_paths() if (base.ROOT/p).is_file()}-covered
    # The verdict lists what the part read; every tested input must be covered.
    if missing:raise ValueError('Targeted proof did not close: '+', '.join(sorted(missing)))
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/gamebox490-delivery.json',) if (base.ROOT/p).is_file()}
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
        print('PASS Build 493 source closure: delivered 492 product + 3D boxes of the library and the manual in the box, no native input changed')
        return
    records,receipts,PROOFS=evidence()
    closure['targetedRuns']={part:{'run':run,'source':source,'job':job} for part,(run,source,job) in PROOFS.items()}
    closure['testedSource']=PROOFS['host'][1]
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
    print('PASS delivered 492 product + Build 493 targeted evidence; no suites rerun, no Core rebuilt')

if __name__=='__main__':
    main()
