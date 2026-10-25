"""Diagnose import refusal using the exact shipped LibHac and synthetic values."""
from pathlib import Path
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
package = Path(sys.argv[1])
assert hashlib.sha256(package.read_bytes()).hexdigest() == 'b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9'
out = ROOT / 'dist/key-shape-probe'
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='key-shape-') as temp:
    work = Path(temp)
    with zipfile.ZipFile(package) as z:
        (work/'LibHac.dll').write_bytes(z.read('lib/net8.0/LibHac.dll'))
    shutil.copyfile(ROOT/'native/melonx/EmbeddedKeyValidation.cs', work/'EmbeddedKeyValidation.cs')
    shutil.copyfile(ROOT/'test/fixtures/melonx_key_shape_517.json', work/'shape.json')
    (work/'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
      <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
      </PropertyGroup><ItemGroup><Reference Include="LibHac"><HintPath>LibHac.dll</HintPath></Reference></ItemGroup></Project>''')
    (work/'Program.cs').write_text(r'''using System;
using System.IO;
using System.Text.Json;
using System.Collections.Generic;
using System.Linq;
using LibHac.Common.Keys;
using Ryujinx.Library;
var fixture=JsonDocument.Parse(File.ReadAllText("shape.json")).RootElement;
var removed=fixture.GetProperty("copyRemovedNames").EnumerateArray().Select(x=>x.GetString()).ToHashSet();
var keys=KeySet.CreateDefaultKeySet();var schema=KeySet.CreateKeyInfoList();var mismatches=new List<object>();
var original=new List<string>();var copy=new List<string>();
foreach(var row in fixture.GetProperty("original").EnumerateArray()){
 var name=row.GetProperty("name").GetString();var size=row.GetProperty("hexChars").GetInt32();
 var text=name+" = "+new string('a',size);original.Add(text);if(!removed.Contains(name))copy.Add(text);
 foreach(var info in schema){if(info.Matches(name.AsSpan(),out int index,out _)){
  int expected=info.Getter(keys,index).Length*2;
  if(expected!=size)mismatches.Add(new {name,actual=size,expected,line=row.GetProperty("originalLine").GetInt32()});
  break;
 }}
}
var reports=new List<object>();
foreach(var entry in new[]{("original",original),("copy",copy)}){
 File.WriteAllLines("prod.keys",entry.Item2);
 try{var result=EmbeddedKeyValidation.Validate("prod.keys");reports.Add(new {input=entry.Item1,result="accepted",recognized=result.Recognized,ignored=result.Ignored});}
 catch(Exception error){reports.Add(new {input=entry.Item1,result="refused",code=EmbeddedKeyValidation.ErrorCode(error)});}
}
File.WriteAllText("result.json",JsonSerializer.Serialize(new {runtime=System.Runtime.InteropServices.RuntimeInformation.RuntimeIdentifier,mismatches,reports,syntheticOnly=true},new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine(File.ReadAllText("result.json"));
''')
    subprocess.run(['dotnet','run','--project','Probe.csproj','-c','Release'],cwd=work,check=True,timeout=180)
    shutil.copyfile(work/'result.json',out/'native-result.json')
try:
    url='https://pub.dev/api/archives/file_picker-12.0.0-beta.3.tar.gz'
    with urllib.request.urlopen(url,timeout=60) as response:
        data=response.read(20*1024*1024)
    assert hashlib.sha256(data).hexdigest()=='51093fc49e4d58935998fb112593c23eda571d14b488388bd41d5d2ba332b26a'
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
        for member in tar:
            if member.isfile() and member.name.endswith('.swift') and 'IOSFilePicker' in member.name:
                text=tar.extractfile(member).read().decode('utf-8')
                (out/Path(member.name).name).write_text(text)
                lines=text.splitlines()
                for index,line in enumerate(lines):
                    if 'copyToTemporaryDirectory' in line:
                        print('\n'.join(lines[max(0,index-3):index+35]))
    (out/'picker-package.json').write_text(json.dumps({'version':'12.0.0-beta.3','sha256':hashlib.sha256(data).hexdigest(),'verified':True}))
except Exception as error:
    print('Picker source retrieval unavailable:',type(error).__name__)
    (out/'picker-package.json').write_text(json.dumps({'verified':False,'errorType':type(error).__name__}))
