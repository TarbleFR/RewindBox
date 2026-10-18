"""Compose delivered 479, exact source-rights proofs and bounded scraping MD5."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
import unified_cheats_delivery as previous

BASE='964599711fb9813f646a3695c05b968d760c69ae'
RIGHTS_SOURCE='4c5eeba0f4c2abb587806ceb620ea105f14abdf8'
DELIVERED='ff28cf2a63695400ad09d1c61538059d96992cc1'
APP='fe610c9f92c62e5815950d1aecc460d1314ee87e'
APP_RUN=39132169652
RIGHTS_RUN=39131701581
PRODUCT={'lib/utils/optimized_md5_utils.dart','lib/services/screenscraper/rom_hasher.dart'}
TESTED=PRODUCT|{'test/scraping_streaming_md5_test.dart','test/scraping_streaming_md5_test.py',
    '.github/workflows/scraping-streaming-md5.yml'}
DELIVERY_ONLY={'AGENTS.md','docs/build480-scraping-md5.md','docs/evidence/scraping480-delivery.json',
    'docs/evidence/scraping480-validation.json','.github/diagnostics/scraping480_delivery.py',
    '.github/workflows/retroarch-delivery.yml','build-utils/delivery-480-recipient.pem',
    'build-utils/validate_unified_cheats_ipa.py'}
RIGHTS_PRODUCT={'assets/data/libretro_skin_overlays.json','assets/legal/THIRD_PARTY_NOTICES.md',
    'assets/legal/libretro/LIBRETRO_CORES.md','lib/services/libretro_overlay_converter.dart',
    'lib/services/libretro_skin_catalogs.dart','native/cheats/catalogue/SOURCES.md',
    'native/cheats/catalogue/manifest.json.gz',
    'native/cheats/catalogue/packs/pack-3d2c4e9572d2f91c230dc571.json.gz',
    'native/cheats/catalogue/packs/pack-a0a577560bb7fc62f92b9b52.json.gz',
    'native/cheats/catalogue/packs/pack-cdbe34c7759fc24c4051e06a.json.gz',
    'native/cheats/catalogue/packs/pack-e13ef8ccd4892dd04e451d35.json.gz',
    'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatCatalog.m',
    'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz'}

def source_closure():
    for end in (['HEAD'],[]):
        paths=set(previous.command(['git','diff','--name-only',BASE,*end]).splitlines())
        extra=paths-TESTED-DELIVERY_ONLY
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        previous.command(['git','diff','--exit-code',APP,*end,'--',*sorted(TESTED)])
    changed=set(previous.command(['git','diff','--name-only',DELIVERED,RIGHTS_SOURCE,'--',
        'lib','packages','assets','native','pubspec.yaml','pubspec.lock']).splitlines())
    if changed!=RIGHTS_PRODUCT:raise ValueError('Unexpected product changes since delivered 479: '+', '.join(sorted(changed^RIGHTS_PRODUCT)))
    merged=set(previous.command(['git','diff','--name-only',RIGHTS_SOURCE,BASE,'--','lib','packages','assets','native','pubspec.yaml','pubspec.lock']).splitlines())
    if merged!=PRODUCT|{'assets/legal/libretro/LIBRETRO_CORES.md'}:
        raise ValueError('Unexpected concurrent product/provenance change')
    receipt=json.loads((previous.ROOT/'docs/evidence/source-rights-withdrawal.json').read_text())
    manifest=(previous.ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()
    if hashlib.sha256(manifest).hexdigest()!=receipt['manifestSHA256']:
        raise ValueError('Index differs from exact successful source-rights proof')
    return {'deliveredBaseline':DELIVERED,'sourceRightsSnapshot':RIGHTS_SOURCE,'mergedProvenanceSnapshot':BASE,'testedScraping':APP,
        'changedProductPaths':sorted(PRODUCT),'manifestSHA256':receipt['manifestSHA256'],
        'precompiledCoresAndHelpersUnchanged':True}

def evidence():
    records=[previous.successful_run(39127133775,DELIVERED,['checks','native','Release device build • cold']),
        previous.successful_run(RIGHTS_RUN,RIGHTS_SOURCE,['native','overlays']),
        previous.successful_run(APP_RUN,APP,['targeted'])]
    with tempfile.TemporaryDirectory(prefix='scraping480-proof-') as tmp:
        subprocess.run(['gh','run','download',str(APP_RUN),'--repo','TarbleFR/neostation-ios',
            '--name','scraping480-'+APP,'--dir',tmp],check=True)
        files=list(Path(tmp).rglob('verdict.json'))
        if len(files)!=1:raise ValueError('Ambiguous or missing actual MD5 verdict')
        raw=files[0].read_bytes();verdict=json.loads(raw)
    if verdict['result']!='passed' or verdict['source']!=APP or verdict['scenarios']!=5:
        raise ValueError('Wrong targeted proof identity/result')
    for flag in ('baselineWholeFileReadReproducedSafely','nativeFilesStreamed','androidSAFContractUnchanged',
                 'persistentStartCompletionFailureLogsVerified'):
        if verdict[flag] is not True:raise ValueError('Missing targeted hash proof '+flag)
    m=verdict['largeFile']
    if m['fixtureBytes']!=3363110912 or m['digest']!='f70f295bdaa27ba3e3ebc9f6fce9ddb8' or m['extraRss']>=192*1024*1024:
        raise ValueError('Full-size exact digest / memory bound did not pass')
    for path,digest in verdict['inputsSHA256'].items():
        if hashlib.sha256((previous.ROOT/path).read_bytes()).hexdigest()!=digest:
            raise ValueError('Changed tested input '+path)
    if set(verdict['inputsSHA256'])!=TESTED:raise ValueError('Incomplete targeted input closure')
    records[-1].update(verdictSHA256=hashlib.sha256(raw).hexdigest(),largeFile=m,
        scenarios=5,scenariosExecuted=1,scenariosReused=4,reusedComponents=verdict['reusedComponents'],
        concurrentWorkers=6,physicalDeviceCrashReproduced=False)
    receipts={p:hashlib.sha256((previous.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/cheats479-delivery.json','docs/evidence/source-rights-withdrawal.json')}
    return records,receipts

if __name__=='__main__':
    previous.source_closure=source_closure;previous.evidence=evidence;previous.CATALOGUE=APP;previous.main()
