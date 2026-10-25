"""Compose Build 491 with the removal of Dusklight and of the Ports playlist.

Build 492 is the delivered Build 491 (9faa3f9b, product of 59bec98c: Build 490, Canvas ES-DE,
KartPad removal) plus the maintainer decision of 20 October 2026
(docs/ports-removal-2026-10-20.md): Dusklight and the Ports playlist leave
NeoStation. No Dusklight Core, bridge, notice or identity in the IPA, the
Build 350 native donor fetched by range without any Dusklight member, and the
IPA checked by build-utils/validate_no_dusklight_ipa.py. The Ports rows of
data.sqlite leave only after a checked copy of the database; no game file is
touched. No emulator Core is rebuilt and no engine, helper, skin, cheat,
texture or game box input changes. This gate reads CI evidence; it never reruns
suites. Each part (host, native) of .github/workflows/build492-checks.yml must
have passed on the delivery commit itself, every tested input must be
byte-identical to that commit, and the verdicts (BUILD 492) must cover every
changed input.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import kartpad491_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Build 491 delivery source and its delivery run (checks/native/cold).
DELIVERED='9faa3f9b07f93b4fdca19a0a325a9180fe75b20f'
DELIVERED_RUN=39353891715
BASE=DELIVERED
WORKFLOW='build492-checks.yml'
JOBS={
    'host':'Analysis, delivery Dart suite, Dusklight and Ports removal checks',
    'native':'NeoPlay companion adapters and external display sources for iPhone',
}
PARTS=('host','native')
# Delivery wiring, records, workflows and pins: no product or tested input.
DELIVERY_ONLY={'AGENTS.md','README.md','.github/diagnostics/portsremoval492_delivery.py',
    'build-utils/delivery-492-recipient.pem'}
WORKFLOWS_PREFIX='.github/workflows/'
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS
RPCS3_CORE_PATHS=previous.RPCS3_CORE_PATHS
# The product files Build 492 changes (added, modified or deleted) since 491.
REMOVAL_PRODUCT={
    'assets/images/ports-gaming.webp','assets/legal/Dusklight-CC0-1.0.txt',
    'assets/legal/THIRD_PARTY_NOTICES.md','assets/systems/ports.json',
    'lib/data/datasources/sqlite_database_service.dart','lib/data/datasources/sqlite_service.dart',
    'lib/l10n/dusklight_locale.dart','lib/l10n/ports_locale.dart','lib/l10n/storage_locale.dart',
    'lib/providers/sqlite_config_provider.dart','lib/providers/sqlite_config_provider/scanning.dart',
    'lib/repositories/scraper_repository.dart','lib/repositories/system_repository.dart',
    'lib/screens/game_screen/game_details_card/game_details_card_list.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_emulator_tab.dart',
    'lib/screens/game_screen/game_settings_dialog/game_settings_manage_tab.dart',
    'lib/screens/game_screen/my_games_list.dart','lib/screens/libretro/libretro_consoles_screen.dart',
    'lib/screens/settings_screen/legal_credits_dialog.dart',
    'lib/screens/settings_screen/new_settings_options/widgets/external_display_setting_rows.dart',
    'lib/screens/systems_screen/my_systems_section/system_card.dart',
    'lib/services/console_catalog.dart','lib/services/dusklight_game_identity.dart',
    'lib/services/dusklight_internal_service.dart','lib/services/game/game_launch_service.dart',
    'lib/services/game_launch_manager.dart','lib/services/ports_game_identity.dart',
    'lib/services/retired_ports_backup.dart','lib/services/screenscraper_service.dart',
    'lib/services/storage/storage_categorizer.dart','lib/services/storage/storage_cleanup_planner.dart',
    'lib/services/storage/storage_orphan_detector.dart','lib/services/storage/storage_roots.dart',
    'lib/services/system_art/canvas_es_de_capsules.dart','lib/utils/game_launch_utils.dart',
    'lib/widgets/libretro_engine_panel.dart','lib/widgets/ports_internal_playlist_actions.dart',
    'lib/widgets/system_emulator_settings_dialog.dart',
    'packages/external_display/ios/Classes/ExternalDisplayPlugin.m',
    'packages/external_display/ios/Classes/NeoExternalDisplayCoordinator.h',
    'packages/external_display/lib/external_display.dart',
    'packages/neoplay_bridge/ios/Classes/NPGameHUDAnchor.swift',
    'pubspec.yaml',
}
# Every file of the removed trees is part of the change too.
REMOVED_TREES=('native/dusklight','packages/dusklight_internal_bridge')
REMOVED=('native/dusklight','packages/dusklight_internal_bridge','build-utils/dusklight',
    'build-utils/validate_dusklight_ipa.py','.github/workflows/dusklight-core.yml',
    'assets/legal/Dusklight-CC0-1.0.txt','assets/systems/ports.json','assets/images/ports-gaming.webp',
    'lib/services/dusklight_internal_service.dart','lib/l10n/dusklight_locale.dart','lib/l10n/ports_locale.dart',
    # KartPad stays gone (Build 491).
    'packages/kartpad_internal_bridge','native/kartpad','build-utils/kartpad',
    'lib/services/kartpad_internal_service.dart')


def product():
    paths=set(REMOVAL_PRODUCT)
    for tree in REMOVED_TREES:
        paths|=set(base.command(['git','ls-tree','-r','--name-only',DELIVERED,'--',tree]).splitlines())
    return paths


def tested_paths():
    """Every non-documentation path changed since Build 491 that is not delivery wiring."""
    paths=set(base.command(['git','diff','--name-only',BASE,'HEAD']).splitlines())
    return {path for path in paths if not path.startswith('docs/') and path not in DELIVERY_ONLY
            and not path.startswith(WORKFLOWS_PREFIX)}


def tested_source():
    return base.command(['git','rev-parse','HEAD'])


def records_only(path):
    # Documentation and delivery records: never packaged, never a tested input.
    return path.startswith('docs/') or path in DELIVERY_ONLY


def proofs(head):
    """The latest successful build492-checks.yml run on HEAD, or on an ancestor of
    HEAD when every commit since only touched documentation or delivery records
    (as kartpad491_delivery.py). evidence() still compares every verdict input
    with the files of HEAD, byte for byte."""
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
    present=sorted(p for p in tested if (base.ROOT/p).exists())
    if present:base.command(['git','diff','--exit-code','HEAD','--',*present])
    expected=product()
    for end in (['HEAD'],[]):
        # The product differs from Build 491 exactly by the removal.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        if changed!=expected:raise ValueError('Unexpected product change since Build 491: '+', '.join(sorted(changed^expected)))
        # No Core input changed: the RPCS3 and ARMSX2 Cores, the libretro cores package.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*RPCS3_CORE_PATHS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--','build-utils/libretro'])
        # The texture catalogue, the game box, the engines' bridges and NeoSwap
        # are the Build 491 ones.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--','packages/neo_texture_catalog','native/textures',
            'packages/libretro_internal_bridge','packages/dolphin_internal_bridge','packages/armsx2_internal_bridge',
            'packages/rpcs3_internal_bridge','packages/neo_swap','native/neoswap',
            'native/neoswap-relay','native/neoswap-donation'])
    # Dusklight, the Ports playlist and KartPad are gone for good.
    for gone in REMOVED:
        if (base.ROOT/gone).exists():raise ValueError('Removed component came back: '+gone)
    return {'deliveredBaseline':DELIVERED,'deliveredRun':DELIVERED_RUN,'baselineRecord':BASE,'testedSource':source,
        'changedProductPaths':sorted(expected),'coreRebuilt':False,'dusklightRemoved':True,'portsPlaylistRemoved':True,
        'kartPadRemoved':True,'otherEnginesCataloguesSkinsHelpersUnchanged':True}

rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin
part_run=previous.part_run


def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold'])]
    PROOFS=proofs(tested_source())
    verdicts={}
    with tempfile.TemporaryDirectory(prefix='portsremoval492-proof-') as tmp:
        for part in PARTS:
            run,source,job=PROOFS[part]
            records.append(part_run(run,source,job))
            folder=Path(tmp)/part
            subprocess.run(['gh','run','download',str(run),'--repo','TarbleFR/RewindBox',
                '--name',f'build492-{part}-'+source,'--dir',str(folder)],check=True)
            files=list(folder.rglob(f'{part}-verdict.json'))
            if len(files)!=1:raise ValueError('Ambiguous or missing verdict: '+part)
            raw=files[0].read_bytes();verdicts[part]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
    covered=set()
    for part,(verdict,digest) in verdicts.items():
        if verdict['result']!='passed' or verdict['source']!=PROOFS[part][1] or verdict['build']!=492 or verdict['part']!=part:
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
        ('docs/evidence/kartpad491-delivery.json','docs/evidence/gamebox490-delivery.json') if (base.ROOT/p).is_file()}
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
        print('PASS Build 492 source closure: Build 491 product without Dusklight and the Ports playlist, no Core input changed')
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
    print('PASS Build 491 product without Dusklight and Ports + Build 492 targeted evidence; no suites rerun, no Core rebuilt')

if __name__=='__main__':
    main()
