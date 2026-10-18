"""Compose delivered 475 with the closed, targeted PS2/PS3 follow-up proof.

No suite or emulator core is rebuilt by this gate. Changed catalogue/menu code
must exactly equal the successful Apple SDK/Foundation/UIKit candidate.
"""
import hashlib
from pathlib import Path
import unified_cheats_delivery as previous

BASE='e6bdfd79d2244a41845ceb9d7774eade5b554611'
DELIVERED='69dd419030024e18457464d6a4b0e580bd5f6058'
TESTED='9af4126dfcbd9727564793c7f0f45f3671f9b7ca'
RUN=39106305814
MENU_SOURCE='61cceed5bf3deebbdc28dd04160d0207b608eaa5'
MENU_RUN=39105809611
UI_SOURCE='6c41e180da2eaf693bb8480d43abff1552b5df94'
UI_RUN=39106115226
PROVED={
    'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m',
    'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatList.m',
    'packages/neo_cheat_catalog/ios/Classes/Public/NeoUnifiedCheatCatalog.h',
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3SessionMenu.mm',
    'test/unified_catalog_runtime_native.m',
    'test/unified_catalog_browser_ui_tests.m',
    'test/unified_catalog_browser_ui_test.py',
    'test/cheats476_regression.py',
    '.github/workflows/cheats476.yml',
}
DELIVERY_ONLY={
    '.github/diagnostics/cheats476_delivery.py',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/validate_unified_cheats_ipa.py',
    'build-utils/delivery-476-recipient.pem',
    'docs/build476-ps2-ps3-cheats.md',
    'docs/evidence/cheats476-delivery.json',
    'AGENTS.md',
}

def source_closure():
    for args in (['git','diff','--name-only',BASE,'HEAD'],['git','diff','--name-only',BASE]):
        extra=set(previous.command(args).splitlines())-PROVED-DELIVERY_ONLY
        if extra:
            raise ValueError('Unproved changes outside the targeted fix: '+', '.join(sorted(extra)))
    for target in ('HEAD',):
        previous.command(['git','diff','--exit-code',TESTED,target,'--',*sorted(PROVED)])
    previous.command(['git','diff','--exit-code',TESTED,'--',*sorted(PROVED)])
    previous.command(['git','diff','--exit-code',UI_SOURCE,TESTED,'--',
        'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatList.m',
        'test/unified_catalog_browser_ui_tests.m','test/unified_catalog_browser_ui_test.py'])
    previous.command(['git','diff','--exit-code',MENU_SOURCE,TESTED,'--',
        'packages/neo_cheat_catalog/ios/Classes/Public/NeoUnifiedCheatCatalog.h',
        'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3SessionMenu.mm',
        'packages/armsx2_internal_bridge','packages/dolphin_internal_bridge',
        'test/unified_native_ios_test.py'])
    # The delivered 475 proof covers all unchanged Dart, catalogue data, skins,
    # library, cores/helpers and NeoSwap inputs. The allowlist above rejects any
    # change to those inputs; there is no package-wide exemption.
    previous.command(['git','diff','--exit-code',DELIVERED,BASE,'--','packages','lib','assets','native','tools','pubspec.yaml','pubspec.lock'])
    return {'baselineDelivery':DELIVERED,'baselineReceipt':BASE,'testedService':TESTED,
            'testedMenusAndAPI':MENU_SOURCE,'testedUIKit':UI_SOURCE,
            'changedInputs':sorted(PROVED),'allOtherProductAndDataInputsUnchanged':True}

def evidence():
    records=[
        previous.successful_run(39102171744,DELIVERED,['checks','native','Release device build • cold']),
        previous.successful_run(MENU_RUN,MENU_SOURCE,['targeted']),
        previous.successful_run(UI_RUN,UI_SOURCE,['targeted']),
        previous.successful_run(RUN,TESTED,['targeted']),
    ]
    receipt=previous.ROOT/'docs/evidence/unified-cheats-direct475.json'
    return records,{'docs/evidence/unified-cheats-direct475.json':hashlib.sha256(receipt.read_bytes()).hexdigest()}

if __name__=='__main__':
    previous.source_closure=source_closure
    previous.evidence=evidence
    previous.CATALOGUE=TESTED
    previous.main()
