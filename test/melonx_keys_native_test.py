#!/usr/bin/env python3
"""Reproduce the old rejection and exercise the actual pinned LibHac reader.

Synthetic non-secret bytes only. Native content case 2 is extracted verbatim;
its dependencies are doubles to observe unintended live-set/firmware writes.
The iOS smoke separately exercises the compiled export with the real runtime.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'c34dc844ce28c5e46b972215122f01415fd88239'
package = Path(sys.argv[1])
assert hashlib.sha256(package.read_bytes()).hexdigest() == 'b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9'
with tempfile.TemporaryDirectory(prefix='melonx-keys-') as temporary:
    work = Path(temporary)
    with zipfile.ZipFile(package) as archive:
        (work / 'LibHac.dll').write_bytes(archive.read('lib/net8.0/LibHac.dll'))
    (work / 'Test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
      <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
      </PropertyGroup><ItemGroup><Reference Include="LibHac"><HintPath>LibHac.dll</HintPath></Reference></ItemGroup></Project>''')
    old = subprocess.check_output(['git', 'show', BASELINE + ':native/melonx/EmbeddedKeyValidation.cs'], cwd=ROOT, text=True)
    (work / 'OldValidation.cs').write_text(old.replace('EmbeddedKeyValidation', 'OldValidation'))
    shutil.copyfile(ROOT / 'native/melonx/EmbeddedKeyValidation.cs', work / 'EmbeddedKeyValidation.cs')
    content = (ROOT / 'native/melonx/EmbeddedContent.cs').read_text()
    case = content.split('                            case 2:\n', 1)[1].split('                            case 3:', 1)[0]
    assert case.endswith('                                break;\n')
    case = case.removesuffix('                                break;\n')
    (work / 'Content.cs').write_text('''using System;
using System.IO;
using System.Text.Json;
namespace Ryujinx.Library;
internal static class ContentProbe {
 internal static int Reloads, FirmwareScans;
 private sealed class Files {internal void ReloadKeySet(){Reloads++;throw new IOException("old installation deliberately unavailable");}}
 private sealed class Firmware {internal void LoadEntries(){FirmwareScans++;throw new IOException("unrelated firmware failure");}}
 private static Files _virtualFileSystem = new();
 private static Firmware _contentManager = new();
 internal static string Run(string path) {
 using var memory = new MemoryStream();using var json = new Utf8JsonWriter(memory);json.WriteStartObject();
''' + case + '''
 json.WriteEndObject();json.Flush();return System.Text.Encoding.UTF8.GetString(memory.ToArray());
 }
}
''')
    (work / 'Program.cs').write_text(r'''using System;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Linq;
using LibHac.Common.Keys;
using Ryujinx.Library;
int checks=0;
void Check(bool value){if(!value)throw new Exception("Personal key regression assertion failed (no key material logged).");checks++;}
var root=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
var prod=Path.Combine(root,"prod.keys");var title=Path.Combine(root,"title.keys");
string header="header_key = "+new string('a',64), extra="future_console_key = "+new string('b',32);
void Reject(string text,string code,string path=null){path??=prod;File.WriteAllText(path,text);
 try{EmbeddedKeyValidation.Validate(path);throw new Exception("Malformed fixture accepted.");}
 catch(InvalidDataException error){Check(EmbeddedKeyValidation.ErrorCode(error)==code);Check(!error.ToString().Contains(new string('a',64)));}}
try {
 File.WriteAllText(prod,header+"\n"+extra);
 try{OldValidation.Validate(prod);throw new Exception("Old rejection was not reproduced.");}
 catch(InvalidDataException){checks++;Console.WriteLine("Old Build 515 rejects supported keys accompanied by an unknown entry: reproduced.");}
 var result=EmbeddedKeyValidation.Validate(prod);Check(result.Recognized==1&&result.Ignored==1);
 // Use the real compiled LibHac reader to prove that the header entry actually
 // reaches the key set even though the unknown entry is retained in the file.
 var keys=KeySet.CreateDefaultKeySet();var schema=KeySet.CreateKeyInfoList();
 using(var input=File.OpenRead(prod))ExternalKeyReader.ReadMainKeys(keys,input,schema,null);
 var info=schema.First(k=>k.Matches("header_key".AsSpan(),out _,out _));
 Check(info.Getter(keys,0).ToArray().All(b=>b==0xaa));
 File.WriteAllText(prod,header+"\n"+header.ToUpperInvariant()+"\n"+extra);
 result=EmbeddedKeyValidation.Validate(prod);Check(result.Recognized==1&&result.Ignored==1);
 foreach(var encoding in new Encoding[]{new UTF8Encoding(true),Encoding.Unicode,Encoding.BigEndianUnicode}) {
  File.WriteAllText(prod,"# personal export\r\n\r\n"+header.ToUpperInvariant().Replace(" = ",",\t")+"\r\n"+extra,encoding);
  result=EmbeddedKeyValidation.Validate(prod);Check(result.Recognized==1&&result.Ignored==1);
  keys=KeySet.CreateDefaultKeySet();using(var input=File.OpenRead(prod))ExternalKeyReader.ReadMainKeys(keys,input,schema,null);
  Check(info.Getter(keys,0).ToArray().All(b=>b==0xaa));
 }
 Reject(extra,"keyNoSupported");Reject("# comment\n","keyNoSupported");
 Reject("header_key = aa","keySize");Reject("header_key = aaa","keySyntax");
 Reject("header_key = zz","keySyntax");Reject("invalid line","keySyntax");
 Reject(header+"\nheader_key = "+new string('b',64),"keyConflict");
 Reject("header_key = "+new string('a',2048),"keySyntax");
 Reject(new string('a',4*1024*1024+1),"keySyntax");
 File.WriteAllText(title,new string('1',32)+" = "+new string('a',32));
 Check(EmbeddedKeyValidation.Validate(title).Recognized==1);
 Reject(new string('1',32)+" = aa","keySize",title);
 Reject("bad_rights = "+new string('a',32),"keySyntax",title);
 // Preview must succeed even when a live reload would fail, and leave old data
 // alone. Installation is the only branch that invokes the reload.
 File.WriteAllText(prod,header+"\n"+extra);
 using(var report=JsonDocument.Parse(ContentProbe.Run(prod))){
  Check(report.RootElement.GetProperty("recognizedKeys").GetInt32()==1);
  Check(report.RootElement.GetProperty("ignoredKeys").GetInt32()==1);
 }
 Check(ContentProbe.Reloads==0&&ContentProbe.FirmwareScans==0);
 try{ContentProbe.Run("");throw new Exception("Reload not reached.");}catch(IOException){Check(ContentProbe.Reloads==1&&ContentProbe.FirmwareScans==0);}
 Check(EmbeddedKeyValidation.ErrorCode(new IOException())=="keyReadFailed");
 Check(EmbeddedKeyValidation.ErrorCode(new InvalidOperationException())=="keyImportFailed");
 Console.WriteLine($"{checks} production key/real LibHac reader/preview isolation checks passed.");
}finally{Directory.Delete(root,true);}
''')
    try:
        output = subprocess.check_output(['dotnet', 'run', '--project', str(work / 'Test.csproj'), '-c', 'Release'], text=True, stderr=subprocess.STDOUT, timeout=180)
    except subprocess.CalledProcessError as error:
        print(error.output, flush=True)
        raise
    print(output)
    assert 'Old Build 515 rejects' in output and 'checks passed.' in output
    out = ROOT / 'dist/melonx/keys-regression.json'; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'baseline':BASELINE,'result':output,'personalKeysUsed':False,
      'inputs':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
        ['test/melonx_keys_native_test.py','native/melonx/EmbeddedKeyValidation.cs','native/melonx/EmbeddedContent.cs']},
      'libHacPackageSha256':hashlib.sha256(package.read_bytes()).hexdigest()},indent=2)+'\n')
