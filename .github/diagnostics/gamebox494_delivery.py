"""Compose the delivered Build 493 with the Build 494 legibility of the box backs.

Build 494 is the delivered Build 493 (3D boxes in the three views) plus, at the maintainer's request of
20 October 2026 (docs/build494-plan.md, docs/game-box-3d.md § 12):
- the back read straight on, and the flat view, shown as made for the exact
  size they cover on the screen (Mitchell-Netravali resampling instead of
  the GPU's trilinear filtering of a larger decode), with an optional light
  sharpening of the brightness ("Sharp text", on by default);
- in portrait, the viewer's panel limited to a share of the height so that
  the box, and its back, are drawn larger (Play stays shown);
- the box reader's recognizer: the Build 493 reading unchanged, then a small
  print pass (minimum text height, small scans enlarged for Vision only) whose
  lines are only added where the first reading found none; cached transcripts
  read again once.
No emulator Core is rebuilt; the only native input that changes is the
neo_box_reader plugin's recognizer. This gate reads CI evidence; it never
reruns suites. The host and native parts of .github/workflows/build494-checks.yml
must have passed on the delivery commit or on an ancestor differing only by
records, every tested input must be byte-identical to the delivered tree, and
the verdicts (BUILD 494) must cover every changed input.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import gamebox493_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Build 493 source (the f181a123 product, its checks and gate, plus the 492
# delivery records of another session) and its delivery run (checks/native,
# cold Release).
DELIVERED='013d32ed0238922dcabe57aca407a6e4b49c82f5'
DELIVERED_RUN=39359025363
# Every change of this cycle is counted from the delivered 493 source.
BASE=DELIVERED
WORKFLOW='build494-checks.yml'
JOBS={'host':'Analysis, delivery Dart suite, sharp back and game box checks',
      'native':'Vision small print (Build 493 control and Build 494) on macOS and the iOS Simulator; iPhone SDK type check'}
PARTS=('host','native')
# Delivery wiring, records, workflows and pins: no product or tested input.
DELIVERY_ONLY={'AGENTS.md','README.md','.github/diagnostics/gamebox494_delivery.py',
    'build-utils/delivery-494-recipient.pem'}
WORKFLOWS_PREFIX='.github/workflows/'
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS
RPCS3_CORE_PATHS=previous.RPCS3_CORE_PATHS

sys.path.insert(0,str(base.ROOT/'test'))
import build494_targeted_test as targeted  # noqa: E402
# The product files Build 494 changes: the runner's product list, every one of them.
PRODUCT=set(targeted.PRODUCT)
NATIVE_PRODUCT=set(targeted.NATIVE_PRODUCT)
# Files another session changed since Build 493, neither packaged nor tested
# by this build (the runner's list, path by path).
OTHER_SESSION=set(targeted.OTHER_SESSION)
OTHER_PRODUCT_PATHS={p for p in OTHER_SESSION if any(p==q or p.startswith(q+'/') for q in PRODUCT_PATHS)}


def tested_paths():
    """Every non-documentation path changed since Build 493 that is not delivery wiring."""
    paths=set(base.command(['git','diff','--name-only',BASE,'HEAD']).splitlines())
    return {path for path in paths if not path.startswith('docs/') and path not in DELIVERY_ONLY
            and not path.startswith(WORKFLOWS_PREFIX) and path not in OTHER_SESSION}


def records_only(path):
    # Documentation and delivery records: never packaged, never a tested input.
    return path.startswith('docs/') or path in DELIVERY_ONLY


def proofs(head):
    """The latest successful build494-checks.yml run on HEAD, or on an ancestor of
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
    if len(DELIVERED)!=40 or DELIVERED_RUN is None:raise ValueError('The delivered Build 493 is not pinned')
    tested=tested_paths()
    # The working tree is the tested commit (nothing edited after checkout).
    base.command(['git','diff','--exit-code','HEAD','--',*sorted(tested)])
    for end in (['HEAD'],[]):
        # The product differs from delivered 493 exactly by the Build 494 files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        expected=PRODUCT|OTHER_PRODUCT_PATHS
        if changed!=expected:raise ValueError('Unexpected product change since Build 493: '+', '.join(sorted(changed^expected)))
        # No Core input changed: the RPCS3 and ARMSX2 Cores, the libretro cores package.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*RPCS3_CORE_PATHS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--','build-utils/libretro'])
        # One native input only: the box reader plugin's recognizer; every other
        # package, native source and the iOS project are the delivered 493 ones.
        native=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--','packages','native','ios']).splitlines())
        if native!=NATIVE_PRODUCT:raise ValueError('Unexpected native change since Build 493: '+', '.join(sorted(native^NATIVE_PRODUCT)))
    # KartPad and Dusklight stay removed.
    for gone in ('packages/kartpad_internal_bridge','native/kartpad','build-utils/kartpad',
                 'lib/services/kartpad_internal_service.dart','packages/dusklight_internal_bridge','native/dusklight',
                 'build-utils/dusklight','lib/services/dusklight_internal_service.dart'):
        if base.command(['git','ls-files','--',gone]):raise ValueError('A removed port came back: '+gone)
    return {'deliveredBaseline':DELIVERED,'deliveredRun':DELIVERED_RUN,'baselineRecord':BASE,'testedSource':source,
        'changedProductPaths':sorted(PRODUCT),'coreRebuilt':False,'changedNativeInputs':sorted(NATIVE_PRODUCT),
        'otherSessionUnpackagedPaths':sorted(OTHER_SESSION),
        'otherEnginesCataloguesSkinsHelpersUnchanged':True}

rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin


def shown_job_name(name):
    # GitHub lists a job whose name is longer than 100 characters under its
    # first 97 characters followed by '...' (the native part's name is 106).
    return name if len(name)<=100 else name[:97]+'...'


def part_run(run_id,ref,name):
    return previous.part_run(run_id,ref,shown_job_name(name))


def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold'])]
    PROOFS=proofs(base.command(['git','rev-parse','HEAD']))
    verdicts={}
    with tempfile.TemporaryDirectory(prefix='gamebox494-proof-') as tmp:
        for part in PARTS:
            run,source,job=PROOFS[part]
            records.append(part_run(run,source,job))
            folder=Path(tmp)/part
            subprocess.run(['gh','run','download',str(run),'--repo','TarbleFR/RewindBox',
                '--name',f'build494-{part}-'+source,'--dir',str(folder)],check=True)
            files=list(folder.rglob(f'{part}-verdict.json'))
            if len(files)!=1:raise ValueError('Ambiguous or missing verdict: '+part)
            raw=files[0].read_bytes();verdicts[part]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
    covered=set()
    for part,(verdict,digest) in verdicts.items():
        if verdict['result']!='passed' or verdict['source']!=PROOFS[part][1] or verdict['build']!=494 or verdict['part']!=part:
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
        ('docs/evidence/gamebox490-delivery.json','docs/evidence/gamebox493-delivery.json') if (base.ROOT/p).is_file()}
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
        print('PASS Build 494 source closure: delivered 493 product + legibility of the box backs, only the box reader recognizer changed natively')
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
    print('PASS delivered 493 product + Build 494 targeted evidence; no suites rerun, no Core rebuilt')

if __name__=='__main__':
    main()
