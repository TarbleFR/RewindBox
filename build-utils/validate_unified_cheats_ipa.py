"""Inspect the actual packaged unified index and all four native consumers."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import plistlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def validate(ipa, build):
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        apps = {n.split('/')[1] for n in names if n.startswith('Payload/') and '.app/' in n}
        if len(apps) != 1:
            raise ValueError('Expected exactly one app')
        root = 'Payload/' + apps.pop() + '/'
        info = plistlib.loads(z.read(root + 'Info.plist'))
        if info['CFBundleVersion'] != str(build):
            raise ValueError('Wrong IPA build')
        matches = [n for n in names if n.startswith(root) and n.endswith('/NeoCheatCatalog.bundle/manifest.json.gz')]
        if len(matches) != 1:
            raise ValueError('Missing or duplicated unified resource bundle')
        data = z.read(matches[0])
        expected = (ROOT / 'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()
        if data != expected:
            raise ValueError('Packaged index differs from the Apple-tested final index')
        manifest = json.loads(gzip.decompress(data))
        if build >= 480:
            # From 586 the hosted index is the one left after the 28 October withdrawal of the unlicensed
            # 60 FPS programs, and the app bundles its origin publication (v2): same games and chunks.
            withdrawal='source-rights-withdrawal-fps478.json' if build >= 586 else 'source-rights-withdrawal.json'
            receipt=json.loads((ROOT/'docs/evidence'/withdrawal).read_bytes())
            counts=(receipt['totals']['games'],receipt['preservedPacks']+len(receipt['replacedPacks']),receipt['totals']['programs'])
            hosted=data
            if build >= 586:
                origin=json.loads((ROOT/'native/cheats/catalogue/v2/VALIDATION.json').read_bytes())
                if data!=(ROOT/'native/cheats/catalogue/v2/manifest.json.gz').read_bytes() or (
                        hashlib.sha256(data).hexdigest(),len(data))!=(origin['manifest_sha256'],origin['manifest_bytes']):
                    raise ValueError('Packaged index differs from the origin publication')
                hosted=(ROOT/'native/cheats/catalogue/manifest.json.gz').read_bytes()
                strip=lambda game:{k:v for k,v in game.items() if k!='pack_id'}
                if [strip(g) for g in manifest['games']]!=[strip(g) for g in json.loads(gzip.decompress(hosted))['games']]:
                    raise ValueError('Origin publication lists other games or chunks than the hosted index')
            if hashlib.sha256(hosted).hexdigest()!=receipt['manifestSHA256']:
                raise ValueError('Packaged index differs from exact source-rights proof')
            aot=z.read(root+'Frameworks/App.framework/App')
            for marker in (b'[ScrapingMD5] start file=',b'[ScrapingMD5] completed file=',b'[ScrapingMD5] failed file='):
                if marker not in aot:raise ValueError('Scraping diagnostics missing from actual AOT')
        elif build >= 478:
            receipt=json.loads((ROOT/'docs/evidence/cheats478-sources.json').read_bytes())
            counts=(receipt['totals']['games'],receipt['preservedPackCount']+len(receipt['newPacks']),receipt['totals']['programs'])
            if hashlib.sha256(data).hexdigest()!=receipt['manifestSHA256']:
                raise ValueError('Packaged expansion differs from exact native-tested receipt')
        else:
            counts=(44794,859,2353299) if build >= 477 else (44789,858,2353283)
        if (len(manifest['games']),len(manifest['packs']),manifest['totals']['programs']) != counts:
            raise ValueError('Wrong final publication counts')
        notice=matches[0].rsplit('/',1)[0]+'/gow3-0100-LICENSE.txt'
        if z.read(notice)!=(ROOT/'packages/neo_cheat_catalog/ios/Resources/gow3-0100-LICENSE.txt').read_bytes():
            raise ValueError('Source MIT notice missing from actual app resource')
        if build >= 478 and z.read(matches[0].rsplit('/',1)[0]+'/artemis-rpcs3-LICENSE.txt')!=(ROOT/'packages/neo_cheat_catalog/ios/Resources/artemis-rpcs3-LICENSE.txt').read_bytes():
            raise ValueError('Artemis RPCS3 source MIT notice missing from actual app resource')
        binaries = {}
        for name in ('neo_cheat_catalog', 'libretro_internal_bridge',
                     'armsx2_internal_bridge', 'dolphin_internal_bridge', 'rpcs3_internal_bridge'):
            binary = z.read(root + f'Frameworks/{name}.framework/{name}')
            if b'NeoUnifiedCheatBrowser' not in binary:
                raise ValueError('Unified browser not linked into ' + name)
            if name in ('neo_cheat_catalog','armsx2_internal_bridge','dolphin_internal_bridge','rpcs3_internal_bridge') and b'NeoUnifiedCheatList' not in binary:
                raise ValueError('Direct list missing from '+name)
            if name == 'rpcs3_internal_bridge' and (b'ps3-static-be32' not in binary or b'PPU executable hash: PPU-' not in binary):
                raise ValueError('Actual PPU/static patch binding missing')
            if name == 'libretro_internal_bridge' and b'installedProgramsForIdentity:' not in binary:
                raise ValueError('Arcade boot discovery missing')
            if name == 'neo_cheat_catalog' and b'NeoUnifiedCheatCatalog' not in binary:
                raise ValueError('Shared catalogue implementation missing')
            if name == 'neo_cheat_catalog' and build >= 476:
                for marker in (b'installAllForIdentity:progress:completion:',b'bundled-index.json',b'cached_pack',b'progressPacks'):
                    if marker not in binary:
                        raise ValueError('Packaged PS2/PS3 follow-up is missing '+marker.decode())
            if name == 'neo_cheat_catalog' and build >= 477:
                for marker in (b'NeoUnifiedCheatCatalogProgressNotification',b'installation.json',b'enqueuePack:manifest:priority:completion:',b'resumeDownload'):
                    if marker not in binary:
                        raise ValueError('Packaged common installation fix is missing '+marker.decode())
            if name == 'neo_cheat_catalog' and build >= 478:
                for marker in (b'detectedEdition',b'otherRevisions',b'explainMissingRevision:generation:',b'60fps'):
                    if marker not in binary:
                        raise ValueError('Packaged version/FPS source-note UI is missing '+marker.decode())
            if name == 'neo_cheat_catalog' and build >= 479:
                for marker in (b'getattrlistbulk', b'poolForIdentity:', b'distinctSelections:identity:links:', b'loadGames:context:index:generation:', b'execution_key'):
                    if marker not in binary:
                        raise ValueError('Packaged compatible discovery/streaming fix is missing '+marker.decode())
            if name == 'neo_cheat_catalog' and build >= 480 and b'pokemonfrance' not in binary:
                raise ValueError('Withheld-source cache guard missing')
            if name == 'neo_cheat_catalog' and build >= 586:
                for marker in (b'resolveOriginPack', b'native/cheats/catalogue/v2/manifest.json.gz', b'Origin downloads are unavailable'):
                    if marker not in binary:
                        raise ValueError('Packaged origin publication is missing '+marker.decode())
            binaries[name] = hashlib.sha256(binary).hexdigest()
        if any('/packs/pack-' in n and n.endswith('.json.gz') for n in names):
            raise ValueError('Downloadable full packs must not inflate the IPA')
    return {'result': 'passed', 'build': build, 'manifestSHA256': hashlib.sha256(data).hexdigest(),
            'manifestBytes': len(data), 'transportParts': counts[0], 'packs': counts[1],
            'programs': counts[2], 'frameworksSHA256': binaries,
            'indexBundled': True, 'packsBundled': False,
            'ipaSHA256': hashlib.sha256(ipa.read_bytes()).hexdigest(),
            'physicalDeviceValidated': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('ipa', type=Path)
    p.add_argument('--build-number', type=int, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    result = validate(a.ipa, a.build_number)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, indent=2) + '\n')
    print('PASS final unified index, shared implementation and four compiled consumers')
