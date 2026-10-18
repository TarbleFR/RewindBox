"""Compose the delivered Build 483 with the Build 484 touch-controls editor and its targeted proofs.

Build 484 changes the touch controls of the embedded Dolphin (GameCube, Wii),
ARMSX2 (PS2) and RPCS3 (PS3) engines, their in-game menus and host plugins,
adds the shared neo_touch_layout pod (layouts, on-screen editor, controller
policy, twelve-language texts) and the Emulators-tab panel. No emulator Core
is rebuilt: the RPCS3 Core of Build 483 and every other engine, helper,
catalogue and skin input is the delivered Build 483 product. This gate reads
CI evidence; it never reruns suites. The targeted run must have passed its
three parts (host, native, uikit) on one source, every tested input must be
byte-identical to it, and its verdicts must cover every changed input.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import llvmpipe483_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Branch head before this cycle: the Build 483 delivery record.
BASE='0000000000000000000000000000000000000000'
# Build 483 source and delivery run (checks/native/cold Release).
DELIVERED='0000000000000000000000000000000000000000'
DELIVERED_RUN=0
# Build 484 source tested by touch-layout-checks.yml (three parts).
TESTED_SOURCE='0000000000000000000000000000000000000000'
TESTED_RUN=0
JOBS=['Texts, geometry, pad merge, engine contracts and Flutter',
      'iPhone SDK build and the affected UIKit suites',
      'Editor, five layouts, orientations, multitouch, controller policy and persistence on UIKit']
PARTS=('host','native','uikit')

sys.path.insert(0,str(base.ROOT/'test'))
import build484_targeted_test as targeted  # noqa: E402
PRODUCT=set(targeted.PRODUCT)
TESTED=(PRODUCT|set(targeted.SUPPORT)|set(targeted.HOST_PYTHON)|set(targeted.DART_TESTS)
        |set(targeted.PRE_EXISTING)|set(targeted.PRE_EXISTING_DART)
        |{command[0] for command in targeted.NATIVE+targeted.UIKIT}
        |{'test/embedded_touch_controls_panel_test.dart','test/rpcs3_input_bridge_test.py',
          'test/unified_native_ios_test.py','test/armsx2_graphics_ui_test.py'})
# Delivery wiring, records and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','docs/build484-touch-controls.md','docs/evidence/touch484-delivery.json',
    '.github/diagnostics/touch484_delivery.py','.github/workflows/retroarch-delivery.yml',
    '.github/workflows/neoswap-ipa.yml','build-utils/verify_delivery_reuse.py'}
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS

def source_closure():
    for end in (['HEAD'],[]):
        paths=set(base.command(['git','diff','--name-only',BASE,*end]).splitlines())
        extra=paths-TESTED-DELIVERY_ONLY
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        # Every tested input is byte-identical to the source the three parts tested.
        base.command(['git','diff','--exit-code',TESTED_SOURCE,*end,'--',*sorted(TESTED)])
        # The product differs from delivered 483 exactly by the Build 484 product files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        if changed!=PRODUCT:raise ValueError('Unexpected product change since Build 483: '+', '.join(sorted(changed^PRODUCT)))
        # No Core input changed: ARMSX2 Core sources/ABI and the RPCS3 canonical delta are Build 483's.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS,
                      'build-utils/rpcs3','packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreABI.h'])
    manifest=json.loads((base.ROOT/'build-utils/rpcs3/canonical-source.json').read_text())
    patch=hashlib.sha256((base.ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes()).hexdigest()
    if manifest['patch_sha256']!=previous.PATCH or patch!=previous.PATCH:raise ValueError('RPCS3 Core delta differs from the Build 483 pin')
    return {'deliveredBaseline':DELIVERED,'baselineRecord':BASE,'testedSource':TESTED_SOURCE,'targetedRun':TESTED_RUN,
        'rpcs3CorePin':previous.CORE_SOURCE,'rpcs3CanonicalPatchSHA256':previous.PATCH,
        'changedProductPaths':sorted(PRODUCT),'coreRebuilt':False,
        'otherEnginesCataloguesSkinsHelpersUnchanged':True}

# The RPCS3 Core pin is the Build 483 one: reuse its exact input view and identity checks.
rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin

def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold']),
        base.successful_run(TESTED_RUN,TESTED_SOURCE,JOBS)]
    verdicts={}
    with tempfile.TemporaryDirectory(prefix='touch484-proof-') as tmp:
        for part in PARTS:
            folder=Path(tmp)/part
            subprocess.run(['gh','run','download',str(TESTED_RUN),'--repo','TarbleFR/neostation-ios',
                '--name',f'build484-{part}-'+TESTED_SOURCE,'--dir',str(folder)],check=True)
            files=list(folder.rglob(f'{part}-verdict.json'))
            if len(files)!=1:raise ValueError('Ambiguous or missing verdict: '+part)
            raw=files[0].read_bytes();verdicts[part]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
    covered=set()
    for part,(verdict,digest) in verdicts.items():
        if verdict['result']!='passed' or verdict['source']!=TESTED_SOURCE or verdict['build']!=484 or verdict['part']!=part:
            raise ValueError('Wrong targeted proof identity/result: '+part)
        if verdict['coreRebuilt'] is not False or verdict['deviceValidated'] is not False:
            raise ValueError('Targeted verdict claims more than it ran: '+part)
        for path,sha in verdict['inputsSHA256'].items():
            if hashlib.sha256((base.ROOT/path).read_bytes()).hexdigest()!=sha:
                raise ValueError('Changed tested input '+path)
        covered|=set(verdict['inputsSHA256'])
        records.append({'part':part,'verdictSHA256':digest,'checks':verdict['checks'],
            'timingsSeconds':verdict['timingsSeconds'],**({'uikit':verdict['uikit']} if 'uikit' in verdict else {}),
            **({'preExistingComparison':verdict['preExistingComparison']} if 'preExistingComparison' in verdict else {})})
    missing=TESTED-covered
    if missing:raise ValueError('Targeted proof did not close: '+', '.join(sorted(missing)))
    native=verdicts['native'][0]
    if native['xcode']!='Xcode 26.3\nBuild version 17C529' or native['iphoneSDK']!='26.2':
        raise ValueError('Targeted native checks ran on another toolchain')
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/llvmpipe483-delivery.json','docs/evidence/ps2blend482-delivery.json')}
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
        print('PASS Build 484 source closure: delivered 483 product + tested touch-controls changes, no Core input changed')
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
    print('PASS delivered 483 product + Build 484 touch-controls targeted evidence; no suites rerun, no Core rebuilt')

if __name__=='__main__':
    main()
