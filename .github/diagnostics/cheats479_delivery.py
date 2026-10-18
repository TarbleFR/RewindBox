"""Close changed discovery/UI against exact Apple proofs and delivered 478."""
import gzip,hashlib,json
import unified_cheats_delivery as previous
BASE='ea5e20d7a6fa00bf28dd475ca5936103adb955d0'
DELIVERED='d0107bcdf15d08eaa2b3f72c5d97a87ef204f047'
APP='302f019e949e023fa23b5f94f30d2112c0feaaea'
APP_RUN=39126577930
PRODUCT={'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m',
    'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatList.m',
    'packages/neo_cheat_catalog/ios/Classes/Public/NeoUnifiedCheatCatalog.h'}
TESTED=PRODUCT|{'test/cheats479_runtime.m','test/cheats479_regression.py',
    'test/unified_catalog_browser_ui_tests.m','test/unified_catalog_browser_ui_test.py','.github/workflows/cheats479.yml',
    '.github/diagnostics/cheats479_service_reuse.py'}
DELIVERY_ONLY={'.github/diagnostics/cheats479_delivery.py','.github/workflows/retroarch-delivery.yml',
    'build-utils/validate_unified_cheats_ipa.py','build-utils/delivery-479-recipient.pem','AGENTS.md',
    'docs/build479-fast-cheats.md','docs/evidence/cheats479-delivery.json','docs/evidence/cheats479-performance.json'}
def source_closure():
    for args in (['git','diff','--name-only',BASE,'HEAD'],['git','diff','--name-only',BASE]):
        extra=set(previous.command(args).splitlines())-TESTED-DELIVERY_ONLY
        if extra:raise ValueError('Unproved changed inputs: '+', '.join(sorted(extra)))
    for end in (['HEAD'],[]):previous.command(['git','diff','--exit-code',APP,*end,'--',*sorted(TESTED)])
    changed=set(previous.command(['git','diff','--name-only',DELIVERED,'HEAD','--','packages']).splitlines())
    if changed!=PRODUCT:raise ValueError('Unexpected product composition: '+', '.join(sorted(changed)))
    previous.command(['git','diff','--exit-code',DELIVERED,'HEAD','--','lib','assets','native','pubspec.yaml','pubspec.lock',
        'tools/cheats','build-utils/libretro','packages/neo_swap'])
    previous.command(['git','diff','--exit-code',DELIVERED,'--','lib','assets','native','pubspec.yaml','pubspec.lock','tools/cheats','build-utils/libretro','packages/neo_swap'])
    index=(previous.ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()
    digest=hashlib.sha256(index).hexdigest()
    if digest!='a475a740a2e6251a5638077ffcce53c81afc125acd6fbcfaf97ff28d7602d1a1':raise ValueError('Published 478 index changed')
    return {'baselineDelivery':DELIVERED,'baselineReceipt':BASE,'testedLookupAndFinalUIKit':APP,
        'manifestSHA256':digest,'allSourcePacksAndOtherProductCoreInputsUnchanged':True}
def evidence():
    records=[previous.successful_run(39120442661,DELIVERED,['checks','native','Release device build • cold']),
        {'run':39125808369,'source':'ce585c6bef0f3f714a7dc0f5c005191f74df4c9a',
            'overallConclusion':'failure','successfulSteps':['Actual 478 negative control and 51652-file candidate benchmark',
                'Changed shared installation and integrity behaviour','Changed full-index memory and iPhone SDK']},
        previous.successful_run(APP_RUN,APP,['targeted'])]
    service_run=previous.api('actions/runs/39125808369')
    service_job=previous.api('actions/jobs/117670567809')
    if service_run['head_sha']!=records[1]['source'] or service_run['status']!='completed' or service_run['conclusion']!='failure':
        raise ValueError('Changed service component run identity/status')
    if service_job['run_id']!=39125808369 or service_job['head_sha']!=records[1]['source'] or service_job['conclusion']!='failure':
        raise ValueError('Changed service component job identity/status')
    if not set(records[1]['successfulSteps'])<={s['name'] for s in service_job['steps'] if s.get('conclusion')=='success'}:
        raise ValueError('Missing successful unchanged service component')
    job=next(j for j in previous.api(f'actions/runs/{APP_RUN}/jobs?per_page=100')['jobs'] if j['name']=='targeted')
    log=previous.api(f'actions/jobs/{job["id"]}/logs',raw=True)
    for witness in (APP,'REUSED unchanged 479 service benchmark, 352 checks and full-index memory',
        'Executed 19 tests, with 0 failures','Shared catalogue: 86 complete keys in all twelve languages'):
        if witness not in log:raise ValueError('Missing final SDK/UIKit proof: '+witness)
    required={'Reuse exact successful unchanged service and memory components','Changed iPhone SDK compile and link',
        'Incremental deduplication and all affected direct menu controls in UIKit'}
    if not required<={s['name'] for s in job['steps'] if s.get('conclusion')=='success'}:raise ValueError('Missing successful changed component')
    service=previous.api('actions/jobs/117670567809/logs',raw=True)
    for witness in ('ce585c6bef0f3f714a7dc0f5c005191f74df4c9a','CONFIRMED delivered 478 adds title-only regional/World candidates',
        'PASS 479 compatible edition selection, bounded installed lookup, verified cache; baseline=0',
        'Foundation unified catalogue: 352 behavioral checks passed','Full manifest memory: games=51652'):
        if witness not in service:raise ValueError('Missing successful service component witness: '+witness)
    results={}
    for line in service.splitlines():
        if 'METRICS479 ' in line:
            value=json.loads(line.split('METRICS479 ',1)[1]);results['baseline' if value['baseline'] else 'candidate']=value
    if results['baseline']['initialPerFileChecks']<51652 or results['candidate']['initialPerFileChecks']!=0:
        raise ValueError('Full installed metadata operation bound did not pass')
    records[-2].update(job=117670567809,performance=results,logSHA256=hashlib.sha256(service.encode()).hexdigest(),
        scope='successful unchanged service benchmark, 352 checks and full-index memory only; earlier SDK passed but final changed SDK/UI execute in the final source')
    records[-1].update(job=job['id'],logSHA256=hashlib.sha256(log.encode()).hexdigest(),distinctUIKitScenarios=19,
        sourceAndEngineAcceptance='unchanged source programs and native engine adapters reuse delivered 478; changed lookup/integrity/UI have exact component proofs')
    service_paths=['packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m',
        'packages/neo_cheat_catalog/ios/Classes/Public/NeoUnifiedCheatCatalog.h','test/cheats479_runtime.m',
        'test/cheats479_regression.py','test/cheats477_runtime.m','test/cheats477_regression.py','test/unified_catalog_runtime_native.m',
        'packages/neo_cheat_catalog/ios/Resources','native/cheats/catalogue','test/fixtures/cheats477']
    previous.command(['git','diff','--exit-code','ce585c6bef0f3f714a7dc0f5c005191f74df4c9a','HEAD','--',*service_paths])
    paths=('docs/evidence/cheats478-delivery.json','docs/evidence/cheats478-sources.json','docs/evidence/cheats478-fps.json')
    return records,{p:hashlib.sha256((previous.ROOT/p).read_bytes()).hexdigest() for p in paths}
if __name__=='__main__':
    previous.source_closure=source_closure;previous.evidence=evidence;previous.CATALOGUE=APP;previous.main()
