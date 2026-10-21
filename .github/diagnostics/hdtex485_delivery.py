"""Compose the delivered Build 484 with the Build 485 ARMSX2 Core (ABI 8) and its targeted proofs.

Build 485 adds HD texture packs to the embedded ARMSX2 engine: the Core exposes
the engine's own texture replacement state, per-game switch, reload and .tar.zst
decoder (ABI 8, two read accessors added to GSTextureReplacements), the host
installs packs into ARMSX2/textures/<serial>/replacements (store, Flutter
channel, in-game page) and the game settings show a panel in twelve languages.
Every other input - RPCS3 Core 483, Dolphin, Dusklight, libretro cores,
catalogues, skins, helpers, the Build 484 touch-controls editor - is the
delivered Build 484 product. This gate reads CI evidence; it never reruns
suites or rebuilds a core. The ARMSX2 Core run is the one pinned by the delivery
workflow and must have passed both its jobs (framework compilation with the
Foundation store and Core adapter tests; UIKit Graphics menu with the HD
textures page and the host ABI compile); the targeted run must have passed on
the same source, with every tested input identical.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import touch484_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Branch head before this cycle: the Build 484 delivery record on Claude.
BASE='39a22de2e043eca70bf4fe250f95fdeb3e23f324'
# Build 484 source and its delivery run (checks/native reused, cold Release).
DELIVERED='e76f40b77fb45e8ce23f161d5d4f4b0dd6fbf3f3'
DELIVERED_RUN=39177384518
# Build 485 Core source: ARMSX2 Core ABI 8, host store/bridge/page, panel, locales, tests.
CORE_SOURCE='1343906f05e33b40f10f7026a1a6e2327c338d0e'
CORE_RUN=39178893158          # armsx2-core.yml
CORE_JOBS=['Compile pinned ARMSX2 iOS framework','Verify ARMSX2 Graphics menu and host ABI']
# Tested source: CORE_SOURCE + the podspec comment refused by armsx2_external_display_test.py
# (touch-layout-checks run 39178889242, host part) and that contract added to the targeted run.
TESTED_SOURCE='587a9d9dc3a52cd613388abc73150f034474910a'
APP_RUN=39181081216           # build485-checks.yml, job targeted
# The only tested inputs that differ between the two runs (no Core input, no compiled code).
CORE_TO_TESTED={'packages/armsx2_internal_bridge/ios/armsx2_internal_bridge.podspec','test/build485_targeted_test.py'}
ARMSX2_REVISION='9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe'

sys.path.insert(0,str(base.ROOT/'test'))
import build485_targeted_test as targeted  # noqa: E402
PRODUCT=set(targeted.PRODUCT)
TESTED=PRODUCT|set(targeted.TESTS)
# Delivery wiring, records, credits and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','docs/build485-hd-textures.md','docs/evidence/hdtex485-delivery.json',
    'docs/LEGAL_AND_CREDITS.md','.github/diagnostics/hdtex485_delivery.py',
    '.github/workflows/retroarch-delivery.yml','.github/workflows/neoswap-ipa.yml',
    'build-utils/verify_delivery_reuse.py','test/import_memory_candidate_scope_test.py'}
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS

def source_closure():
    for name,value in (('BASE',BASE),('DELIVERED',DELIVERED),('CORE_SOURCE',CORE_SOURCE),('TESTED_SOURCE',TESTED_SOURCE)):
        if len(value)!=40:raise ValueError(f'{name} is not pinned yet')
    for end in (['HEAD'],[]):
        paths=set(base.command(['git','diff','--name-only',BASE,*end]).splitlines())
        extra=paths-TESTED-DELIVERY_ONLY
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        # Every tested input is byte-identical to the targeted run's source, every ARMSX2 Core
        # input to the Core run's source.
        base.command(['git','diff','--exit-code',TESTED_SOURCE,*end,'--',*sorted(TESTED)])
        base.command(['git','diff','--exit-code',CORE_SOURCE,*end,'--',*ARMSX2_CORE_INPUTS])
        # The product differs from delivered 484 exactly by the Build 485 product files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        if changed!=PRODUCT:raise ValueError('Unexpected product change since Build 484: '+', '.join(sorted(changed^PRODUCT)))
        # The RPCS3 Core inputs are Build 484's (that is, Build 483's pin).
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',
                      'build-utils/rpcs3','packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreABI.h'])
    # Between the Core run and the targeted run only the podspec comment and the targeted script moved.
    moved=set(base.command(['git','diff','--name-only',CORE_SOURCE,TESTED_SOURCE,'--',*sorted(TESTED)]).splitlines())
    if moved!=CORE_TO_TESTED:raise ValueError('Tested inputs differ between the Core and targeted runs: '+', '.join(sorted(moved^CORE_TO_TESTED)))
    pin=previous.previous  # llvmpipe483_delivery: the RPCS3 Core pin
    manifest=json.loads((base.ROOT/'build-utils/rpcs3/canonical-source.json').read_text())
    patch=hashlib.sha256((base.ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes()).hexdigest()
    if manifest['patch_sha256']!=pin.PATCH or patch!=pin.PATCH:raise ValueError('RPCS3 Core delta differs from the Build 483 pin')
    source=json.loads((base.ROOT/'build-utils/armsx2/source.json').read_text())
    abi=(base.ROOT/'packages/armsx2_internal_bridge/ios/Classes/ARMSX2CoreABI.h').read_text()
    if source['revision']!=ARMSX2_REVISION or source['abi_version']!=8 or '#define NEO_ARMSX2_ABI_VERSION 8u' not in abi:
        raise ValueError('ARMSX2 2.6 pin or ABI 8 changed')
    return {'deliveredBaseline':DELIVERED,'baselineRecord':BASE,'testedSource':TESTED_SOURCE,'coreSource':CORE_SOURCE,
        'coreToTestedChanges':sorted(CORE_TO_TESTED),'armsx2CoreRun':CORE_RUN,
        'targetedRun':APP_RUN,'rpcs3CorePin':pin.CORE_SOURCE,'rpcs3CanonicalPatchSHA256':pin.PATCH,
        'changedProductPaths':sorted(PRODUCT),'armsx2CoreChanged':True,'rpcs3CoreChanged':False,
        'otherEnginesCataloguesSkinsHelpersUnchanged':True}

# The RPCS3 Core pin is the Build 483 one: reuse its exact input view and identity checks.
rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin

def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold']),
        base.successful_run(CORE_RUN,CORE_SOURCE,CORE_JOBS),
        base.successful_run(APP_RUN,TESTED_SOURCE,['targeted'])]
    with tempfile.TemporaryDirectory(prefix='hdtex485-proof-') as tmp:
        subprocess.run(['gh','run','download',str(APP_RUN),'--repo','TarbleFR/RewindBox',
            '--name','build485-'+TESTED_SOURCE,'--dir',tmp],check=True)
        files=list(Path(tmp).rglob('verdict.json'))
        if len(files)!=1:raise ValueError('Ambiguous or missing targeted verdict')
        raw=files[0].read_bytes();verdict=json.loads(raw)
        subprocess.run(['gh','run','download',str(CORE_RUN),'--repo','TarbleFR/RewindBox',
            '--name','ARMSX2Core-diagnostics-'+CORE_SOURCE,'--dir',tmp+'/core'],check=True)
        identity=(Path(tmp)/'core'/'identity.txt').read_text()
    if verdict['result']!='passed' or verdict['source']!=TESTED_SOURCE or verdict['build']!=485:
        raise ValueError('Wrong targeted proof identity/result')
    if verdict['coreRebuilt'] is not False or verdict['deviceValidated'] is not False:
        raise ValueError('Targeted verdict claims more than it ran')
    for path,digest in verdict['inputsSHA256'].items():
        if hashlib.sha256((base.ROOT/path).read_bytes()).hexdigest()!=digest:
            raise ValueError('Changed tested input '+path)
    missing=TESTED-set(verdict['inputsSHA256'])
    if missing:raise ValueError('Targeted proof did not close: '+', '.join(sorted(missing)))
    if f'host={CORE_SOURCE}' not in identity or f'armsx2={ARMSX2_REVISION}' not in identity:
        raise ValueError('ARMSX2 Core diagnostics identity differs from the pinned run')
    records[1].update(armsx2Revision=ARMSX2_REVISION,abi=8,identitySHA256=hashlib.sha256(identity.encode()).hexdigest())
    records[2].update(verdictSHA256=hashlib.sha256(raw).hexdigest(),dartTests=verdict['dartTests'],
        pythonChecks=verdict['pythonChecks'],timingsSeconds=verdict['timingsSeconds'])
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/ps2blend482-delivery.json','docs/evidence/llvmpipe483-delivery.json',
         'docs/evidence/touch484-delivery.json')
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
        print('PASS Build 485 source closure: delivered 484 product + tested ARMSX2 Core/app changes, RPCS3 Core pin unchanged')
        return
    records,receipts=evidence()
    record={'result':'passed','testedSHA':TESTED_SOURCE,'coreSHA':CORE_SOURCE,'candidateSHA':base.command(['git','rev-parse','HEAD']),
        'validationWasReused':True,'sourceClosure':closure,'reusedEvidence':records,'receiptSHA256':receipts,
        'deviceGameplayValidated':False,'coreRebuilt':True,'coreRun':CORE_RUN,'rebuiltCore':'ARMSX2 (ABI 8)'}
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
    print('PASS delivered 484 product + Build 485 ARMSX2 Core and targeted evidence; no suites rerun, one Core rebuilt')

if __name__=='__main__':
    main()
