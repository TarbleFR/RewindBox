"""Compose the delivered Build 490 with Canvas (ES-DE) and the removal of KartPad.

Build 491 is the delivered Build 490 (tag build-490) plus two changes from the
Claude branch, at the maintainer's choice of 20 October 2026:
- Canvas (ES-DE) as a curated external System Art source
  (docs/system-art/Canvas-ES-DE.md), with the analyzer cleanup that came with it;
- KartPad removed from NeoStation entirely (docs/kartpad-removal-2026-10-19.md):
  no KartPad framework, bridge, host or root resource in the IPA, the Build 350
  native donor fetched by range without any KartPad member, and the IPA checked
  by build-utils/validate_no_kartpad_ipa.py.
No emulator Core is rebuilt and no engine, helper, skin, cheat, texture or game
box input changes: they are the delivered Build 490 product. This gate reads CI
evidence; it never reruns suites. Each part (host, native) of
.github/workflows/build491-checks.yml must have passed on the delivery commit
itself, every tested input must be byte-identical to that commit, and the
verdicts (BUILD 491) must cover every changed input.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import gamebox490_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Build 490 source (tag build-490) and its delivery run (checks/native/cold).
DELIVERED='d152e5a270037484a435d641e04acd3a2ccaf3a6'
DELIVERED_RUN=39346406673
# Every change of this cycle is counted from the delivered 490 source.
BASE=DELIVERED
# build491-checks.yml is dispatched on the delivery commit: its parts ran on
# exactly the tree packaged here. Each part: the job that must have passed.
WORKFLOW='build491-checks.yml'
JOBS={
    'host':'Analysis, delivery Dart suite, KartPad removal and Canvas checks',
    'native':'NeoPlay companion adapters in the iOS Simulator',
}
PARTS=('host','native')
# The only native inputs of this cycle: NeoPlay no longer anchors to the old
# KartPad overlay. Every other changed input is read by the host part.
NATIVE={'packages/neoplay_bridge/ios/Classes/NPGameHUDAnchor.swift','test/neoplay/companion_tests.swift'}
# Delivery wiring, records, workflows and pins: no product or tested input.
DELIVERY_ONLY={'AGENTS.md','README.md','.github/diagnostics/kartpad491_delivery.py',
    'build-utils/verify_delivery_reuse.py','build-utils/delivery_cipher.py','build-utils/delivery-491-recipient.pem'}
WORKFLOWS_PREFIX='.github/workflows/'
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS
RPCS3_CORE_PATHS=previous.RPCS3_CORE_PATHS
# The product files Build 491 changes (added, modified or deleted) since 490.
CANVAS_PRODUCT={
    'assets/legal/Canvas-ES-DE-ATTRIBUTION.md',
    'lib/services/neo_assets_service.dart',
    'lib/services/system_art/canvas_es_de_capsules.dart',
    'tools/system_art/canvas-es-de-flat-webp.txt',
    'tools/system_art/canvas_es_de.py',
    # Analyzer cleanup of the same session (no behaviour change).
    'lib/services/libretro_skin_catalog_service.dart',
    'lib/services/texture_catalog_service.dart',
}
KARTPAD_REMOVAL_PRODUCT={
    'assets/legal/KartPad-RIGHTS_AND_LICENSES.md','assets/legal/KartPad-THIRD_PARTY_NOTICES.md',
    'assets/legal/THIRD_PARTY_NOTICES.md','assets/systems/ports.json',
    'lib/l10n/ports_locale.dart','lib/l10n/storage_locale.dart','lib/models/game_model.dart',
    'lib/providers/sqlite_config_provider.dart','lib/providers/sqlite_config_provider/scanning.dart',
    'lib/screens/game_screen/my_games_list.dart','lib/screens/libretro/libretro_consoles_screen.dart',
    'lib/screens/settings_screen/legal_credits_dialog.dart',
    'lib/screens/settings_screen/new_settings_options/widgets/external_display_setting_rows.dart',
    'lib/services/console_catalog.dart','lib/services/external_display_service.dart',
    'lib/services/game/game_launch_service.dart','lib/services/game/game_list_service.dart',
    'lib/services/game_launch_manager.dart','lib/services/home_music_service.dart',
    'lib/services/kartpad_internal_service.dart','lib/services/music_player_service.dart',
    'lib/services/ports_display_title.dart','lib/services/ports_game_identity.dart',
    'lib/utils/game_launch_utils.dart','lib/widgets/ports_internal_playlist_actions.dart',
    'native/kartpad/core/DonorAudioSession.h','native/kartpad/core/DonorDataLifecycle.h',
    'native/kartpad/core/DonorSessionReset.h','native/kartpad/core/GuestLanguageState.h',
    'native/kartpad/core/NeoKartPadCore.mm','native/kartpad/core/SessionRunLoop.h',
    'native/kartpad/core/SessionState.h','native/kartpad/core/UIKitEventPump.h',
    'native/kartpad/core/WindowHandoff.h','native/kartpad/donor/DonorSessionControl.inc',
    'native/kartpad/donor/NeoKartPadDonorCore.mm',
    'packages/kartpad_internal_bridge/ios/Classes/KartPadCoreABI.h',
    'packages/kartpad_internal_bridge/ios/Classes/KartPadCoreLoader.h',
    'packages/kartpad_internal_bridge/ios/Classes/KartPadHostWindowAwaiter.h',
    'packages/kartpad_internal_bridge/ios/Classes/KartPadHostWindowAwaiter.mm',
    'packages/kartpad_internal_bridge/ios/Classes/KartPadHostWindowPolicy.h',
    'packages/kartpad_internal_bridge/ios/Classes/KartPadHostWindowSelection.h',
    'packages/kartpad_internal_bridge/ios/Classes/KartPadInternalBridgePlugin.h',
    'packages/kartpad_internal_bridge/ios/Classes/KartPadInternalBridgePlugin.mm',
    'packages/kartpad_internal_bridge/ios/kartpad_internal_bridge.podspec',
    'packages/kartpad_internal_bridge/lib/kartpad_internal_bridge.dart',
    'packages/kartpad_internal_bridge/pubspec.yaml',
    'packages/neoplay_bridge/ios/Classes/NPGameHUDAnchor.swift',
    'pubspec.yaml',
}
PRODUCT=CANVAS_PRODUCT|KARTPAD_REMOVAL_PRODUCT


def tested_paths():
    """Every non-documentation path changed since Build 490 that is not delivery wiring."""
    paths=set(base.command(['git','diff','--name-only',BASE,'HEAD']).splitlines())
    return {path for path in paths if not path.startswith('docs/') and path not in DELIVERY_ONLY
            and not path.startswith(WORKFLOWS_PREFIX)}


def tested_source():
    return base.command(['git','rev-parse','HEAD'])


def records_only(path):
    # Documentation and delivery records: never packaged, never a tested input.
    return path.startswith('docs/') or path in DELIVERY_ONLY


def proofs(head):
    """The latest successful build491-checks.yml run on HEAD, or on an ancestor of
    HEAD when every commit since only touched documentation or delivery wiring
    (the delivery records written after the checks). evidence() still compares
    every verdict input with the files of HEAD, byte for byte."""
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
    source=tested_source()
    for name,value in (('BASE',BASE),('DELIVERED',DELIVERED)):
        if len(value)!=40:raise ValueError(f'{name} is not pinned')
    tested=tested_paths()
    # The working tree is the tested commit (nothing edited after checkout).
    base.command(['git','diff','--exit-code','HEAD','--',*sorted(tested)])
    for end in (['HEAD'],[]):
        # The product differs from delivered 490 exactly by the Build 491 files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        if changed!=PRODUCT:raise ValueError('Unexpected product change since Build 490: '+', '.join(sorted(changed^PRODUCT)))
        # No Core input changed: the RPCS3 and ARMSX2 Cores, the libretro cores package.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*RPCS3_CORE_PATHS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--','build-utils/libretro'])
        # The texture catalogue, the game box, Dusklight, the engines' bridges and
        # NeoSwap are the delivered 490 ones.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--','packages/neo_texture_catalog','native/textures',
            'packages/libretro_internal_bridge','packages/dolphin_internal_bridge','packages/armsx2_internal_bridge',
            'packages/rpcs3_internal_bridge','packages/dusklight_internal_bridge','packages/neo_swap','native/neoswap',
            'native/neoswap-relay','native/neoswap-donation','native/dusklight','build-utils/dusklight'])
    # KartPad is gone for good: nothing of it may come back into the tree.
    for gone in ('packages/kartpad_internal_bridge','native/kartpad','build-utils/kartpad',
                 'lib/services/kartpad_internal_service.dart'):
        if (base.ROOT/gone).exists():raise ValueError('KartPad came back: '+gone)
    return {'deliveredBaseline':DELIVERED,'deliveredRun':DELIVERED_RUN,'baselineRecord':BASE,'testedSource':source,
        'changedProductPaths':sorted(PRODUCT),'coreRebuilt':False,'kartPadRemoved':True,
        'otherEnginesCataloguesSkinsHelpersUnchanged':True}

rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin
part_run=previous.part_run


def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold'])]
    PROOFS=proofs(tested_source())
    verdicts={}
    with tempfile.TemporaryDirectory(prefix='kartpad491-proof-') as tmp:
        for part in PARTS:
            run,source,job=PROOFS[part]
            records.append(part_run(run,source,job))
            folder=Path(tmp)/part
            subprocess.run(['gh','run','download',str(run),'--repo','TarbleFR/RewindBox',
                '--name',f'build491-{part}-'+source,'--dir',str(folder)],check=True)
            files=list(folder.rglob(f'{part}-verdict.json'))
            if len(files)!=1:raise ValueError('Ambiguous or missing verdict: '+part)
            raw=files[0].read_bytes();verdicts[part]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
    covered=set()
    for part,(verdict,digest) in verdicts.items():
        if verdict['result']!='passed' or verdict['source']!=PROOFS[part][1] or verdict['build']!=491 or verdict['part']!=part:
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
    # Verdicts list what each part read; every tested input must be covered by one.
    if missing:raise ValueError('Targeted proof did not close: '+', '.join(sorted(missing)))
    native=verdicts['native'][0]
    if native['xcode']!='Xcode 26.3\nBuild version 17C529' or native['iphoneSDK']!='26.2':
        raise ValueError('Targeted native checks ran on another toolchain')
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/gamebox490-delivery.json','docs/evidence/hdtex489-delivery.json') if (base.ROOT/p).is_file()}
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
        print('PASS Build 491 source closure: delivered 490 product + Canvas (ES-DE) + KartPad removal, no Core input changed')
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
    print('PASS delivered 490 product + Build 491 targeted evidence; no suites rerun, no Core rebuilt')

if __name__=='__main__':
    main()
