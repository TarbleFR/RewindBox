#!/usr/bin/env python3
"""Execute the real packed-depth formatter and mip endpoint mapper, old and new."""
import argparse,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();sys.path.insert(0,str(ROOT/'build-utils/melonx'));import adapt_texture_readback_bounds as adapter

def method(s,marker):
 start=s.index(marker);end=s.index('{',start)+1;depth=1
 while depth:
  depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[start:end]
new=adapter.edits(a.source);reports={}
with tempfile.TemporaryDirectory(prefix='texture-readback-')as tmp:
 for variant in ['control','candidate']:
  w=Path(tmp)/variant;w.mkdir()
  view=a.source/'src/Ryujinx.Graphics.Vulkan/TextureView.cs';copy=a.source/'src/Ryujinx.Graphics.Vulkan/TextureCopy.cs'
  v=view.read_text()if variant=='control'else new[view];c=copy.read_text()if variant=='control'else new[copy]
  formatter=method(v,'private ReadOnlySpan<byte> GetDataFromBuffer(').replace('private ReadOnlySpan','public ReadOnlySpan')
  mapper=method(c,'static (Offset3D, Offset3D) ExtentsToOffset3D(').replace('static (Offset3D','public static (Offset3D')
  (w/'Probe.cs').write_text('using System;class Probe {public bool Convert=true;bool NeedsD24S8Conversion()=>Convert;int GetBufferDataLength(int n)=>n*2;'+formatter+mapper+'}\nrecord struct Offset3D(int X,int Y,int Z);record struct Extents2D(int X1,int Y1,int X2,int Y2);')
  (w/'FormatConverter.cs').write_bytes((a.source/'src/Ryujinx.Graphics.Vulkan/FormatConverter.cs').read_bytes())
  s=(w/'Probe.cs').read_text().replace('using System;','using System;using Ryujinx.Graphics.Vulkan;');(w/'Probe.cs').write_text(s)
  (w/'Program.cs').write_text(r'''using System;using System.Runtime.InteropServices;
class Program {static int checks;static void Check(bool v){checks++;if(!v)throw new Exception("check "+checks);}static void Main(){
 var p=new Probe();for(int count=1;count<=257;count+=4){byte[] host=new byte[count*8];var input=MemoryMarshal.Cast<byte,uint>(host.AsSpan());for(int i=0;i<count;i++){input[i*2]=(uint)BitConverter.SingleToInt32Bits((i%3)*0.5f);input[i*2+1]=(uint)(i&255);}
 foreach(bool inplace in new[]{false,true}){byte[] work=(byte[])host.Clone();var data=p.GetDataFromBuffer(work,work.Length,inplace?work:Span<byte>.Empty);
#if CANDIDATE
 Check(data.Length==count*4);
#else
 Check(data.Length==(inplace?count*8:count*16));
#endif
 var words=MemoryMarshal.Cast<byte,uint>(data);for(int i=0;i<count;i++){uint depth=(i%3)==0?0u:(i%3)==1?0x7fffffu:0xffffffu;Check(words[i]==(depth<<8|(uint)(i&255)));}
 }
 }
 p.Convert=false;byte[] plain={1,2,3,4,5,6,7,8};Check(p.GetDataFromBuffer(plain,plain.Length,Span<byte>.Empty).SequenceEqual(plain));
 foreach(int width in new[]{1,2,3,4,7,8,16,31,64,127,256})foreach(int height in new[]{1,2,3,8,31,64,128}){
 int levels=1+(int)Math.Floor(Math.Log2(Math.Max(width,height)));
 for(int level=0;level<levels;level++)foreach(bool flipX in new[]{false,true})foreach(bool flipY in new[]{false,true}){
 var(a,b)=Probe.ExtentsToOffset3D(new(flipX?width:0,flipY?height:0,flipX?0:width,flipY?0:height),width,height,level);
#if CANDIDATE
 int x=Math.Max(1,width>>level),y=Math.Max(1,height>>level);
#else
 int x=width>>level,y=height>>level;
#endif
 Check(a.X==(flipX?x:0)&&b.X==(flipX?0:x)&&a.Y==(flipY?y:0)&&b.Y==(flipY?0:y));Check(a.Z==0&&b.Z==1);
 }}
#if CANDIDATE
 // D32FS8 records are eight bytes. Malformed or truncated readbacks fail before conversion.
 p.Convert=true;foreach(int length in new[]{-1,1,4,7,9}){bool threw=false;try{p.GetDataFromBuffer(new byte[16],length,Span<byte>.Empty);}catch(ArgumentException){threw=true;}Check(threw);}
 bool shortInput=false;try{p.GetDataFromBuffer(new byte[8],16,Span<byte>.Empty);}catch(ArgumentException){shortInput=true;}Check(shortInput);
#endif
 Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new{checks,result="passed"}));}}
''')
  (w/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><DefineConstants>'+('CANDIDATE'if variant=='candidate'else'CONTROL')+'</DefineConstants><NuGetAudit>false</NuGetAudit><EnableNETAnalyzers>false</EnableNETAnalyzers></PropertyGroup></Project>')
  (w/'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}');(w/'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
  r=subprocess.run([os.environ.get('DOTNET','dotnet'),'run','--project',str(w),'-c','Release'],cwd=w,capture_output=True,text=True,timeout=90)
  if r.returncode:print(r.stdout,r.stderr);r.check_returncode()
  reports[variant]=json.loads(next(l for l in r.stdout.splitlines()if l.startswith('{')))
inputs=['build-utils/melonx/adapt_texture_readback_bounds.py','test/melonx_texture_readback_bounds_test.py']
r=dict(result='passed',reports=reports,productionMethodsExtracted=True,vulkanDriverExecuted=False,physicalBlackTextureFixProven=False,inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in inputs})
p=ROOT/'dist/melonx/texture-readback-bounds-checks.json';p.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
