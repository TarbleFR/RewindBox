"""Close the shared installation fix and exact supplemental data against Apple proofs.

The delivered 476 baseline covers unchanged cores, helpers, library and skins.
Only the changed service, list and appended source data need new execution.
"""
import hashlib
import json
import unified_cheats_delivery as previous

BASE='b09f3394bcb8df68014bff216898c80b598d8481'
DELIVERED='314da5e0b40602c50621eb73ec740eb7c9b4da4f'
SERVICE='448c02cb72f50b4b5213a866655886221a8efc1a'
SERVICE_RUN=39109127858
DATA_PARENT='49413f433031435affc70e2f04889eeb7ebf449c'
DATA='49413f433031435affc70e2f04889eeb7ebf449c'
PUBLISHED='db6b9bc95cfe3fc1f6594662bfde3dca9fc0fe17'
DATA_RUN=39109829873
SERVICE_INPUTS={
    'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m',
    'packages/neo_cheat_catalog/ios/Classes/Public/NeoUnifiedCheatCatalog.h',
    'test/cheats477_regression.py','test/cheats477_runtime.m',
    'test/fixtures/cheats477/bladestorm-bles00113.json',
    'test/fixtures/cheats477/gow2-scus97481.json',
    '.github/workflows/cheats477.yml',
}
DATA_INPUTS={
    'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatList.m',
    'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz',
    'packages/neo_cheat_catalog/ios/Resources/labels.json',
    'native/cheats/catalogue/manifest.json.gz',
    'native/cheats/catalogue/audit.json.gz',
    'native/cheats/catalogue/packs/pack-2e1b142f0a03297148b4160e.json.gz',
    'native/cheats/catalogue/SOURCES.md',
    'tools/cheats/unified-sources.json','tools/cheats/unified_adapt.py',
    'tools/cheats/unified_browser_labels.py','tools/cheats/unified477.py',
    'tools/cheats/sources477.json',
    'tools/cheats/snapshots/ps2-pal-477.json',
    'tools/cheats/snapshots/bladestorm-jp-477.json',
    'test/cheats477_editions.py','test/cheats477_editions.mm',
    'test/unified_catalog_browser_ui_tests.m','test/unified_catalog_browser_ui_test.py',
    '.github/workflows/cheats477-data.yml',
    'docs/evidence/cheats477-editions.json',
}
DELIVERY_ONLY={
    '.github/diagnostics/cheats477_delivery.py',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/validate_unified_cheats_ipa.py',
    'build-utils/delivery-477-recipient.pem','AGENTS.md',
    'docs/build477-global-cheats.md','docs/evidence/cheats477-delivery.json',
}

def source_closure():
    allowed=SERVICE_INPUTS|DATA_INPUTS|DELIVERY_ONLY
    for end in ('HEAD',):
        extra=set(previous.command(['git','diff','--name-only',BASE,end]).splitlines())-allowed
        if extra:raise ValueError('Unproved changed inputs: '+', '.join(sorted(extra)))
    extra=set(previous.command(['git','diff','--name-only',BASE]).splitlines())-allowed
    if extra:raise ValueError('Unproved working inputs: '+', '.join(sorted(extra)))
    for ref,paths in ((SERVICE,SERVICE_INPUTS),(DATA,DATA_INPUTS)):
        previous.command(['git','diff','--exit-code',ref,'HEAD','--',*sorted(paths)])
        previous.command(['git','diff','--exit-code',ref,'--',*sorted(paths)])
    previous.command(['git','diff','--exit-code',DELIVERED,BASE,'--','packages','lib','assets','native','tools','pubspec.yaml','pubspec.lock'])
    if DATA!=DATA_PARENT and previous.command(['git','rev-parse',DATA+'^'])!=DATA_PARENT:
        raise ValueError('Generated data must descend from the exact workflow source')
    previous.command(['git','diff','--exit-code',PUBLISHED,DATA,'--',
        'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz',
        'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m'])
    receipt=json.loads((previous.ROOT/'docs/evidence/cheats477-editions.json').read_bytes())
    index=(previous.ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()
    if hashlib.sha256(index).hexdigest()!=receipt['manifestSHA256']:
        raise ValueError('Index differs from exact edition proof')
    return {'baselineDelivery':DELIVERED,'baselineReceipt':BASE,'testedService':SERVICE,
            'testedDataAndFinalUIKit':DATA,'dataWorkflowSource':DATA_PARENT,
            'manifestSHA256':receipt['manifestSHA256'],'allOtherProductAndCoreInputsUnchanged':True}

def evidence():
    records=[previous.successful_run(39106631911,DELIVERED,['checks','native','Release device build • cold']),
             previous.successful_run(SERVICE_RUN,SERVICE,['targeted']),
             previous.successful_run(DATA_RUN,DATA_PARENT,['publish','apple']),
             previous.component_run(39109583367,'62144045a381fcfd27cd2cb668e895dabf8ef4fe',['publish'],'failure')]
    # The Apple job explicitly checks out the generated child, rather than its
    # workflow parent's index. Verify that exact identity in its retained log.
    jobs=previous.api(f'actions/runs/{DATA_RUN}/jobs?per_page=100')['jobs']
    apple=next(job for job in jobs if job['name']=='apple')
    log=previous.api(f'actions/jobs/{apple["id"]}/logs',raw=True)
    for witness in (DATA,'PASS exact supplement: five editions / 16 native programs',
                    'Executed 11 tests, with 0 failures'):
        if witness not in log:raise ValueError('Missing exact edition/native witness: '+witness)
    records[-2]['checkedOutAppleSource']=DATA
    memory_log=previous.api('actions/jobs/117622682323/logs',raw=True)
    if PUBLISHED not in memory_log or 'Full manifest memory: games=44794' not in memory_log:
        raise ValueError('Missing unchanged full-index memory witness')
    records[-1].update(fullIndexMemorySource=PUBLISHED,fullIndexMemoryJob=117622682323,
                       scope='successful publisher and full-index memory probe only; later native fixture assertion failed')
    paths=('docs/evidence/cheats476-delivery.json','docs/evidence/cheats477-editions.json')
    return records,{p:hashlib.sha256((previous.ROOT/p).read_bytes()).hexdigest() for p in paths}

if __name__=='__main__':
    previous.source_closure=source_closure
    previous.evidence=evidence
    previous.CATALOGUE=DATA
    previous.main()
