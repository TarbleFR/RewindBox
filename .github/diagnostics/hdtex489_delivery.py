"""Compose the delivered Build 488 with the Build 489 changes: Beetle PSX HW in Vulkan and verified manual packs.

Build 489 gives Beetle PSX HW a Vulkan context (MoltenVK) instead of the
OpenGL ES 3 preference its renderer choice never accepted, relaunches once on
its software renderer when no Vulkan device can be made, locks its HD texture
options (folder "save", no dump, bounded lazy caches), adds the PS1 adapter of
neo_texture_catalog (ps1-disc-serial identity, <content>-texture-replacements
beside the memory cards, Track + Replace per game, the running core's report on
the page), and lets a manual pack carry the author's file verified on CI
(download.verified), installed only from that exact file. No emulator Core is
rebuilt: the pinned Beetle PSX HW binary, the RPCS3 Core of Build 487, the
ARMSX2 Core of Build 485 and every other engine, helper, skin and cheat input
are the delivered Build 488 product. This gate reads CI evidence; it never
reruns suites. Each part (host, native, uikit) of .github/workflows/hd-textures.yml
and the Beetle job of .github/workflows/libretro-simulator.yml must have passed
on the tested source, every tested input must be byte-identical to that source,
and the verdicts (BUILD 489) must cover every changed input.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import hdtex488_delivery as previous
base=previous.base  # unified_cheats_delivery: command, api, successful_run, ROOT

# Branch head before this cycle's product push: the Build 488 records on Claude.
BASE='984ade52a2c55f539d4b362e1019aadaf71c30ba'
# Build 488 source and its delivery run (checks/native reused, cold Release).
DELIVERED='2bdca0d4b7a353af17016c528d2cf38ecacc9e9b'
DELIVERED_RUN=39267021460
# Build 489 source tested by hd-textures.yml and libretro-simulator.yml. Each part: (run, source, job).
TESTED_SOURCE='7c6a86e425f678607a885d3be70bb64221919732'
PROOFS={
    'host':(39337036938,TESTED_SOURCE,'Readers, identities, installer, labels, catalogue, contracts and Flutter'),
    'native':(39337040395,TESTED_SOURCE,'Store and adapters on Foundation, iPhone SDK build of every changed source'),
    'uikit':(39337043258,TESTED_SOURCE,'The HD textures page on UIKit with the bundled catalogue'),
}
# The real Beetle PSX HW core in Vulkan in the Simulator (frame, pack, off): (run, source, job).
SIMULATOR=(39337045728,TESTED_SOURCE,'beetle')
PARTS=('host','native','uikit')

sys.path.insert(0,str(base.ROOT/'test'))
import build486_targeted_test as targeted  # noqa: E402
# The product files Build 489 changes (every one is in the runner's product list).
PRODUCT={
    'lib/services/libretro_core_catalog.dart',
    'lib/services/libretro_internal_service.dart',
    'lib/services/libretro_resolution.dart',
    'lib/services/texture_catalog_service.dart',
    'native/textures/catalogue/manifest.json.gz',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreHost.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroCoreHost.m',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSession.m',
    # The device's A1R5G5B5 support read before Beetle loads (no crash on a device without it).
    'packages/libretro_internal_bridge/ios/Classes/LibretroVulkanRenderer.h',
    'packages/libretro_internal_bridge/ios/Classes/LibretroVulkanRenderer.m',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureCatalog.m',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureEngines.mm',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureHDPage.m',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureIdentity.h',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureIdentityReader.mm',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureInstall.h',
    'packages/neo_texture_catalog/ios/Classes/NeoTexturePackStore.mm',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureSupport.h',
    'packages/neo_texture_catalog/ios/Classes/NeoTextureSupport.m',
    'packages/neo_texture_catalog/ios/Classes/Public/NeoTextureEngine.h',
    'packages/neo_texture_catalog/ios/Classes/Public/NeoTextureHDPage.h',
    'packages/neo_texture_catalog/ios/Classes/Public/NeoTexturePackStore.h',
    'packages/neo_texture_catalog/ios/Resources/labels.json',
    'packages/neo_texture_catalog/ios/Resources/manifest.json.gz',
}
# Inputs of the Simulator proof (the probe app, its scenarios and workflow).
SIMULATOR_INPUTS={'test/libretro_simulator_probe.py','test/libretro_simulator/probe.m','test/libretro_simulator/beetle_lifecycle_probe.h',
    '.github/workflows/libretro-simulator.yml',
    # The resolution rules the probe app is given (Beetle's renderer list), also read by libretro_resolution_test.dart.
    'test/fixtures/libretro_resolution/native_rules.json'}
TESTED=(set(targeted.PRODUCT)|set(targeted.SUPPORT)|set(targeted.HOST_PYTHON)|set(targeted.DART_TESTS)|set(targeted.PRE_EXISTING)
        |{command[0] for command in targeted.CATALOGUE+targeted.NATIVE+targeted.UIKIT}|SIMULATOR_INPUTS)
# Delivery wiring, records, credits and pins: no product or Core input.
DELIVERY_ONLY={'AGENTS.md','docs/HD_TEXTURE_CATALOG_SOURCES.md','.github/diagnostics/hdtex489_delivery.py',
    '.github/workflows/retroarch-delivery.yml','.github/workflows/neoswap-ipa.yml','build-utils/verify_delivery_reuse.py',
    # The core option contract run with the pinned binaries by libretro-checks.yml (locked Beetle keys and values).
    'test/libretro_core_options_test.py'}
PRODUCT_PATHS=previous.PRODUCT_PATHS
ARMSX2_CORE_INPUTS=previous.ARMSX2_CORE_INPUTS
RPCS3_CORE_PATHS=previous.RPCS3_CORE_PATHS

def part_inputs(part):
    return previous.part_inputs(part)

def source_closure():
    for name,value in (('BASE',BASE),('DELIVERED',DELIVERED),('TESTED_SOURCE',TESTED_SOURCE)):
        if len(value)!=40:raise ValueError(f'{name} is not pinned yet')
    if not DELIVERED_RUN:raise ValueError('DELIVERED_RUN is not pinned yet')
    for part,(run,source,job) in {**PROOFS,'beetle':SIMULATOR}.items():
        if not run or len(source)!=40:raise ValueError(f'{part} proof is not pinned yet')
    if not PRODUCT<=set(targeted.PRODUCT):raise ValueError('A Build 489 product file is outside the targeted runner')
    for end in (['HEAD'],[]):
        paths=set(base.command(['git','diff','--name-only',BASE,*end]).splitlines())
        # Documentation and records (docs/, AGENTS.md) are never packaged nor tested inputs.
        extra={path for path in paths-TESTED-DELIVERY_ONLY if not path.startswith('docs/')}
        if extra:raise ValueError('Unvalidated changed inputs: '+', '.join(sorted(extra)))
        # Every tested input is byte-identical to the tested source.
        base.command(['git','diff','--exit-code',TESTED_SOURCE,*end,'--',*sorted(TESTED)])
    for part,(run,source,job) in PROOFS.items():
        if source!=TESTED_SOURCE:
            base.command(['git','diff','--exit-code',source,TESTED_SOURCE,'--',*sorted(part_inputs(part))])
    if SIMULATOR[1]!=TESTED_SOURCE:
        base.command(['git','diff','--exit-code',SIMULATOR[1],TESTED_SOURCE,'--',*sorted(SIMULATOR_INPUTS|set(PRODUCT))])
    for end in (['HEAD'],[]):
        # The product differs from delivered 488 exactly by the Build 489 files.
        changed=set(base.command(['git','diff','--name-only',DELIVERED,*end,'--',*PRODUCT_PATHS]).splitlines())
        # Catalogue tooling (sources, verification records, research) is never packaged;
        # it is part of the tested inputs above.
        changed-={path for path in changed if path.startswith('tools/textures/')}
        if changed!=PRODUCT:raise ValueError('Unexpected product change since Build 488: '+', '.join(sorted(changed^PRODUCT)))
        # No Core input changed: the RPCS3 Core and bridge of Build 487, the ARMSX2 Core of Build 485.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*RPCS3_CORE_PATHS])
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--',*ARMSX2_CORE_INPUTS])
        # The libretro cores package (Beetle PSX HW included) is the delivered one.
        base.command(['git','diff','--exit-code',DELIVERED,*end,'--','build-utils/libretro'])
    hosted=(base.ROOT/'native/textures/catalogue/manifest.json.gz').read_bytes()
    bundled=(base.ROOT/'packages/neo_texture_catalog/ios/Resources/manifest.json.gz').read_bytes()
    if hosted!=bundled:raise ValueError('Bundled and hosted HD texture catalogues differ')
    return {'deliveredBaseline':DELIVERED,'baselineRecord':BASE,'testedSource':TESTED_SOURCE,
        'targetedRuns':{part:{'run':run,'source':source} for part,(run,source,job) in PROOFS.items()},
        'simulatorRun':{'run':SIMULATOR[0],'source':SIMULATOR[1],'job':SIMULATOR[2]},
        'catalogueSHA256':hashlib.sha256(hosted).hexdigest(),'changedProductPaths':sorted(PRODUCT),'coreRebuilt':False,
        'otherEnginesCataloguesSkinsHelpersUnchanged':True}

# The Core pins are Build 487's (through 488): reuse its exact input view and identity checks.
rpc_core_input_view=previous.rpc_core_input_view
validate_rpc_core_identity=previous.validate_rpc_core_identity
validate_rpc_core_pin=previous.validate_rpc_core_pin
part_run=previous.part_run

def evidence():
    records=[base.successful_run(DELIVERED_RUN,DELIVERED,['checks','native','Release device build • cold'])]
    verdicts={}
    with tempfile.TemporaryDirectory(prefix='hdtex489-proof-') as tmp:
        for part in PARTS:
            run,source,job=PROOFS[part]
            records.append(part_run(run,source,job))
            folder=Path(tmp)/part
            subprocess.run(['gh','run','download',str(run),'--repo','TarbleFR/neostation-ios',
                '--name',f'build486-{part}-'+source,'--dir',str(folder)],check=True)
            files=list(folder.rglob(f'{part}-verdict.json'))
            if len(files)!=1:raise ValueError('Ambiguous or missing verdict: '+part)
            raw=files[0].read_bytes();verdicts[part]=(json.loads(raw),hashlib.sha256(raw).hexdigest())
        # The Simulator proof: the beetle job passed, and its report shows Beetle in Vulkan
        # presenting the GPU's picture, the probe's pack reported as exactly its valid
        # replacement files (with Track + Replace Textures) through the lifecycle, and
        # replacement off reported as such. The Simulator cannot run Beetle's CPU-to-VRAM
        # copies (texture uploads, state loads): no texture is replaced on screen there.
        run,source,job=SIMULATOR
        records.append(part_run(run,source,job))
        folder=Path(tmp)/'beetle'
        subprocess.run(['gh','run','download',str(run),'--repo','TarbleFR/neostation-ios',
            '--name','libretro-simulator-beetle-'+source,'--dir',str(folder)],check=True)
        reports=list(folder.rglob('probe.json'))
        if len(reports)!=1:raise ValueError('Ambiguous or missing Simulator report')
        results={r['name']:r for r in json.loads(reports[0].read_text())['results']}
        statuses={name:(results.get(name) or {}).get('beetleStatus') or {} for name in ('beetle-vulkan-frame','beetle-vulkan-pack','beetle-vulkan-off')}
        if any(status.get('renderer')!='vulkan' for status in statuses.values()):
            raise ValueError('The Simulator report does not show Beetle in Vulkan')
        pack=results.get('beetle-vulkan-pack') or {}
        if not statuses['beetle-vulkan-pack'].get('replace') or statuses['beetle-vulkan-pack'].get('recognized')!=pack.get('beetleReplacementsPrepared') \
                or not pack.get('beetleReplacementsPrepared'):
            raise ValueError('The Simulator report does not show the replacement files reported with replacement on')
        if statuses['beetle-vulkan-off'].get('replace') is not False:
            raise ValueError('The Simulator report does not show replacement off')
        # Pause, background, state save, rotation and audio, the pack still reported after them
        # (a state load is not run in the Simulator: its Metal refuses Beetle's linear textures).
        lifecycle=pack.get('beetleLifecycle') or []
        if len(lifecycle)!=13 or not all(check.get('passed') for check in lifecycle):
            raise ValueError('The Simulator report does not show the Beetle lifecycle checks passing')
        records.append({'part':'beetle','run':run,'source':source,'reportSHA256':hashlib.sha256(reports[0].read_bytes()).hexdigest(),
            'beetleStatus':statuses,'replacementFilesWritten':pack.get('beetleReplacementsPrepared'),
            'lifecycleChecks':[check['name'] for check in lifecycle]})
    covered=set()
    for part,(verdict,digest) in verdicts.items():
        if verdict['result']!='passed' or verdict['source']!=PROOFS[part][1] or verdict['build']!=489 or verdict['part']!=part:
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
    missing={p for p in TESTED-SIMULATOR_INPUTS if (base.ROOT/p).is_file()}-covered
    if missing:raise ValueError('Targeted proof did not close: '+', '.join(sorted(missing)))
    native=verdicts['native'][0]
    if native['xcode']!='Xcode 26.3\nBuild version 17C529' or native['iphoneSDK']!='26.2':
        raise ValueError('Targeted native checks ran on another toolchain')
    receipts={p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in
        ('docs/evidence/hdtex488-delivery.json','docs/evidence/rpcs3diag487-delivery.json') if (base.ROOT/p).is_file()}
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
        print('PASS Build 489 source closure: delivered 488 product + tested Beetle PSX HW / verified manual pack changes, no Core input changed')
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
    print('PASS delivered 488 product + Build 489 Beetle PSX HW / verified manual pack targeted evidence; no suites rerun, no Core rebuilt')

if __name__=='__main__':
    main()
