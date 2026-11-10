#!/usr/bin/env python3
"""Independently verify downloaded Core bytes; never execute historical fixtures."""
import argparse,hashlib,io,json,struct,sys,zipfile
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'build-utils/melonx'))
from validate_runtime_reuse import verify_smoke_report

def sha(raw):return hashlib.sha256(raw).hexdigest()
def safe(name):
 p=PurePosixPath(name)
 assert name and not p.is_absolute()and'..'not in p.parts and'\\'not in name,name

def macho(raw,platform,required):
 magic,cpu,sub,kind,count,length,flags,reserved=struct.unpack_from('<8I',raw)
 assert magic==0xfeedfacf and cpu==0x100000c and kind==6,'Not an ARM64 dylib'
 at=32;table=None;build=None
 for _ in range(count):
  cmd,size=struct.unpack_from('<II',raw,at);assert size>=8 and at+size<=32+length
  if cmd==2:table=struct.unpack_from('<4I',raw,at+8)
  if cmd==0x32:build=struct.unpack_from('<4I',raw,at+8)
  at+=size
 assert at==32+length and build and build[0]==platform,'Wrong target platform'
 assert table,'Missing real symbol table'
 symoff,nsyms,stroff,strsize=table;assert symoff+nsyms*16<=len(raw)and stroff+strsize<=len(raw)
 names=set()
 for index in range(nsyms):
  strx,typ,sect,desc,value=struct.unpack_from('<IBBHQ',raw,symoff+index*16)
  if not(typ&1)or not(typ&0xe)or typ&0xe0:continue
  assert strx<strsize
  end=raw.index(b'\0',stroff+strx,stroff+strsize)
  names.add(raw[stroff+strx:end].decode())
 assert {'_'+n for n in required}<=names,'Missing actual ABI symbol'
 return dict(cpu='arm64',platform=platform,minOS=build[1],sdk=build[2],publicDefinitions=len(names),requiredExports=len(required))

def main():
 p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--source',required=True);p.add_argument('--sha256',required=True);p.add_argument('--bytes',required=True,type=int);p.add_argument('--output',type=Path);a=p.parse_args()
 assert a.archive.stat().st_size==a.bytes and sha(a.archive.read_bytes())==a.sha256
 c=json.loads((ROOT/'build-utils/melonx/hogwarts-launch-core-contract.json').read_text())
 with zipfile.ZipFile(a.archive)as z:
  names=z.namelist();assert len(names)==len(set(names));assert z.testzip()is None
  for n in names:safe(n)
  result=json.loads(z.read('core-validation/result.json'));gates=json.loads(z.read('core-validation/gates.json'));preflight=json.loads(z.read('core-validation/preflight.json'))
  assert result['result']=='passed'and result['execution']['source']==a.source and result['physicalDeviceTested']is False
  assert result['hogwartsCrashCauseProven']is False and result['gpuStartupDelayFixed']is False
  assert result['freshAppleGates']==1 and result['reusedAppleGates']==36
  assert sha(z.read('core-validation/gates.json'))==result['gateReceiptSha256']
  assert json.loads(z.read('embedded-inputs.json'))==c['preparationInputs']
  for n,h in c['preparationInputs'].items():assert sha((ROOT/n).read_bytes())==h,n
  with zipfile.ZipFile(io.BytesIO(z.read('embedded-adapted-source.zip')))as prepared:
   assert len(prepared.namelist())==len(set(prepared.namelist()))==154
   assert {n:sha(prepared.read(n))for n in prepared.namelist()}==c['preparedMembers']
  assert len(gates['receipts'])==1 and len(gates['retainedReceipts'])==36
  for n,h in {**gates['receipts'],**gates['retainedReceipts']}.items():
   raw=z.read(n);assert sha(raw)==h and json.loads(raw)['result']=='passed',n
  literal=json.loads(z.read('reused-literal/literal-memory-checks.json'))
  assert literal['checks']==12167 and literal['wrongWidth']==620 and literal['lostVector31']==literal['lostZeroReads']==60
  for n,h in literal['inputs'].items():assert sha((ROOT/n).read_bytes())==h,n
  binaries={}
  for runtime,platform in [('ios-arm64',2),('iossimulator-arm64',7)]:
   identityRaw=z.read(runtime+'/identity.json');identity=json.loads(identityRaw);raw=z.read(runtime+'/Ryujinx.Library.dylib')
   assert identity['host']==a.source and identity['runtimeIdentifier']==runtime and identity['embeddedLibraryAbi']==2
   assert identity['source']==json.loads((ROOT/'build-utils/melonx/source.json').read_text())and identity['adaptations']==c['preparationInputs']
   assert sha(identityRaw)==result['identities'][runtime]and sha(raw)==identity['sha256']==result['binaries'][runtime]['sha256']and len(raw)==identity['size']==result['binaries'][runtime]['bytes']
   binaries[runtime]=dict(sha256=sha(raw),bytes=len(raw),**macho(raw,platform,identity['exports']))
  smoke=json.loads(z.read('runtime-smoke/actual-runtime.json'))
  assert sha(z.read('runtime-smoke/actual-runtime.json'))==result['runtimeSmokeSha256']
  verify_smoke_report(smoke,{'simulatorSha256':binaries['iossimulator-arm64']['sha256']},preflight['smokeInputs'])
  assert result['homebrewSimulatorSessions']==result['releasedBackingSessions']==2
  for n,h in result['inputs'].items():assert sha((ROOT/n).read_bytes())==h,n
 report=dict(result='passed',execution=result['execution'],archive=dict(filename=a.archive.name,bytes=a.bytes,sha256=a.sha256),binaries=binaries,preparationInputs=117,preparedMembers=154,freshAppleGates=1,reusedAppleReceipts=36,literalChecks=12167,homebrewSimulatorSessions=2,releasedBackingSessions=2,physicalHogwartsTested=False,hogwartsCrashCauseProven=False,gpuStartupDelayFixed=False)
 if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report))

if __name__=='__main__':main()
