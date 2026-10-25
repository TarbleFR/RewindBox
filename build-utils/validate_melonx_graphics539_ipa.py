#!/usr/bin/env python3
"""Retain audio/host proofs and bind the latest graphics-journal fix to its rebuilt engine."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path
import validate_melonx_audio537_ipa as previous
from rpcs3cell539_delivery import MELONX_SOURCE,MELONX_RUN

ROOT=Path(__file__).resolve().parents[1]
IDENTITY='MeloNX-graphics539-identity.json'
SESSION='native/melonx/EmbeddedSession.cs'
previous.proof.MELONX_SOURCE=MELONX_SOURCE
previous.proof.MELONX_RUN=MELONX_RUN
previous.retained.proof.MELONX_SOURCE=MELONX_SOURCE
previous.retained.proof.MELONX_RUN=MELONX_RUN
# This one changed file is covered below by the exact new source, regression
# receipt, compiled prefix and rebuilt engine adaptation hash, not by533.
previous.retained.proof.PRODUCT=previous.retained.proof.PRODUCT-{SESSION}

def expected():
    receipt=json.loads((ROOT/'docs/evidence/melonx-effective-graphics-journal.json').read_bytes())
    assert receipt['result']=='passed' and receipt['summary'].startswith('PASS 22 ')
    assert not receipt['gpuRenderingTested'] and not receipt['deviceTested']
    for p,h in receipt['inputs'].items():
        data=(ROOT/p).read_bytes()
        assert hashlib.sha256(data).hexdigest()==h,p
        assert data==subprocess.check_output(['git','show',MELONX_SOURCE+':'+p],cwd=ROOT),p
    old=subprocess.check_output(['git','show',receipt['baseline']+':'+SESSION],cwd=ROOT)
    new=(ROOT/SESSION).read_bytes()
    assert old.count(b'FormattableString.Invariant($"resolution=')==1
    assert old.replace(b'FormattableString.Invariant($"resolution=',b'FormattableString.Invariant($"Applied graphics: resolution=',1)==new
    return dict(coreSource=MELONX_SOURCE,coreRun=MELONX_RUN,regression=receipt,
        physicalDeviceTested=False,graphicsImprovementClaimed=False)

def embed(app):
    proof=expected()
    previous.embed(app)
    (app/IDENTITY).write_text(json.dumps(proof,indent=2)+'\n')

def validate(ipa,build):
    result=previous.validate(ipa,build)
    with zipfile.ZipFile(ipa) as z:
        root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
        proof=json.loads(z.read(root+IDENTITY));assert proof==expected()
        identity=json.loads(z.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
        assert identity['host']==MELONX_SOURCE
        assert identity['adaptations'][SESSION]==hashlib.sha256((ROOT/SESSION).read_bytes()).hexdigest()
        core=z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
        assert previous.contains(core,'Applied graphics: resolution='), 'Latest source-built journal prefix missing'
    return dict(result,latestGraphicsJournal=proof,compiledGraphicsJournalVerified=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
    p.add_argument('--build-number',type=int,default=539);p.add_argument('--report',type=Path);a=p.parse_args()
    if a.embed:embed(a.embed)
    else:
        assert a.ipa and a.report
        result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
