#!/usr/bin/env python3
"""Retain the exact resolved package declarations and original license files."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

source=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve();output.mkdir(parents=True,exist_ok=True)
records={}
for assets in sorted((source/'src').glob('*/obj/project.assets.json')):
 document=json.loads(assets.read_text());folders=[Path(p) for p in document.get('packageFolders',{})]
 for identifier,library in document.get('libraries',{}).items():
  if library.get('type')!='package' or identifier in records:continue
  name,version=identifier.rsplit('/',1);relative=library.get('path',f'{name.lower()}/{version}')
  package=next((folder/relative for folder in folders if (folder/relative).is_dir()),None)
  assert package is not None,identifier
  record={'id':name,'version':version,'resolvedSha512':library.get('sha512'),'notices':{}}
  target=output/'NuGet'/name/version;target.mkdir(parents=True,exist_ok=True)
  for path in package.rglob('*'):
   if not path.is_file():continue
   base=path.name.lower()
   if not (base.endswith('.nuspec') or base.endswith('.nupkg.sha512') or base.startswith(('license','copying','notice','third-party-notices','thirdpartynotices'))):continue
   assert path.stat().st_size<=16*1024*1024
   destination=target/path.relative_to(package);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
   record['notices'][str(destination.relative_to(output))]=hashlib.sha256(path.read_bytes()).hexdigest()
   if base.endswith('.nuspec'):
    root=ET.parse(path).getroot();ns={'n':root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
    metadata=root.find('n:metadata',ns) if ns else root.find('metadata')
    def node(key):return metadata.find('n:'+key,ns) if ns else metadata.find(key)
    for key in ['license','copyright','authors','projectUrl','licenseUrl']:
     value=node(key)
     if value is not None:record[key]={'text':value.text,'attributes':value.attrib}
    repo=node('repository')
    if repo is not None:record['repository']=repo.attrib
  assert record['notices'],identifier
  records[identifier]=record
# Include the SDK/runtime's original .NET license and third-party notices.
dotnet=Path(shutil.which('dotnet')).resolve().parent
for path in dotnet.iterdir():
 if path.is_file() and path.name.lower().startswith(('license','thirdpartynotices','third-party-notices')):
  shutil.copy2(path,output/path.name)
config=output/'BuildConfiguration';config.mkdir(exist_ok=True)
for path in [source/'global.json',source/'nuget.config',source/'src/Ryujinx.Library/Ryujinx.Library.csproj']:
 shutil.copy2(path,config/path.name)
receipt={'packages':records,'dotnetInfo':subprocess.check_output(['dotnet','--info'],cwd=source,text=True),
         'scope':'Resolved package declarations and original license files; not an attestation that all corresponding-source obligations are complete.'}
(output/'resolved-managed-packages.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Retained resolved managed package notices:',len(records))
