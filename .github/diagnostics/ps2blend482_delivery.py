"""Compose the delivered Build 481 with the Build 482 ARMSX2 Core (ABI 7) and its targeted proofs.

Build 482 changes the ARMSX2 Core (blending accuracy over the upstream INI
layers, ABI 7), its host plugin, in-game menu and native locales, and adds the
Get More RAM information before the PS3 firmware installation (Flutter). Every
other input - RPCS3 Core 481, Dolphin, Dusklight, libretro cores, catalogues,
skins, helpers - is the delivered Build 481 product. This gate reads CI
evidence; it never reruns suites or rebuilds a core. The ARMSX2 Core run is the
one pinned by the delivery workflow and must have passed both its jobs
(framework compilation with the Foundation/MRC adapter test, UIKit Graphics
menu with the host ABI compile); the targeted run must have passed its Flutter
and contract checks on the same source, with every tested input identical.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import spucache481_delivery as previous
base=previous.previous  # unified_cheats_delivery: command, api, successful_run, ROOT

# Branch head before this cycle: the Build 481 delivery record.
BASE='42c781c52bbb0811ca7c61786b843930b0c217b7'
# Build 481 source (run 39148545918: checks/native reused, cold Release).
DELIVERED='839d114763e80a9945d162369e8d8f258bb82485'
# Build 482 source: ARMSX2 Core ABI 7, host plugin, menu, locales, PS3 preflight, tests.
CORE_SOURCE='da091fa7483279844d5a7406dfafd0f447ab3099'
CORE_RUN=39155495662          # armsx2-core.yml
CORE_JOBS=['Compile pinned ARMSX2 iOS framework','Verify ARMSX2 Graphics menu and host ABI']
APP_RUN=39155497540           # build482-checks.yml, job targeted
ARMSX2_REVISION='9d989ca933a85bb2f1d111fd3b9e5742ac7d2fbe'
PRODUCT={'lib/l10n/rpcs3_firmware_locale.dart','lib/widgets/rpcs3_firmware_preflight_dialog.dart',
    'lib/screens/rpcs3_manager_screen.dart','lib/widgets/rpcs3_internal_playlist_actions.dart',
    'packages/armsx2_internal_bridge/core/ARMSX2BlendingAccuracy.h',
    'packages/armsx2_internal_bridge/core/ARMSX2BlendingAccuracy.inc',
    'packages/armsx2_internal_bridge/core/ARMSX2Core.mm',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2CoreABI.h',
    'packages/armsx2_internal_bridge/ios/Classes/ARMSX2InGameLocalization.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2InternalBridgePlugin.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2SessionMenu.mm',
    'build-utils/armsx2/source.json'}
TESTED=PRODUCT|{'test/rpcs3_firmware_preflight_test.dart','test/rpcs3_firmware_library_test.dart',
    'test/rpcs3_rap_import_menu_test.dart','test/rpcs3_internal_integration_test.dart',
    'test/armsx2_embedded_library_contract_test.dart','test/armsx2_in_game_localization_test.dart',
    'test/localization_12_locale_coverage_test.py','test/armsx2_bios_hacks_test.py',
    'test/armsx2_graphics_test.py','test/armsx2_graphics_ui_test.py','test/armsx2_blending_accuracy_test.mm',
    'test/build482_targeted_test.py','.github/workflows/build482-checks.yml','.github/workflows/armsx2-core.yml',
    'build-utils/verify_delivery_reuse.py'}
# Delivery wiring, records and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','docs/build482-ps2-blending-ps3-ram.md','docs/evidence/ps2blend482-delivery.json',
    'docs/armsx2-26-integration.md','.github/diagnostics/ps2blend482_delivery.py',
    '.github/workflows/retroarch-delivery.yml','.github/workflows/neoswap-ipa.yml',
    'test/import_memory_candidate_scope_test.py'}
PRODUCT_PATHS=['lib','packages','assets','native','pubspec.yaml','pubspec.lock','tools','build-utils/libretro',
    'build-utils/rpcs3','build-utils/armsx2']
ARMSX2_CORE_INPUTS=['packages/armsx2_internal_bridge/core','packages/armsx2_internal_bridge/ios/Classes/ARMSX2CoreABI.h',
    'build-utils/armsx2']

def source_closure():
    for end in (['HEAD'],[]):
        paths=set(base.command(['git','diff','--name-only',BASE,*end]).splitlines())
        extra=paths-TESTED-DELIVERY_ONLY
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        # Every tested input is byte-identical to the source both runs tested.
        base.command(['git','diff','--exit-code',CORE_SOURCE,*end,'--',*sorted(TESTED)])
        base.command(['git','diff','--exit-code',CORE_SOURCE,*end,'--',*ARMSX2_CORE_INPUTS])
        # The product differs from delivered 481 exactly by the Build 482 product files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        if changed!=PRODUCT:raise ValueError('Unexpected product change since Build 481: '+', '.join(sorted(changed^PRODUCT)))
    manifest=json.loads((base.ROOT/'build-utils/rpcs3/canonical-source.json').read_text())
    patch=hashlib.sha256((base.ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes()).hexdigest()
    if manifest['patch_sha256']!=previous.PATCH or patch!=previous.PATCH:raise ValueError('RPCS3 Core delta differs from the Build 481 pin')
    source=json.loads((base.ROOT/'build-utils/armsx2/source.json').read_text())
    abi=(base.ROOT/'packages/armsx2_internal_bridge/ios/Classes/ARMSX2CoreABI.h').read_text()
    if source['revision']!=ARMSX2_REVISION or source['abi_version']!=7 or '#define NEO_ARMSX2_ABI_VERSION 7u' not in abi:
        raise ValueError('ARMSX2 2.6 pin or ABI 7 changed')
    return {'deliveredBaseline':DELIVERED,'baselineRecord':BASE,'testedSource':CORE_SOURCE,'armsx2CoreRun':CORE_RUN,
        'targetedRun':APP_RUN,'rpcs3CorePin':previous.CORE_SOURCE,'rpcs3CanonicalPatchSHA256':previous.PATCH,
        'changedProductPaths':sorted(PRODUCT),'armsx2CoreChanged':True,'rpcs3CoreChanged':False,
        'otherEnginesCataloguesSkinsHelpersUnchanged':True}

# The RPCS3 Core pin is the Build 481 one: reuse its exact input view and identity checks.
rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin

def evidence():
    records=[base.successful_run(39148545918,DELIVERED,['checks','native','Release device build • cold']),
        base.successful_run(CORE_RUN,CORE_SOURCE,CORE_JOBS),
        base.successful_run(APP_RUN,CORE_SOURCE,['targeted'])]
    with tempfile.TemporaryDirectory(prefix='ps2blend482-proof-') as tmp:
        subprocess.run(['gh','run','download',str(APP_RUN),'--repo','TarbleFR/neostation-ios',
            '--name','build482-'+CORE_SOURCE,'--dir',tmp],check=True)
        files=list(Path(tmp).rglob('verdict.json'))
        if len(files)!=1:raise ValueError('Ambiguous or missing targeted verdict')
        raw=files[0].read_bytes();verdict=json.loads(raw)
        subprocess.run(['gh','run','download',str(CORE_RUN),'--repo','TarbleFR/neostation-ios',
            '--name','ARMSX2Core-diagnostics-'+CORE_SOURCE,'--dir',tmp+'/core'],check=True)
        identity=(Path(tmp)/'core'/'identity.txt').read_text()
    if verdict['result']!='passed' or verdict['source']!=CORE_SOURCE or verdict['build']!=482:
        raise ValueError('Wrong targeted proof identity/result')
    if verdict['coreRebuilt'] is not False or verdict['deviceValidated'] is not False:
        raise ValueError('Targeted verdict claims more than it ran')
    for path,digest in verdict['inputsSHA256'].items():
        if hashlib.sha256((base.ROOT/path).read_bytes()).hexdigest()!=digest:
            raise ValueError('Changed tested input '+path)
    missing=TESTED-set(verdict['inputsSHA256'])-{'build-utils/verify_delivery_reuse.py'}
    if missing:raise ValueError('Targeted proof did not close: '+', '.join(sorted(missing)))
    if f'host={CORE_SOURCE}' not in identity or f'armsx2={ARMSX2_REVISION}' not in identity:
        raise ValueError('ARMSX2 Core diagnostics identity differs from the pinned run')
    records[1].update(armsx2Revision=ARMSX2_REVISION,abi=7,identitySHA256=hashlib.sha256(identity.encode()).hexdigest())
    records[2].update(verdictSHA256=hashlib.sha256(raw).hexdigest(),dartTests=verdict['dartTests'],
        pythonChecks=verdict['pythonChecks'],timingsSeconds=verdict['timingsSeconds'])
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/spucache481-delivery.json',)}
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
        print('PASS Build 482 source closure: delivered 481 product + tested ARMSX2 Core/app changes, RPCS3 Core pin unchanged')
        return
    records,receipts=evidence()
    record={'result':'passed','testedSHA':CORE_SOURCE,'candidateSHA':base.command(['git','rev-parse','HEAD']),
        'validationWasReused':True,'sourceClosure':closure,'reusedEvidence':records,'receiptSHA256':receipts,
        'deviceGameplayValidated':False,'coreRebuilt':True,'coreRun':CORE_RUN,'rebuiltCore':'ARMSX2 (ABI 7)'}
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
    print('PASS delivered 481 product + Build 482 ARMSX2 Core and targeted evidence; no suites rerun, one Core rebuilt')

if __name__=='__main__':
    main()
