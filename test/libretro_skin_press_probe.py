#!/usr/bin/env python3
"""Actual LibretroSession + UIKit skin press / core input evidence, macOS CI.

UIKit contacts are scripted; physical touch hardware is not claimed. Real
DeSmuME and PCE run original homebrew, NeoTest covers PSX/NES input profiles.
Third-party reference artwork is downloaded for testing only, never bundled
into the product or checked into this repository.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile
import libretro_simulator_probe as probe

REFERENCES = (
    ('press-atomic','gbc','delta-skins/delta-skins.github.io','61dad28f552051bc05f519f968e913bf243d22eb',
     'gbc/GBC-AtomicPink.deltaskin','d870e53c3728c6b84aeb163b489e03e8ab903ad0927f18ce27dd3235ddcfec84'),
    ('press-complex','nes','LitRitt/emuskins','8f788c6ea9c0cadb15ce700fc4208507c463131c',
     'Skins/LitRitt/Ignited/Orange/NES/skin.deltaskin','3f23a623b4d7d35fc7297c8f4bdd7a6b29e27f58e397ef78b052598a51e7cc69'),
    ('press-ds','nds','Manic-EMU/ManicEMU','fbaeab79c214d5920bb51afa6f2d786fb2b12a58',
     'System.core/DS.manicskin','6ff544f2c1c896df5896387196e4a123b9a40c256bd3a8c0ec5b49ee83209fd1'),
    ('press-psx','psx','Manic-EMU/ManicEMU','fbaeab79c214d5920bb51afa6f2d786fb2b12a58',
     'System.core/PS1.manicskin','e82581ce172af8049fb6a9c610a151cbb12ee224c730c88d7a3f785b350a4778'),
)
SCENARIOS = [
    {'name':'press-atomic','core':'neotest','console':'gbc','content':'content/Shader Pattern.ntc','skinPress':'press-atomic','expect':'run'},
    {'name':'press-ds','core':'desmume','console':'nds','content':'content/shader-pattern.nds','skinPress':'press-ds','expect':'run'},
    {'name':'press-psx','core':'neotest','console':'psx','content':'content/Shader Pattern.ntc','skinPress':'press-psx','expect':'run'},
    {'name':'press-flat-nes','core':'neotest','console':'nes','content':'content/Shader Pattern.ntc','skinPress':'press-flat','expect':'run'},
    {'name':'press-pce','core':'mednafen_pce_fast','console':'pce','content':'content/probe-pce.pce','skinPress':'default','expect':'run'},
    {'name':'press-n64','core':'neotest','console':'n64','content':'content/Shader Pattern.ntc','skinPress':'default','expect':'run'},
    *[{'name':skin,'core':'neotest','console':'nes','content':'content/Shader Pattern.ntc','skinPress':skin,'expect':'run'}
      for skin in ['press-complex','press-texture','press-authored','press-alpha','press-overlap','press-asymmetric','press-separated']],
]


def fixtures(app):
    for identifier, console, repository, revision, path, expected in REFERENCES:
        url=f'https://raw.githubusercontent.com/{repository}/{revision}/{path}'
        with urllib.request.urlopen(url,timeout=60) as response:
            data=response.read(50*1024*1024+1)
        # Manic stores these archives in Git LFS. raw.githubusercontent.com
        # serves the pointer; the pinned media endpoint serves its object.
        if data.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
            pointer=dict(line.split(' ',1) for line in data.decode('ascii').splitlines())
            assert pointer['oid']=='sha256:'+expected and int(pointer['size'])<=50*1024*1024
            media=f'https://media.githubusercontent.com/media/{repository}/{revision}/{path}'
            with urllib.request.urlopen(media,timeout=60) as response:
                data=response.read(50*1024*1024+1)
            assert len(data)==int(pointer['size']), path
        assert hashlib.sha256(data).hexdigest()==expected, path
        folder=app/'SkinFixtures'/identifier
        folder.mkdir(parents=True)
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(data)) as archive:
            for name in archive.namelist():
                assert not name.startswith('/') and '..' not in Path(name).parts
            archive.extractall(folder)
        (folder/'neostation-skin.json').write_text(json.dumps({'consoles':[console]}))


def pick_tablet():
    listing=json.loads(probe.output(['xcrun','simctl','list','devices','available','-j']))
    choices=[(runtime,d['name'],d['udid']) for runtime, devices in listing['devices'].items()
             for d in devices if d.get('isAvailable') and d['name'].startswith('iPad') and 'iOS' in runtime]
    if not choices: raise SystemExit('No iPad simulator available')
    runtime,name,udid=sorted(choices,reverse=True)[0]
    return udid, name+' '+runtime


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cores',required=True)
    parser.add_argument('--inputs',required=True)
    parser.add_argument('--evidence',required=True)
    parser.add_argument('--label',required=True)
    parser.add_argument('--scenario',choices=[s['name'] for s in SCENARIOS])
    parser.add_argument('--device',choices=['iphone','ipad'])
    args=parser.parse_args()
    args.sources=None;args.only=[];args.lot1=False;args.lot2=False;args.official_shaders=False
    probe.SCENARIOS=[s for s in SCENARIOS if not args.scenario or s['name']==args.scenario]
    # These session tests load only their selected cores. Avoid installing
    # unrelated large frameworks into each freshly erased simulator; the
    # pinned binary bytes of the exercised cores remain unchanged.
    used={s['core'] for s in probe.SCENARIOS}
    probe.REAL_CORES=[core for core in probe.REAL_CORES if core in used]
    evidence=Path(args.evidence);evidence.mkdir(parents=True,exist_ok=True)
    problems=[]
    with tempfile.TemporaryDirectory(prefix='skin-press-') as work:
        app,scenarios=probe.assemble(args,probe.BRIDGE,Path(work))
        fixtures(app)
        probe.run(['codesign','--force','--sign','-','--timestamp=none',app])
        for device in ([args.device] if args.device else ['iphone','ipad']):
            selected=scenarios if device=='iphone' else [s for s in scenarios if s['skinPress']!='press-flat']
            config=json.loads((app/'probe-config.json').read_text());config['scenarios']=selected
            (app/'probe-config.json').write_text(json.dumps(config))
            probe.run(['codesign','--force','--sign','-','--timestamp=none',app])
            if device=='ipad':probe.pick_device=pick_tablet
            folder=evidence/device;folder.mkdir()
            outcome=probe.run_in_simulator(app,folder,600)
            (folder/'outcome.json').write_text(json.dumps(outcome,indent=2))
            report=json.loads((folder/'probe.json').read_text()) if (folder/'probe.json').exists() else {'results':[]}
            errors=probe.evaluate(report,selected)
            for result in report.get('results',[]):
                print(json.dumps({'device':device,'name':result['name'],'checks':result.get('skinChecks',[])}),flush=True)
            problems.extend(device+': '+e for e in errors)
    (evidence/'verdict.json').write_text(json.dumps({'source':args.label,'problems':problems,
        'physicalDeviceValidated':False,'contacts':'scripted UIKit','controller':'Apple virtual GCController'},indent=2))
    if problems:raise SystemExit('\n'.join(problems))
    print('Selected actual embedded-session skin scenarios passed (scripted UIKit, Simulator).')

if __name__=='__main__':main()
