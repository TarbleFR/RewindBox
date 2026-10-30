#!/usr/bin/env python3
"""Real helper JS plus extracted actual Core reply validator; native boundaries doubled."""
import argparse,hashlib,importlib,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args()
sys.path.insert(0,str(ROOT/'build-utils/melonx'));import adapt_sized_jit as adapter
node=json.loads(subprocess.check_output(['node',str(ROOT/'test/melonx_sized_jit/Protocol.js'),str(ROOT/'packages/melonx_jit_helper/ios/Resources/melonx-universal.js')],text=True))
output=adapter.edits(a.source);text=next(iter(output.values()));begin=text.index('        private unsafe nint PrepareSizedArena()');end=text.index('        private void AllocateDualMapping',begin);method=text[begin:end].replace('private unsafe nint PrepareSizedArena','public unsafe nint PrepareSizedArena')
with tempfile.TemporaryDirectory(prefix='sized-jit-managed-')as tmp:
 work=Path(tmp)
 (work/'Probe.cs').write_text('''using System;
unsafe class Probe {
 public ulong Size{get;private set;}public Probe(ulong size){Size=size;}
 public static bool OldHelper,Refused;public static int Calls,Corrupt=-1;public static ulong Actual,CorruptValue;
 static byte* BreakGetJITMappingPub(byte* descriptor,nuint count){Calls++;if(descriptor==null)return OldHelper?null:(byte*)0x5242574a49543031UL;ulong* r=(ulong*)descriptor;if(Refused){r[6]=2;r[7]=9;return null;}r[4]=Actual;r[5]=0x400000000UL;r[6]=1;r[7]=2;if(Corrupt>=0)r[Corrupt]=CorruptValue;return (byte*)0x400000000UL;}
'''+method+'}')
 (work/'Program.cs').write_text('''using System;
unsafe class Program{
 static int checks;static void Check(bool v){checks++;if(!v)throw new Exception("check "+checks);}
 static void Reset(){Probe.OldHelper=Probe.Refused=false;Probe.Calls=0;Probe.Corrupt=-1;Probe.Actual=1024UL<<20;}
 static void Reject(ulong requested){var p=new Probe(requested);bool threw=false;try{p.PrepareSizedArena();}catch(Exception){threw=true;}Check(threw&&p.Size==requested);}
 static void Main(){for(ulong size=512UL<<20;size<=1024UL<<20;size+=64UL<<20){Reset();Probe.Actual=size;var p=new Probe(1024UL<<20);Check((ulong)p.PrepareSizedArena()==0x400000000UL&&p.Size==size&&Probe.Calls==2);}
 Reset();Probe.OldHelper=true;Reject(1024UL<<20);Check(Probe.Calls==1);
 Reset();Probe.Refused=true;Reject(1024UL<<20);Check(Probe.Calls==2);
 foreach(var test in new( int,ulong)[]{(0,0),(1,960UL<<20),(2,448UL<<20),(3,32UL<<20),(4,448UL<<20),(4,1088UL<<20),(4,513UL<<20),(5,0),(5,0x400000001UL),(6,0),(6,3),(7,0),(7,10)}){Reset();Probe.Corrupt=test.Item1;Probe.CorruptValue=test.Item2;Reject(1024UL<<20);Check(Probe.Calls==2);}
 foreach(ulong size in new[]{448UL<<20,1088UL<<20,1023UL<<20}){Reset();Reject(size);Check(Probe.Calls==0);}
 Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new{checks,result="passed"}));}}
''')
 (work/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit><EnableNETAnalyzers>false</EnableNETAnalyzers></PropertyGroup></Project>')
 (work/'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}');(work/'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
 r=subprocess.run([os.environ.get('DOTNET','dotnet'),'run','--project',str(work),'-c','Release'],cwd=work,capture_output=True,text=True,timeout=90)
 if r.returncode:print(r.stdout,r.stderr);r.check_returncode()
 managed=json.loads(next(l for l in r.stdout.splitlines()if l.startswith('{')))
inputs=['build-utils/melonx/adapt_sized_jit.py','packages/melonx_jit_helper/ios/Resources/melonx-universal.js','test/melonx_sized_jit_test.py','test/melonx_sized_jit/Protocol.js']
report=dict(result='passed',helper=node,managed=managed,physicalDeviceTested=False,nativeVMAndTransportDoubled=True,inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in inputs})
o=ROOT/'dist/melonx/sized-jit-checks.json';o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
