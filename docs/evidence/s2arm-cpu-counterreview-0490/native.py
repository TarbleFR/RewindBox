from pathlib import Path
import argparse,json,os,statistics,subprocess,sys,shutil
from xml.sax.saxutils import escape
parser=argparse.ArgumentParser(description="Compile and compare the extracted session-table methods with NativeAOT on Linux x64.")
parser.add_argument('--reference',type=Path,required=True)
parser.add_argument('--candidate',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--dotnet',default=shutil.which('dotnet') or 'dotnet')
parser.add_argument('--illink-assembly',type=Path,help='Optional in-process ILLink task override for environments that cannot create MSBuild task hosts')
a=parser.parse_args()
root=a.output.resolve();root.mkdir(parents=True,exist_ok=True)
dotnet=a.dotnet
subprocess.run([sys.executable,str(Path(__file__).with_name('check.py')),'--reference',str(a.reference),'--candidate',str(a.candidate),'--output',str(root),'--dotnet',dotnet,'--generate-only'],check=True)
tasks=''
if a.illink_assembly:
 assembly=escape(str(a.illink_assembly.resolve()))
 tasks=f'<UsingTask TaskName="ComputeManagedAssemblies" AssemblyFile="{assembly}" Override="true" /><UsingTask TaskName="ILLink" AssemblyFile="{assembly}" Override="true" />'
for name in ['before','after']:
 p=root/(name+'-native');p.mkdir(exist_ok=True)
 code=(root/name/'Program.cs').read_text()
 code=code.replace('Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new{test="trace",ops,objects=id,digest=hash.ToString("x16"),capacity=d.Snapshot().capacity}));',r'''Console.WriteLine($"{{\"test\":\"trace\",\"ops\":{ops},\"objects\":{id},\"digest\":\"{hash:x16}\",\"capacity\":{d.Snapshot().capacity}}}");''')
 code=code.replace('Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new{test="concurrent",workers=8,operations=closes,errors}));',r'''Console.WriteLine($"{{\"test\":\"concurrent\",\"workers\":8,\"operations\":{closes},\"errors\":{errors}}}");''')
 code=code.replace('Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new{test="bench",filled,ns=sw.Elapsed.TotalNanoseconds/loops,sink}));',r'''Console.WriteLine(FormattableString.Invariant($"{{\"test\":\"bench\",\"filled\":{filled},\"ns\":{sw.Elapsed.TotalNanoseconds/loops},\"sink\":{sink}}}"));''')
 assert 'JsonSerializer' not in code
 (p/'Program.cs').write_text(code)
 (p/'NuGet.Config').write_text('<configuration><packageSources><clear/></packageSources></configuration>')
 (p/'bench.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable><Optimize>true</Optimize><PublishAot>true</PublishAot></PropertyGroup>'+tasks+'</Project>')
 with (p/'build.log').open('w') as log:
  result=subprocess.run([dotnet,'publish',str(p/'bench.csproj'),'-c','Release','-r','linux-x64','--nologo','-v','minimal'],stdout=log,stderr=subprocess.STDOUT)
 assert result.returncode==0,(p/'build.log').read_text()
 print(name+' published',flush=True)


def run(name,flag,*args):
 env=dict(os.environ,S2A_RB_SESSION_SCAN=str(flag))
 r=subprocess.run([str(root/(name+'-native')/'bin/Release/net10.0/linux-x64/publish/bench'),*map(str,args)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 assert r.returncode==0,r.stdout
 return [json.loads(x) for x in r.stdout.splitlines() if x.startswith('{')]
proof=[]
for label,name,flag in [('reference0479','before',1),('0493_flag0','after',0),('0493_flag1','after',1)]:
 proof.append({'variant':label,'results':run(name,flag)})
assert len({x['results'][0]['digest'] for x in proof})==1
(root/'native-correctness.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof,indent=2),flush=True)
rows=[]
for filled in [0,512,1023]:
 for pair in range(6):
  choices=[('reference0479','before',1),('0493_flag0','after',0),('0493_flag1','after',1)]
  if pair%2:choices.reverse()
  for label,name,flag in choices:
   row=run(name,flag,'bench',filled)[0];row.update(variant=label,pair=pair);rows.append(row)
(root/'native-timing.json').write_text(json.dumps(rows,indent=2)+'\n')
summary=[]
for filled in [0,512,1023]:
 summary.append({'filled':filled,**{label:statistics.median(r['ns'] for r in rows if r['filled']==filled and r['variant']==label)for label in ['reference0479','0493_flag0','0493_flag1']}})
(root/'native-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
