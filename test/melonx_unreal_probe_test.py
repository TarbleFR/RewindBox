#!/usr/bin/env python3
"""Compile the production bounded RomFS project detector, without private game data."""
import hashlib,json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='unreal-probe-')as tmp:
 p=Path(tmp);source=ROOT/'native/melonx/EmbeddedUnrealProjectProbe.cs';(p/source.name).write_bytes(source.read_bytes())
 (p/'Program.cs').write_text(r'''using System;using System.IO;using System.Linq;using Ryujinx.Library;
int checks=0;void Check(bool value){checks++;if(!value)throw new Exception("check "+checks);}
string Detect(params string[] files)=>EmbeddedUnrealProjectProbe.Detect(files);
Check(Detect("/Phoenix/Content/Paks/pakchunk0-Switch.pak")=="Phoenix");
Check(Detect("/Engine/Content/Paks/a.pak","/Phoenix/Content/Paks/A.PAK","/Phoenix/Content/Paks/B.pak")=="Phoenix");
Check(Detect("/Phoenix/content/paks/x.pak")=="Phoenix");
foreach(string x in new[]{"/Engine/Content/Paks/a.pak","/Phoenix/Content/NoPaks/a.pak","/Phoenix/Content/Paks/a.txt","/../Content/Paks/a.pak","/a\\b/Content/Paks/a.pak","/é/Content/Paks/a.pak"})Check(Detect(x)==null);
foreach(string x in new[]{"/Phoenix/Content/Paks/../a.pak","/Phoenix/Content/Paks//a.pak"}){bool bad=false;try{Detect(x);}catch(InvalidDataException){bad=true;}Check(bad);}
bool ambiguous=false;try{Detect("/Phoenix/Content/Paks/a.pak","/Other/Content/Paks/b.pak");}catch(InvalidDataException){ambiguous=true;}Check(ambiguous);
Check(EmbeddedUnrealProjectProbe.Detect(Enumerable.Repeat("/Phoenix/Content/Paks/a.pak",16384))=="Phoenix");
bool bounded=false;try{EmbeddedUnrealProjectProbe.Detect(Enumerable.Repeat("/Phoenix/Content/Paks/a.pak",16385));}catch(InvalidDataException){bounded=true;}Check(bounded);
Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new{result="passed",checks}));
''')
 (p/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><NuGetAudit>false</NuGetAudit><EnableNETAnalyzers>false</EnableNETAnalyzers></PropertyGroup></Project>')
 (p/'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}');(p/'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
 r=subprocess.run([os.environ.get('DOTNET','dotnet'),'run','--project',str(p),'-c','Release'],cwd=p,capture_output=True,text=True,timeout=90)
 if r.returncode:print(r.stdout,r.stderr);r.check_returncode()
 result=json.loads(next(l for l in r.stdout.splitlines()if l.startswith('{')))
 result.update(physicalGameDataRead=False,configurationLoadVerified=False,inputs={str(n.relative_to(ROOT)):hashlib.sha256(n.read_bytes()).hexdigest()for n in[source,Path(__file__)]})
 out=ROOT/'dist/melonx/unreal-probe-checks.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
