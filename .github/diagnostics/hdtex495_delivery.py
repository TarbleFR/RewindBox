"""Compose the delivered Build 494 with the Build 495 changes: Mesen as an NES engine and the NES HD packs.

Build 495 is the delivered Build 494 (sharper box backs, another session) plus,
at the maintainer's request of 20 October 2026 (docs/hd-textures-nes-mesen.md):
- Mesen, the official libretro buildbot core for iOS ARM64, added unchanged to
  the delivered 34-core package (lot 3: LibretroCores-4c218620, 35 cores) as
  an alternative NES / Famicom / FDS engine, credited (GPLv3), declared to the
  BIOS checker for disksys.rom (never provided);
- the NES adapter of neo_texture_catalog (nes-rom-sha1 identity, hires.txt
  packs installed in System/HdPacks/<content name>, the core option
  mesen_hdpacks per game, a game switched to Mesen through NeoStation's own
  engine choice when its pack is switched on);
- the expanded index (NES, PSP, PS2 and PS1 packs) and twelve-language texts.
No other Core is rebuilt: the RPCS3, ARMSX2 and Dolphin Cores and the 34 earlier
libretro cores are the delivered ones, byte for byte. This gate reads CI
evidence; it never reruns suites. The host, native, uikit and cores parts of
.github/workflows/hd-textures.yml and the mesen job of
.github/workflows/libretro-simulator.yml must have passed on the tested source,
every tested input must be byte-identical to that source, and the verdicts
(BUILD 495) must cover every changed input.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import gamebox494_delivery as previous
import hdtex489_delivery as catalogue_gate
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Build 494 source and its delivery run (checks/native reused, cold Release).
DELIVERED=''
DELIVERED_RUN=None
# The 35-core package: built by libretro-cores.yml on this commit (Mesen added to the delivered 34).
CORES_SOURCE='4c2186204ce06b50b989689a9c2322068f523a58'
CORES_RUN=39366986940
# Build 495 source tested by hd-textures.yml (push) and libretro-simulator.yml (mesen). Each part: (run, source, job).
TESTED_SOURCE=''
PROOFS={
    'host':(None,TESTED_SOURCE,'Readers, identities, installer, labels, catalogue, contracts and Flutter'),
    'native':(None,TESTED_SOURCE,'Store and adapters on Foundation, iPhone SDK build of every changed source'),
    'uikit':(None,TESTED_SOURCE,'The HD textures page on UIKit with the bundled catalogue'),
}
# The delivered package's binaries against the option, folder and BIOS contracts (no verdict file: job result).
CORES_PROOF=(None,TESTED_SOURCE,'Texture replacement in the pinned libretro cores (N64, PS1, NES) and in Mesen on the buildbot')
# The real Mesen core in the Simulator: 256x240 without a pack, 512x480 with the probe's pack, 256x240 with it off.
SIMULATOR=(None,TESTED_SOURCE,'mesen')
MESEN_SCENARIOS=('mesen-plain-1','mesen-hd-pack-1','mesen-plain-2','mesen-hd-pack-2','mesen-hd-pack-off')
PARTS=('host','native','uikit')

sys.path.insert(0,str(base.ROOT/'test'))
import build486_targeted_test as targeted  # noqa: E402
# The product files Build 495 changes (every one is in the runner's product list).
PRODUCT={
    'assets/data/libretro_bios_requirements.json',
    'assets/legal/libretro/LIBRETRO_CORES.md',
    'assets/legal/libretro/license-sources.json',
    'assets/legal/libretro/mesen-LICENSE',
    'assets/legal/libretro/mesen-README.md',
    'lib/services/libretro_core_catalog.dart',
    'lib/services/texture_catalog_service.dart',
    'native/textures/catalogue/manifest.json.gz',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureCatalogPlugin.m',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureEngines.mm',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureHDPage.m',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureIdentity.h',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureIdentityReader.mm',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureInstall.h',
    'packages/neo_texture_catalog/ios/Classes/NeoTexturePackStore.mm',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureSupport.h',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureSupport.m',
    'packages/neo_texture_catalog/ios/Classes/Public/NeoTextureEngine.h',
    'packages/neo_texture_catalog/ios/Resources/labels.json',
    'packages/neo_texture_catalog/ios/Resources/manifest.json.gz',
    'packages/neo_texture_catalog/lib/neo_texture_catalog.dart',
}
# Native inputs that change: the texture catalogue pod and the libretro session (its HD textures row).
NATIVE_PRODUCT={path for path in PRODUCT if path.startswith(('packages/','native/'))}
# The package: core list and the tool that adds cores to the delivered package (built once, on CORES_SOURCE).
CORES_INPUTS={'build-utils/libretro/cores.json','build-utils/libretro/add_cores.py','.github/workflows/libretro-cores.yml'}
# Inputs of the Simulator proof (the probe app, its scenarios and workflow).
SIMULATOR_INPUTS={'test/libretro_simulator_probe.py','test/libretro_simulator/probe.m','.github/workflows/libretro-simulator.yml'}
TESTED=(set(targeted.PRODUCT)|set(targeted.SUPPORT)|set(targeted.HOST_PYTHON)|set(targeted.DART_TESTS)|set(targeted.PRE_EXISTING)
        |{command[0] for command in targeted.CATALOGUE+targeted.NATIVE+targeted.UIKIT}|SIMULATOR_INPUTS
        |{'tools/textures/probe_cores.py','.github/workflows/hd-textures.yml'})
# Delivery wiring, records, credits and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','docs/HD_TEXTURE_CATALOG_SOURCES.md','.github/diagnostics/hdtex495_delivery.py',
    '.github/workflows/retroarch-delivery.yml','.github/workflows/neoswap-ipa.yml','.github/workflows/libretro-checks.yml',
    'build-utils/delivery-495-recipient.pem'}
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS
RPCS3_CORE_PATHS=previous.RPCS3_CORE_PATHS
# Files another session changed since Build 494, neither packaged nor tested by this build.
OTHER_SESSION=set()

def part_inputs(part):
    return catalogue_gate.part_inputs(part)

def pinned():
    for name,value in (('DELIVERED',DELIVERED),('TESTED_SOURCE',TESTED_SOURCE)):
        if len(value)!=40:raise ValueError(f'{name} is not pinned yet')
    if not DELIVERED_RUN:raise ValueError('DELIVERED_RUN is not pinned yet')
    for part,(run,source,job) in {**PROOFS,'cores':CORES_PROOF,'mesen':SIMULATOR}.items():
        if not run or len(source)!=40:raise ValueError(f'{part} proof is not pinned yet')

def source_closure():
    pinned()
    if not PRODUCT<=set(targeted.PRODUCT):raise ValueError('A Build 495 product file is outside the targeted runner')
    if targeted.BUILD!=495:raise ValueError('The targeted runner does not prove Build 495')
    for end in (['HEAD'],[]):
        paths=set(base.command(['git','diff','--name-only',DELIVERED,*end]).splitlines())
        # Documentation and records (docs/, AGENTS.md) are never packaged nor tested inputs.
        extra={path for path in paths-TESTED-DELIVERY_ONLY-CORES_INPUTS-OTHER_SESSION if not path.startswith('docs/')}
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        # Every tested input is byte-identical to the tested source.
        base.command(['git','diff','--exit-code',TESTED_SOURCE,*end,'--',*sorted(TESTED)])
        # The core list and the package tool are those the 35-core package was built from.
        base.command(['git','diff','--exit-code',CORES_SOURCE,*end,'--','build-utils/libretro',*sorted(CORES_INPUTS)])
    for part,(run,source,job) in {**PROOFS,'cores':CORES_PROOF}.items():
        if source!=TESTED_SOURCE:
            base.command(['git','diff','--exit-code',source,TESTED_SOURCE,'--',*sorted(part_inputs(part) if part in PROOFS else TESTED)])
    if SIMULATOR[1]!=TESTED_SOURCE:
        base.command(['git','diff','--exit-code',SIMULATOR[1],TESTED_SOURCE,'--',*sorted(SIMULATOR_INPUTS|PRODUCT)])
    for end in (['HEAD'],[]):
        # The product differs from delivered 494 exactly by the Build 495 files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        # Catalogue tooling (sources, verification records, research) is never packaged; it is
        # part of the tested inputs above. The package tool and core list are the package's.
        changed-={path for path in changed if path.startswith('tools/textures/')}
        changed-=CORES_INPUTS
        if changed!=PRODUCT:raise ValueError('Unexpected product change since Build 494: '+', '.join(sorted(changed^PRODUCT)))
        # No other Core input changed: the RPCS3 Core of Build 487, the ARMSX2 Core of Build 485.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*RPCS3_CORE_PATHS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS])
        native=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--','packages','native','ios']).splitlines())
        if native!=NATIVE_PRODUCT:raise ValueError('Unexpected native change since Build 494: '+', '.join(sorted(native^NATIVE_PRODUCT)))
    # The package adds Mesen to the delivered 34 cores and nothing else.
    cores=json.loads((base.ROOT/'build-utils/libretro/cores.json').read_text())
    added=[core for core in cores['cores'] if core['id'] not in cores['base']['coreIds']] if 'base' in cores else None
    if added is None or [core['id'] for core in added]!=['mesen'] or len(cores['base']['coreIds'])!=34:
        raise ValueError('The core package is not the delivered 34 cores plus Mesen')
    hosted=(base.ROOT/'native/textures/catalogue/manifest.json.gz').read_bytes()
    bundled=(base.ROOT/'packages/neo_texture_catalog/ios/Resources/manifest.json.gz').read_bytes()
    if hosted!=bundled:raise ValueError('Bundled and hosted HD texture catalogues differ')
    return {'deliveredBaseline':DELIVERED,'deliveredRun':DELIVERED_RUN,'testedSource':TESTED_SOURCE,
        'targetedRuns':{part:{'run':run,'source':source} for part,(run,source,job) in PROOFS.items()},
        'coresProof':{'run':CORES_PROOF[0],'source':CORES_PROOF[1],'job':CORES_PROOF[2]},
        'simulatorRun':{'run':SIMULATOR[0],'source':SIMULATOR[1],'job':SIMULATOR[2]},
        'libretroCores':{'source':CORES_SOURCE,'run':CORES_RUN,'added':['mesen'],'count':35},
        'catalogueSHA256':hashlib.sha256(hosted).hexdigest(),'changedProductPaths':sorted(PRODUCT),
        'changedNativeInputs':sorted(NATIVE_PRODUCT),'coreRebuilt':False,
        'otherEnginesCataloguesSkinsHelpersUnchanged':True}

# The Core pins are Build 487's (through 494): reuse its exact input view and identity checks.
rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin
part_run=previous.part_run

def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold'])]
    # The 35-core package was built by libretro-cores.yml on CORES_SOURCE.
    package=base.api(f'actions/runs/{CORES_RUN}')
    if package['head_sha']!=CORES_SOURCE or package['conclusion']!='success' or package['path']!='.github/workflows/libretro-cores.yml':
        raise ValueError('The libretro cores package run is not the pinned successful one')
    records.append({'part':'libretroCores','run':CORES_RUN,'source':CORES_SOURCE,'conclusion':'success'})
    verdicts={}
    with tempfile.TemporaryDirectory(prefix='hdtex495-proof-') as tmp:
        for part in PARTS:
            run,source,job=PROOFS[part]
            records.append(part_run(run,source,job))
            folder=Path(tmp)/part
            subprocess.run(['gh','run','download',str(run),'--repo','TarbleFR/neostation-ios',
                '--name',f'build486-{part}-'+source,'--dir',str(folder)],check=True)
            files=list(folder.rglob(f'{part}-verdict.json'))
            if len(files)!=1:raise ValueError('Ambiguous or missing verdict: '+part)
            raw=files[0].read_bytes();verdicts[part]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
        records.append(part_run(*CORES_PROOF))
        # The Simulator proof: the mesen job passed (every scenario's required and forbidden
        # frame-size lines), and its report holds the five Mesen scenarios.
        run,source,job=SIMULATOR
        records.append(part_run(run,source,job))
        folder=Path(tmp)/'mesen'
        subprocess.run(['gh','run','download',str(run),'--repo','TarbleFR/neostation-ios',
            '--name','libretro-simulator-mesen-'+source,'--dir',str(folder)],check=True)
        reports=list(folder.rglob('probe.json'))
        if len(reports)!=1:raise ValueError('Ambiguous or missing Simulator report')
        names={r['name'] for r in json.loads(reports[0].read_text())['results']}
        if not set(MESEN_SCENARIOS)<=names:
            raise ValueError('The Simulator report lacks Mesen scenarios: '+', '.join(sorted(set(MESEN_SCENARIOS)-names)))
        records.append({'part':'mesen','run':run,'source':source,'reportSHA256':hashlib.sha256(reports[0].read_bytes()).hexdigest(),
            'scenarios':list(MESEN_SCENARIOS)})
    covered=set()
    for part,(verdict,digest) in verdicts.items():
        if verdict['result']!='passed' or verdict['source']!=PROOFS[part][1] or verdict['build']!=495 or verdict['part']!=part:
            raise ValueError('Wrong targeted proof identity/result: '+part)
        if verdict['coreRebuilt'] is not False or verdict['deviceValidated'] is not False:
            raise ValueError('Targeted verdict claims more than it ran: '+part)
        for path,sha in verdict['inputsSHA256'].items():
            if hashlib.sha256((base.ROOT/path).read_bytes()).hexdigest()!=sha:
                raise ValueError('Changed tested input '+path)
        covered|=set(verdict['inputsSHA256'])
        records.append({'part':part,'run':PROOFS[part][0],'source':PROOFS[part][1],'verdictSHA256':digest,'checks':verdict['checks'],
            'timingsSeconds':verdict['timingsSeconds'],
            **({'preExistingComparison':verdict['preExistingComparison']} if 'preExistingComparison' in verdict else {})})
    # The probe app and the cores job's own inputs are proven by their jobs, not by a verdict file.
    missing={p for p in TESTED-SIMULATOR_INPUTS-{'tools/textures/probe_cores.py','.github/workflows/hd-textures.yml'}
             if (base.ROOT/p).is_file()}-covered
    if missing:raise ValueError('Targeted proof did not close: '+', '.join(sorted(missing)))
    native=verdicts['native'][0]
    if native['xcode']!='Xcode 26.3\nBuild version 17C529' or native['iphoneSDK']!='26.2':
        raise ValueError('Targeted native checks ran on another toolchain')
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/gamebox494-delivery.json','docs/evidence/gamebox493-delivery.json') if (base.ROOT/p).is_file()}
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
        print('PASS Build 495 source closure: delivered 494 product + Mesen (35-core package) and the NES HD textures, no other Core input changed')
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
    print('PASS delivered 494 product + Build 495 Mesen / NES HD textures targeted evidence; no suites rerun, no other Core rebuilt')

if __name__=='__main__':
    main()
