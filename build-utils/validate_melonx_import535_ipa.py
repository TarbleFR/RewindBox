"""Verify the signed IPA contains the tested import flow and retained engine."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import melonximport535_delivery as proof
import validate_melonx_memory533_ipa as retained

IDENTITY='MeloNX-import535-identity.json'
# Old Flutter evidence applies only to unchanged inputs. Changed import code has
# its own current-source test receipt below, never attributed to an old run.
retained.proof.PRODUCT = retained.proof.PRODUCT - proof.IMPORT_INPUTS

def inputs():
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
            for p in sorted(proof.IMPORT_INPUTS | proof.TEST_INPUTS)}

def check_receipt(receipt):
    assert receipt['result']=='passed'
    assert receipt['source']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert receipt['inputs']==inputs()
    assert receipt['negativeControl']=='old post-import scan reopens unrelated ROM files'
    assert receipt['tests']==['test/melonx_import_completion_test.dart',
        'test/melonx_presentation_widgets_test.dart',
        'test/melonx_library_files_test.dart','test/melonx_transfer_test.dart']
    assert receipt['physicalDeviceTested'] is False
    assert receipt['nativeContentInspectionMocked'] is True
    assert receipt['retainedSuites']==dict(
        source='6ddf9d7c8d33de468dae75cdc210073990620f3d', run=40184536490,
        job=121142416733, tests=receipt['tests'][1:], passedTests=39)

def embed(app):
    receipt=json.loads((ROOT/'build/delivery/melonx-import535-tests.json').read_bytes())
    check_receipt(receipt)
    (app/IDENTITY).write_text(json.dumps(receipt,indent=2)+'\n')
    (app/retained.IDENTITY).write_text(json.dumps(retained.expected(),indent=2)+'\n')
    p=retained.presentation
    for key in ('SOURCE','HOST_SOURCE','HOST_RUN','APP_SOURCE','APP_RUN','PRODUCT'):
        setattr(p,key,getattr(retained.proof,key))
    (app/p.IDENTITY).write_text(json.dumps(p.expected(),indent=2)+'\n')

def validate(ipa,build):
    report=retained.validate(ipa,build)
    with zipfile.ZipFile(ipa) as z:
        root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/')
                  and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
        receipt=json.loads(z.read(root+IDENTITY));check_receipt(receipt)
        aot=z.read(root+'Frameworks/App.framework/App')
        for marker in [b'MeloNX import game completed: ',b'choosingFiles',b'importResults']:
            assert marker in aot, ('Import correction missing from compiled Flutter app',marker)
    return dict(report,imports=receipt,compiledImportMarkersVerified=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path)
    p.add_argument('--embed',type=Path);p.add_argument('--build-number',type=int,default=535)
    p.add_argument('--report',type=Path);a=p.parse_args()
    if a.embed:embed(a.embed)
    else:
        assert a.ipa and a.report
        report=validate(a.ipa,a.build_number)
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
