"""Transport the existing encrypted payload in four bounded, verified pieces."""
import argparse,hashlib,json,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
a=p.parse_args();names={'artifact.tar.enc','format.json','password.rsa'}
assert {f.name for f in a.source.iterdir()}==names
files={n:(a.source/n).read_bytes() for n in names}
assert json.loads(files['format.json'])=={'cipher':'AES-256-CBC PBKDF2 200000','keyEnvelope':'RSA OAEP SHA256','content':'tar','publication':'encrypted delivery only'}
data=files['artifact.tar.enc'];width=(len(data)+3)//4
assert 0<width<=64*1024*1024
parts=[data[i*width:(i+1)*width] for i in range(4)]
manifest=dict(schemaVersion=1,source=os.environ['GITHUB_SHA'],run=int(os.environ['GITHUB_RUN_ID']),
 build=int(os.environ['BUILD_NUMBER']),encrypted=True,rebuilt=False,
 files={n:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in sorted(files.items())},
 parts=[dict(index=i,bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for i,v in enumerate(parts)])
assert b''.join(parts)==data
for i,part in enumerate(parts):
 folder=a.destination/('part%02d'%i);folder.mkdir(parents=True,exist_ok=False)
 (folder/'data.bin').write_bytes(part)
 for name in ['format.json','password.rsa']:(folder/name).write_bytes(files[name])
 (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
