"""Compose unchanged delivered 477 components with exact 478 data/UI proofs.

This reader verifies identities and successful jobs; no suite or core rebuild.
"""
import gzip
import hashlib
import json
import unified_cheats_delivery as previous

BASE='9ce7566e1421ee65d4ec6f1450c9df08a7a5c2ad'
DELIVERED='38b3c681c575c7b9f0c05e01ef5a0f708cdd09f8'
WORKFLOW='8bb5ea9d38c18b16ade86219d56e0cc71ea05c0a'
DATA='940afd3971180286171dfc4964bcf701e6588d56'
APP='97bd841447263b0d345df7b1b98a345d7e838816'
APP_RUN=39119945539
MEMORY='5c8ea95cda48993caa0ac74fc7eefd1855c2d67c'
DATA_RUN=39119129264
PRODUCT={
    'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatList.m',
    'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz',
    'packages/neo_cheat_catalog/ios/Resources/labels.json',
    'packages/neo_cheat_catalog/ios/Resources/artemis-rpcs3-LICENSE.txt',
    'packages/rpcs3_internal_bridge/ios/Classes/RPCS3UnifiedCheats.mm',
}
INPUTS=PRODUCT|{
    '.github/workflows/cheats478-data.yml','.github/workflows/cheats478-native.yml',
    '.github/diagnostics/cheats478_memory_reuse.py','.github/diagnostics/cheats478_source_reuse.py','AGENTS.md','docs/build478-source-expansion.md',
    'tools/cheats/sources478.json','tools/cheats/unified478.py','tools/cheats/unified478_formats.py',
    'tools/cheats/unified478_fps.py','tools/cheats/fps478_inventory.py','tools/cheats/unified-sources.json',
    'tools/cheats/unified_formats.py','tools/cheats/snapshots/nds-fps-478.json',
    'tools/cheats/unified_adapt.py','tools/cheats/unified_catalogue.py','tools/cheats/unified_browser_labels.py',
    'test/cheats478_sources.py','test/cheats478_sources.mm','test/cheats478_pnach_accept.cpp',
    'test/unified_catalog_browser_ui_test.py','test/unified_catalog_browser_ui_tests.m',
    'native/cheats/catalogue/manifest.json.gz','native/cheats/catalogue/audit.json.gz',
    'native/cheats/catalogue/SOURCES.md','native/cheats/catalogue/supplement478-provenance.json.gz',
    'native/cheats/catalogue/supplement478-native-rejections.json.gz',
    'docs/evidence/cheats478-sources.json','docs/evidence/cheats478-fps.json',
}
DELIVERY_ONLY={
    '.github/diagnostics/cheats478_delivery.py','.github/workflows/retroarch-delivery.yml',
    'build-utils/validate_unified_cheats_ipa.py','build-utils/delivery-478-recipient.pem',
    'AGENTS.md','docs/build478-source-expansion.md','docs/evidence/cheats478-delivery.json',
}

