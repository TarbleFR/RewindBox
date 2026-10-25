"""Bind the tested Apple backend, audio handoff and automatic update flow to the IPA."""
import argparse, hashlib, json, subprocess, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import melonxaudio537_delivery as proof
import melonximport535_delivery as imports535
import validate_melonx_memory533_ipa as retained

IDENTITY='MeloNX-audio-update537-identity.json'
# Historical donor/display evidence is kept only for unchanged source inputs.
# Changed files below carry their new 537 evidence instead.
retained.proof.PRODUCT=retained.proof.PRODUCT-imports535.IMPORT_INPUTS-proof.CHANGED
retained.proof.MELONX_SOURCE=proof.MELONX_SOURCE
retained.proof.MELONX_RUN=proof.MELONX_RUN

def check_inputs(receipt):
    assert receipt['result']=='passed' and receipt['physicalDeviceTested'] is False
    for p,h in receipt['inputs'].items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p

def expected():
    imports=json.loads((ROOT/'build/delivery/melonx-import537-tests.json').read_text())
    proof.validate_local_imports(imports)
    audio=json.loads((ROOT/'dist/melonx/apple-audio-update-checks.json').read_text())
    host=json.loads((ROOT/'dist/melonx-host/audio-ownership.json').read_text())
    check_inputs(audio);check_inputs(host)
    assert host['sessionDouble'] and host['iphoneSDKTypecheck']
    return dict(source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        coreSource=proof.MELONX_SOURCE,coreRun=proof.MELONX_RUN,hostSource=proof.HOST_SOURCE,hostRun=proof.HOST_RUN,
        imports=imports,audio=audio,host=host,physicalDeviceTested=False)

def embed(app):
    (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')
    (app/retained.IDENTITY).write_text(json.dumps(retained.expected(),indent=2)+'\n')
    presentation=retained.presentation
    for key in ('SOURCE','HOST_SOURCE','HOST_RUN','APP_SOURCE','APP_RUN','PRODUCT'):
        setattr(presentation,key,getattr(retained.proof,key))
    (app/presentation.IDENTITY).write_text(json.dumps(presentation.expected(),indent=2)+'\n')

def contains(data,text):
    return any(encoded in data for encoded in [text.encode(),text.encode('utf-16le'),text.encode('utf-16le')[:-1]])

def validate(ipa,build):
    report=retained.validate(ipa,build)
    with zipfile.ZipFile(ipa) as z:
        root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
        receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
        identity=json.loads(z.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
        assert identity['host']==proof.MELONX_SOURCE
        for p in ['native/melonx/EmbeddedAddons.cs','native/melonx/EmbeddedAddonSelection.cs','native/melonx/EmbeddedContent.cs','build-utils/melonx/adapt_apple_audio.py']:
            assert identity['adaptations'][p]==hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),p
        core=z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
        for text in ['Apple AVAudioEngine; rate:','startup lead ms: 20','restartDeferred','ambiguousUpdate','addonWrongGame','playAtTime:','hostTimeForSeconds:']:
            assert contains(core,text),text
        host=z.read(root+'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
        front=z.read(root+'Frameworks/external_folder_access.framework/external_folder_access')
        assert b'RewindBox.MeloNX.AudioOwnership' in host and b'RewindBox.MeloNX.AudioOwnership' in front
        assert b'ownershipRestored' in host and b'beforeRun' in host
        dart=z.read(root+'Frameworks/App.framework/App')
        for marker in ['updateGameMissing','ambiguousUpdate','importResults','MeloNX update target metadata unavailable: ']:
            assert contains(dart,marker),marker
    return dict(report,appleAudioAndAutomaticUpdates=receipt,compiledCorrectionMarkersVerified=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
    p.add_argument('--build-number',type=int,default=537);p.add_argument('--report',type=Path);a=p.parse_args()
    if a.embed: embed(a.embed)
    else:
        assert a.ipa and a.report
        report=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