def source_closure():
    receipt=json.loads((previous.ROOT/'docs/evidence/cheats478-sources.json').read_bytes())
    data_paths=INPUTS|{'native/cheats/catalogue/'+p['path'] for p in receipt['newPacks']}
    for args in (['git','diff','--name-only',BASE,'HEAD'],['git','diff','--name-only',BASE]):
        extra=set(previous.command(args).splitlines())-data_paths-DELIVERY_ONLY
        if extra:raise ValueError('Unproved changed inputs: '+', '.join(sorted(extra)))
    tested=data_paths-DELIVERY_ONLY
    previous.command(['git','diff','--exit-code',APP,'HEAD','--',*sorted(tested)])
    previous.command(['git','diff','--exit-code',APP,'--',*sorted(tested)])
    if previous.command(['git','rev-parse',DATA+'^'])!=WORKFLOW:raise ValueError('Generated data parent differs from the exact workflow source')
    changed=set(previous.command(['git','diff','--name-only',DELIVERED,'HEAD','--','packages']).splitlines())
    if not changed.issubset(PRODUCT):raise ValueError('Unproved product changes: '+', '.join(sorted(changed-PRODUCT)))
    # The successful 477 delivery receipt closes all other product, Core,
    # helper, library and skin inputs. None of them is rebuilt for sources.
    previous.command(['git','diff','--exit-code',DELIVERED,'HEAD','--','lib','assets','pubspec.yaml','pubspec.lock',
        'native/neoswap','native/neoswap-relay','native/neoswap-donation','native/nestopia','native/skins',
        'build-utils/libretro','packages/neo_swap'])
    index=(previous.ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()
    if hashlib.sha256(index).hexdigest()!=receipt['manifestSHA256']:raise ValueError('Index differs from exact Apple-tested data')
    if json.loads(gzip.decompress(index))['totals']!=receipt['totals']:raise ValueError('Wrong exact publication counts')
    fps=json.loads((previous.ROOT/'docs/evidence/cheats478-fps.json').read_bytes())
    if fps['manifestSHA256']!=receipt['manifestSHA256']:raise ValueError('FPS inventory differs from this publication')
    return {'baselineReceipt':BASE,'baselineDelivery':DELIVERED,'workflowSource':WORKFLOW,'publishedData':DATA,'testedNativeAndUIKit':APP,'fullIndexMemory':MEMORY,
        'manifestSHA256':receipt['manifestSHA256'],'allOtherProductAndCoreInputsUnchanged':True}

def evidence():
    records=[previous.successful_run(39110222254,DELIVERED,['checks','native','Release device build • cold']),
             previous.component_run(DATA_RUN,WORKFLOW,['publish'],'failure'),
             previous.successful_run(APP_RUN,APP,['apple'])]
    jobs=previous.api(f'actions/runs/{APP_RUN}/jobs?per_page=100')['jobs']
    job=next(j for j in jobs if j['name']=='apple');log=previous.api(f'actions/jobs/{job["id"]}/logs',raw=True)
    receipt=json.loads((previous.ROOT/'docs/evidence/cheats478-sources.json').read_bytes())
    ps=receipt['newProgramsBySystem']
    witnesses=(APP,
        f"PASS exact expansion native: ps2={ps['ps2']} ps3={ps['ps3']} nds={ps['nds']} total={receipt['newPrograms']}",
        'Executed 14 tests, with 0 failures',
        'REUSED exact Linux publication and eight source checks',
        'REUSED successful unchanged full-index memory component')
    for witness in witnesses:
        if witness not in log:raise ValueError('Missing exact native/UIKit witness: '+witness)
    required={'Exact published native programs and changed full-index memory',
        'Compile changed catalogue and RPCS3 helper with the iPhone SDK',
        'Shared installation, revision diagnostics and source notes in UIKit'}
    if not required<={s['name'] for s in job['steps'] if s.get('conclusion')=='success'}:
        raise ValueError('Changed native/SDK/UIKit components did not all pass')
    records[-1].update(checkedOutAppleSource=APP,logSHA256=hashlib.sha256(log.encode()).hexdigest())
    publisher=previous.api('actions/jobs/117650930284/logs',raw=True)
    for witness in (WORKFLOW,'Ran 8 tests','Published 60 FPS selections:'):
        if witness not in publisher:raise ValueError('Missing successful Linux source proof: '+witness)
    records[-2].update(publishedData=DATA,publisherJob=117650930284,
        logSHA256=hashlib.sha256(publisher.encode()).hexdigest())
    memory_job=previous.api('actions/jobs/117651766092')
    if memory_job['head_sha']!=MEMORY or memory_job['conclusion']!='failure':
        raise ValueError('Wrong retained memory component identity')
    memory_log=previous.api('actions/jobs/117651766092/logs',raw=True)
    witness='Full manifest memory: games=51652, file_bytes=7678748, before=2179904, loaded=78857728, after_ten_menus=78874112, retained_growth=16384 bytes'
    if MEMORY not in memory_log or witness not in memory_log:raise ValueError('Missing final index memory witness')
    memory_paths=['packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m',
        'packages/neo_cheat_catalog/ios/Classes/Public/NeoUnifiedCheatCatalog.h',
        'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz','test/unified_catalog_runtime_native.m']
    previous.command(['git','diff','--exit-code',MEMORY,'HEAD','--',*memory_paths])
    records.append({'run':39119416612,'source':MEMORY,'job':117651766092,
        'scope':'successful unchanged full-index memory component only; later staging failed and is corrected by the successful native proof',
        'witness':witness,'logSHA256':hashlib.sha256(memory_log.encode()).hexdigest()})
    paths=('docs/evidence/cheats477-delivery.json','docs/evidence/cheats478-sources.json','docs/evidence/cheats478-fps.json')
    return records,{p:hashlib.sha256((previous.ROOT/p).read_bytes()).hexdigest() for p in paths}

if __name__=='__main__':
    previous.source_closure=source_closure;previous.evidence=evidence;previous.CATALOGUE=APP
    previous.main()
